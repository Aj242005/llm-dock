"""Six-axis approach and centimetre capture regression checks."""

import numpy as np
import pytest
from conftest import make_request
from pydantic import ValidationError

from app.schemas.docking import MotionLimits, SatelliteState, SimulationConfig
from app.schemas.events import LlmSubgoal
from app.sessions.store import Session
from app.simulation.controllers.base import ControlContext, build_controller
from app.simulation.dynamics import DEFAULT_INERTIA, RigidBodyState
from app.simulation.runner import SimulationRunner
from app.simulation.safety import capture_checks


async def test_100m_three_axis_translation_and_rotation_end_in_2cm_capture():
    request = make_request(
        position=(80, 48, 36),
        step_interval_s=0.2,
        max_steps=3000,
        max_thrust_n=50,
        max_acceleration_mps2=0.1,
        near_port_speed_mps=0.3,
        fuel_consumption_rate_pct_per_s=0.001,
        rl_advisor_enabled=False,
    )
    request.secondary.orientation_quat = [np.cos(np.pi / 8), 0, 0, np.sin(np.pi / 8)]
    request.secondary.motion_limits = MotionLimits(
        max_speed_mps=2, max_horizontal_speed_mps=2, max_vertical_speed_mps=2
    )
    session = Session("six-axis-precision")
    await SimulationRunner(session, request).run()
    telemetry = [e for e in session.event_log if e.type == "telemetry"]
    assert session.summary.status == "docked"
    assert telemetry[-1].range_m <= 0.02
    assert np.linalg.norm(telemetry[-1].velocity_mps) <= 0.005
    assert telemetry[-1].capture["eligible"]
    assert any(
        np.all(np.abs(e.command_force_n or [0, 0, 0]) > 0.01)
        and np.linalg.norm(e.command_torque_nm or [0, 0, 0]) > 0.01
        for e in telemetry
    )
    assert max(np.linalg.norm(e.velocity_mps) for e in telemetry) > 1
    assert telemetry[-1].sim_time_s < 180


@pytest.mark.parametrize("controller", ["pid", "lqr"])
def test_attitude_target_works_without_unwinding_equivalent_quaternions(controller):
    control = build_controller(controller, 500, DEFAULT_INERTIA, 0.001)
    q = [np.cos(np.pi / 8), 0, 0, np.sin(np.pi / 8)]
    state = RigidBodyState(position=np.array([10.0, 3.0, 2.0]), quat=np.array(q))
    goal = LlmSubgoal(
        target_position_m=[0, 0, 0],
        target_velocity_mps=[-1, 0, 0],
        closing_speed_mps=1,
        target_orientation_quat=(-np.array(q)).tolist(),
    )
    command = control.compute(state, goal, 0.2, ControlContext())
    assert np.linalg.norm(command.force_n) > 0
    assert np.linalg.norm(command.torque_nm) < 1e-6
    goal.target_orientation_quat = [1, 0, 0, 0]
    assert np.linalg.norm(control.compute(state, goal, 0.2, ControlContext()).torque_nm) > 0


def test_capture_limits_cannot_be_relaxed_past_three_centimetres():
    with pytest.raises(ValidationError):
        SimulationConfig(dock_position_tol_m=0.03001)
    with pytest.raises(ValidationError):
        SatelliteState(capture_radius_m=0.03001)
    state = RigidBodyState(position=np.array([0.031, 0.0, 0.0]))
    assert not capture_checks(state, position_tol=10, primary_radius=10, secondary_radius=10)[
        "eligible"
    ]
