"""Stable port-axis approach and impulse-based fuel accounting."""

import numpy as np
import pytest
from conftest import make_request

from app.schemas.docking import MotionLimits
from app.schemas.events import LlmSubgoal
from app.sessions.store import Session
from app.simulation.dynamics import Command, RigidBodyState
from app.simulation.propellant import G0_MPS2, apply_propellant, mass_flow_kgps
from app.simulation.runner import SimulationRunner


def test_propellant_matches_engine_and_rcs_impulse():
    command = Command(force_n=np.array([30.0, 40.0, 0.0]), torque_nm=np.array([3.0, -6.0, 0.0]))
    expected_flow = 50 / (220 * G0_MPS2) + 9 / (0.75 * 60 * G0_MPS2)
    assert mass_flow_kgps(command) == pytest.approx(expected_flow)
    state = RigidBodyState()
    before_mass, before_inertia = state.mass_kg, state.inertia.copy()
    _, used, flow = apply_propellant(state, command, 2)
    assert used == pytest.approx(expected_flow * 2)
    assert flow == pytest.approx(expected_flow)
    assert state.mass_kg == pytest.approx(before_mass - used)
    assert state.fuel_pct == pytest.approx(100 - used / 25 * 100)
    assert np.allclose(state.inertia, before_inertia * state.mass_kg / before_mass)


def test_coasting_is_free_and_rotational_thrusters_consume_propellant():
    state = RigidBodyState()
    _, used, flow = apply_propellant(state, Command(), 10)
    assert used == flow == 0
    assert state.fuel_pct == 100
    torque_only = Command(torque_nm=np.array([20.0, 0.0, 0.0]))
    _, used, _ = apply_propellant(state, torque_only, 10)
    assert used == pytest.approx(20 / (0.75 * 60 * G0_MPS2) * 10)
    assert state.fuel_pct < 100
    assert mass_flow_kgps(Command(torque_nm=torque_only.torque_nm * 0.5)) == pytest.approx(
        mass_flow_kgps(torque_only) / 2
    )


def test_exhaustion_scales_force_and_torque_to_available_impulse():
    state = RigidBodyState(fuel_pct=0.01)
    command = Command(force_n=np.array([50.0, 0, 0]), torque_nm=np.array([20.0, 0, 0]))
    requested = mass_flow_kgps(command) * 2
    actual, used, _ = apply_propellant(state, command, 2)
    assert used == pytest.approx(25 * 0.01 / 100)
    assert np.allclose(actual.force_n, command.force_n * used / requested)
    assert np.allclose(actual.torque_nm, command.torque_nm * used / requested)
    assert state.fuel_pct == 0
    actual, used, _ = apply_propellant(state, command, 2)
    assert used == 0
    assert np.linalg.norm(actual.force_n) == np.linalg.norm(actual.torque_nm) == 0


@pytest.mark.parametrize("controller", ["lqr", "pid"])
async def test_tumbling_craft_stabilizes_before_final_closure(controller):
    request = make_request(
        position=(80, 48, 36),
        angular_velocity=(1, 3, 0),
        controller=controller,
        step_interval_s=0.2,
        max_steps=3000,
        max_thrust_n=50,
        max_acceleration_mps2=0.1,
        near_port_speed_mps=0.3,
        llm_cadence_steps=240,
        rl_advisor_enabled=False,
    )
    # Roll 15, pitch 40, yaw 35 degrees: the user's tumbling case.
    roll, pitch, yaw = np.deg2rad([15, 40, 35]) / 2
    cx, cy, cz = np.cos([roll, pitch, yaw])
    sx, sy, sz = np.sin([roll, pitch, yaw])
    request.secondary.orientation_quat = [
        cx * cy * cz + sx * sy * sz,
        sx * cy * cz - cx * sy * sz,
        cx * sy * cz + sx * cy * sz,
        cx * cy * sz - sx * sy * cz,
    ]
    request.secondary.motion_limits = MotionLimits(
        max_speed_mps=2, max_horizontal_speed_mps=2, max_vertical_speed_mps=2
    )
    session = Session("tumbling-port-alignment")
    await SimulationRunner(session, request).run()
    telemetry = [event for event in session.event_log if event.type == "telemetry"]
    assert session.summary.status == "docked"
    detumbling = [e for e in telemetry if e.guidance_mode == "detumbling"]
    assert detumbling and min(e.range_m for e in detumbling) > 100
    final_approach = [e for e in telemetry if e.guidance_mode == "final_port_approach"]
    assert final_approach
    assert all(
        e.approach_gate["alignment_ready"] and e.approach_gate["inside_port_corridor"]
        for e in final_approach
    )
    assert min(e.range_m for e in telemetry if not e.approach_gate["alignment_ready"]) >= 4.9
    assert any(
        np.all(np.abs(e.command_force_n or [0, 0, 0]) > 0.01)
        and np.linalg.norm(e.command_torque_nm or [0, 0, 0]) > 0.01
        for e in telemetry
        if e.guidance_mode == "aligning_at_standoff"
    )
    final = telemetry[-1]
    assert final.range_m <= 0.02 and final.capture["eligible"]
    assert final.propellant_used_kg > 1
    assert final.propellant_remaining_kg + final.propellant_used_kg == pytest.approx(25)
    assert final.mass_kg == pytest.approx(500 - final.propellant_used_kg)
    assert final.fuel_pct < 90


def test_capture_waits_for_stable_alignment_and_correct_port_side():
    runner = SimulationRunner(Session("capture-stability"), make_request())
    state = RigidBodyState(position=np.array([0.01, 0, 0]))
    assert not runner._capture(state)["eligible"]
    runner._ports_stable, runner._alignment_stable_s = True, 1
    assert runner._capture(state)["eligible"]
    state.position[0] = -0.01
    assert not runner._capture(state)["eligible"]
    runner.request.config.alignment_stable_time_s = 0
    runner._ports_stable = False
    assert not runner._alignment_ready()


def test_standoff_follows_primary_port_orientation():
    request = make_request()
    request.primary.orientation_quat = [np.cos(np.pi / 4), 0, 0, np.sin(np.pi / 4)]
    runner = SimulationRunner(Session("rotated-port-axis"), request)
    state = RigidBodyState(position=np.array([20.0, 3.0, 2.0]))
    goal = LlmSubgoal(
        target_position_m=[0, 0, 0], target_velocity_mps=[-1, 0, 0], closing_speed_mps=1
    )
    result = runner._continuous_approach(goal, state)
    assert np.allclose(result.target_position_m, [0, 5, 0])
    runner._ports_stable, runner._alignment_stable_s = True, 1
    state.position = np.array([0.0, 5.0, 0.0])
    assert np.allclose(runner._continuous_approach(goal, state).target_position_m, [0, 0, 0])
