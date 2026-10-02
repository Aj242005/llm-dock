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
        dock_velocity_tol_mps=0.005,
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
        speed <= 0.019 + 1e-6
        for event, speed in zip(telemetry, speeds, strict=True)
        if event.range_m <= 5
    )
    assert telemetry[-1].range_m <= 0.02
    assert telemetry[-1].sim_time_s >= 987.5


class WaitingPlanner(ReasoningAgent):
    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False
        self.calls = 0
        self.snapshots = []

    async def reason(self, input_data):
        self.calls += 1
        self.snapshots.append(input_data.model_copy(deep=True))
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        return HeuristicAgent().plan(input_data), "test_planner"


async def wait_until(condition):
    async with asyncio.timeout(2):
        while not condition():
            await asyncio.sleep(0.005)


async def test_planning_keeps_physics_running_and_stop_cancels_the_call():
    planner = WaitingPlanner()
    session = Session("planning-stop")
    request = make_request(
        velocity=(-0.08, 0, 0),
        step_interval_s=0.05,
        playback_speed=5,
        max_thrust_n=2.5,
        max_acceleration_mps2=0.005,
    )
    request.primary.velocity_mps = [0.01, 0, 0]
    task = asyncio.create_task(SimulationRunner(session, request, agent=planner).run())
    await asyncio.wait_for(planner.started.wait(), timeout=1)
    await wait_until(lambda: session.summary.steps_completed >= 3)
    telemetry = [e for e in session.event_log if e.type == "telemetry"]
    assert telemetry[-1].sim_time_s > 0
    assert telemetry[-1].range_m < telemetry[0].range_m
    assert telemetry[-1].primary.position_m[0] > 0
    assert telemetry[-1].planning_pending
    assert telemetry[-1].guidance_mode == "coasting"
    assert planner.snapshots[0].position_m == [50, 0, 0]
    session.cancel_requested = True
    await asyncio.wait_for(task, timeout=0.5)
    assert session.summary.failure_reason.value == "cancelled"
    assert session.summary.steps_completed >= 3
    assert planner.cancelled


async def test_pending_requests_are_coalesced_and_expired_response_is_discarded():
    planner = WaitingPlanner()
    session = Session("expired-plan")
    request = make_request(
        velocity=(-0.1, 0, 0),
        step_interval_s=0.05,
        playback_speed=5,
        llm_cadence_steps=1,
        planner_reserve_s=0,
    )
    task = asyncio.create_task(SimulationRunner(session, request, agent=planner).run())
    await planner.started.wait()
    await wait_until(lambda: session.summary.steps_completed >= 4)
    assert planner.calls == 1
    planner.release.set()
    await wait_until(lambda: any(e.type == "llm_decision" for e in session.event_log))
    session.cancel_requested = True
    await task
    decision = next(e for e in session.event_log if e.type == "llm_decision")
    assert not decision.applied
    assert decision.plan_age_s > 0.05
    assert decision.snapshot_sim_time_s == 0
    assert decision.sim_time_s > decision.snapshot_sim_time_s
    assert any("discarded" in note for note in decision.safety_notes)
    assert decision.recovery_subgoal is not None
    assert np.linalg.norm(decision.recovery_subgoal.target_position_m) < 50
    assert np.dot(decision.recovery_subgoal.target_velocity_mps, [50, 0, 0]) < 0


async def test_delayed_plan_uses_current_near_port_speed_envelope():
    planner = WaitingPlanner()
    session = Session("delayed-approach")
    request = make_request(
        position=(5.01, 0, 0),
        velocity=(-0.1, 0, 0),
        step_interval_s=0.05,
        playback_speed=5,
        llm_cadence_steps=100,
        near_port_speed_mps=0.02,
        dock_velocity_tol_mps=0.005,
    )
    task = asyncio.create_task(SimulationRunner(session, request, agent=planner).run())
    await planner.started.wait()
    await wait_until(lambda: session.summary.steps_completed >= 5)
    planner.release.set()
    await wait_until(lambda: any(e.type == "llm_decision" for e in session.event_log))
    session.cancel_requested = True
    await task
    decision = next(e for e in session.event_log if e.type == "llm_decision")
    assert decision.applied
    assert decision.plan_age_s > 0
    assert np.linalg.norm(decision.subgoal.target_velocity_mps) <= 0.019 + 1e-6
    # A delayed response cannot bypass the stable-alignment interval.
    assert decision.subgoal.target_position_m == [5, 0, 0]


async def test_fault_brakes_before_provider_returns_and_invalidates_old_context():
    planner = WaitingPlanner()
    session = Session("abort-pending")
    request = make_request(
        velocity=(-0.1, 0, 0),
        step_interval_s=0.05,
        playback_speed=5,
        anomalies=[{"type": "priority_change", "step": 2, "priority_change": "abort"}],
    )
    task = asyncio.create_task(SimulationRunner(session, request, agent=planner).run())
    await planner.started.wait()
    await wait_until(lambda: session.summary.steps_completed >= 4)
    telemetry = [e for e in session.event_log if e.type == "telemetry"]
    assert telemetry[-1].guidance_mode == "abort_braking"
    assert telemetry[-1].command_force_n[0] > 0
    planner.release.set()
    await wait_until(lambda: any(e.type == "llm_decision" for e in session.event_log))
    session.cancel_requested = True
    await task
    assert not next(e for e in session.event_log if e.type == "llm_decision").applied


async def test_terminal_time_budget_cancels_pending_provider_without_waiting():
    planner = WaitingPlanner()
    session = Session("planning-budget")
    request = make_request(step_interval_s=0.1, playback_speed=10, max_time_s=0.3)
    await asyncio.wait_for(SimulationRunner(session, request, agent=planner).run(), timeout=1)
    assert session.summary.failure_reason.value == "max_time_exceeded"
    assert planner.cancelled


async def test_last_accepted_maneuver_continues_during_the_next_provider_call():
    class SecondCallWaits(WaitingPlanner):
        async def reason(self, input_data):
            if not self.snapshots:
                self.snapshots.append(input_data)
                self.calls = 1
                return HeuristicAgent().plan(input_data), "test_planner"
            return await super().reason(input_data)

    planner = SecondCallWaits()
    session = Session("continue-active-plan")
    request = make_request(
        step_interval_s=0.05,
        playback_speed=5,
        llm_cadence_steps=3,
        max_thrust_n=2.5,
        max_acceleration_mps2=0.005,
    )
    task = asyncio.create_task(SimulationRunner(session, request, agent=planner).run())
    await asyncio.wait_for(planner.started.wait(), timeout=1)
    await wait_until(lambda: session.summary.steps_completed >= 6)
    telemetry = [e for e in session.event_log if e.type == "telemetry"]
    assert telemetry[-1].planning_pending
    assert telemetry[-1].guidance_mode == "aligning_at_standoff"
    assert telemetry[-1].range_m < telemetry[0].range_m
    assert np.linalg.norm(telemetry[-1].command_force_n) > 0
    assert session.summary.metrics.total_llm_calls == 1
    session.cancel_requested = True
    await task
    assert planner.cancelled


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
        dock_velocity_tol_mps=0.005,
        near_port_speed_mps=0.02,
    )
    session = Session("learned-final-approach")
    await SimulationRunner(session, request).run()
    assert session.summary.status == "docked"
    decision = next(e for e in session.event_log if e.type == "llm_decision")
    assert decision.subgoal.target_position_m == [5, 0, 0]
    assert any(e.guidance_mode == "final_port_approach" for e in session.event_log if e.type == "telemetry")
    # Back out to stand-off while stability accumulates; then close axially.
    assert decision.subgoal.target_velocity_mps == [0.019, 0, 0]
    assert decision.safety_notes
