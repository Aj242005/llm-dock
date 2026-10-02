"""Verify conservative motion and responsive planning without a provider call."""

import asyncio

import numpy as np
from conftest import make_request

from app.llm.reasoning_agent import HeuristicAgent, ReasoningAgent
from app.schemas.docking import MotionLimits
from app.sessions.store import Session
from app.simulation.runner import SimulationRunner


async def test_100m_approach_respects_thrust_speed_and_acceleration():
    request = make_request(
        position=(100, 0, 0),
        max_steps=6000,
        step_interval_s=0.5,
        llm_cadence_steps=60,
        max_thrust_n=2.5,
        max_acceleration_mps2=0.005,
        near_port_speed_mps=0.02,
        dock_velocity_tol_mps=0.02,
        fuel_consumption_rate_pct_per_s=0.001,
    )
    request.secondary.motion_limits = MotionLimits(
        max_speed_mps=0.1,
        max_horizontal_speed_mps=0.1,
        max_vertical_speed_mps=0.05,
    )
    session = Session("slow-approach")
    await SimulationRunner(session, request).run()
    assert session.summary.status == "docked"
    telemetry = [event for event in session.event_log if event.type == "telemetry"]
    velocities = np.asarray([event.secondary_velocity_mps for event in telemetry])
    speeds = np.linalg.norm(velocities, axis=1)
    assert max(speeds) <= 0.1 + 1e-6
    assert max(np.linalg.norm(np.diff(velocities, axis=0) / 0.5, axis=1)) <= 0.005 + 1e-6
    assert session.summary.metrics.max_commanded_thrust_n <= 2.5 + 1e-6
    assert all(
        speed <= 0.02 + 1e-6
        for event, speed in zip(telemetry, speeds, strict=True)
        if event.range_m <= 5
    )
    assert telemetry[-1].range_m <= 1.25
    assert telemetry[-1].sim_time_s >= 987.5


class WaitingPlanner(ReasoningAgent):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def reason(self, input_data):
        self.started.set()
        await self.release.wait()
        return HeuristicAgent().plan(input_data), "test_planner"


async def test_planning_holds_clock_and_stop_cancels_the_call():
    planner = WaitingPlanner()
    session = Session("planning-stop")
    task = asyncio.create_task(SimulationRunner(session, make_request(), agent=planner).run())
    await asyncio.wait_for(planner.started.wait(), timeout=1)
    await asyncio.sleep(0.05)
    assert [event.sim_time_s for event in session.event_log] == [0, 0]
    assert session.event_log[-1].type == "planning"
    session.cancel_requested = True
    await asyncio.wait_for(task, timeout=0.5)
    assert session.summary.failure_reason.value == "cancelled"
    assert session.summary.steps_completed == 0


async def test_real_time_pacing_yields_and_remains_interruptible():
    session = Session("real-time-stop")
    request = make_request(playback_speed=1, step_interval_s=0.5, llm_enabled=False)
    task = asyncio.create_task(SimulationRunner(session, request).run())
    await asyncio.sleep(0.15)
    assert len([event for event in session.event_log if event.type == "telemetry"]) == 2
    session.cancel_requested = True
    await asyncio.wait_for(task, timeout=0.5)
    assert session.summary.steps_completed == 1


async def test_learned_lateral_advice_is_aligned_and_slowed_for_capture(monkeypatch):
    from app.schemas.events import RlAdvisorSuggestion

    proposal = RlAdvisorSuggestion(
        suggested_position_m=[1.2, 0.5, 0],
        suggested_velocity_mps=[-0.04, 0.03, 0],
        closing_speed_mps=0.04,
        lookahead_s=4,
    )
    monkeypatch.setattr(SimulationRunner, "_advisor_suggestion", lambda *args: proposal)
    request = make_request(
        position=(4, 0, 0),
        max_steps=600,
        step_interval_s=0.5,
        llm_cadence_steps=60,
        rl_advisor_enabled=True,
        max_thrust_n=2.5,
        max_acceleration_mps2=0.005,
        dock_velocity_tol_mps=0.02,
        near_port_speed_mps=0.02,
    )
    session = Session("learned-final-approach")
    await SimulationRunner(session, request).run()
    assert session.summary.status == "docked"
    decision = next(e for e in session.event_log if e.type == "llm_decision")
    assert decision.subgoal.target_position_m == [0, 0, 0]
    assert decision.subgoal.target_velocity_mps == [-0.019, 0, 0]
    assert decision.safety_notes
