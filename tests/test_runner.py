"""End-to-end runner tests: full simulation runs to terminal events."""

from __future__ import annotations

import numpy as np
import pytest
from conftest import make_request

from app.schemas.docking import AnomalyConfig, AnomalyType, FailureReason, StopReason
from app.schemas.events import (
    AnomalyEvent,
    DockedEvent,
    FailedEvent,
    LlmDecisionEvent,
    TelemetryEvent,
)
from app.sessions.store import Session
from app.simulation.runner import SimulationRunner


async def _run(req, session_id: str = "test") -> Session:
    session = Session(session_id=session_id)
    runner = SimulationRunner(session=session, request=req)
    await runner.run()
    return session


async def test_heuristic_lqr_docks_from_50m():
    session = await _run(make_request(position=(50.0, 0.0, 0.0), max_steps=400))
    summary = session.summary
    assert summary is not None
    assert summary.status == "docked"
    assert summary.stop_reason is StopReason.DOCKED
    assert summary.steps_completed < 400
    final = summary.final_secondary
    assert final is not None
    assert np.linalg.norm(final.position_m) <= 0.02
    assert np.linalg.norm(final.velocity_mps) <= 0.005
    assert summary.metrics.total_llm_calls > 0
    # Every event type we expect shows up in the log.
    types = {e.type for e in session.event_log}
    assert "llm_decision" in types
    assert "telemetry" in types
    assert "docked" in types
    assert isinstance(session.event_log[-1], DockedEvent)
    # The wire envelope: every event is self-describing for the frontend.
    assert all(e.schema_version == "1.0" for e in session.event_log)
    assert all(e.session_id == "test" for e in session.event_log)
    telemetry = [e for e in session.event_log if isinstance(e, TelemetryEvent)]
    assert telemetry
    assert telemetry[0].primary.orientation_quat == [1.0, 0.0, 0.0, 0.0]
    assert telemetry[-1].metrics_so_far.delta_v_mps > 0.0


async def test_heuristic_pid_docks_from_50m():
    session = await _run(make_request(position=(50.0, 0.0, 0.0), max_steps=400, controller="pid"))
    assert session.summary.status == "docked"


async def test_llm_disabled_docks_with_static_homing():
    session = await _run(make_request(position=(30.0, 0.0, 0.0), max_steps=400, llm_enabled=False))
    summary = session.summary
    assert summary.status == "docked"
    assert summary.metrics.total_llm_calls == 0
    assert not any(isinstance(e, LlmDecisionEvent) for e in session.event_log)


async def test_abort_anomaly_holds_and_times_out():
    session = await _run(
        make_request(
            position=(50.0, 0.0, 0.0),
            max_steps=150,
            anomalies=[
                AnomalyConfig(type=AnomalyType.PRIORITY_CHANGE, step=10, priority_change="abort")
            ],
        )
    )
    summary = session.summary
    assert summary.status == "failed"
    assert summary.stop_reason is StopReason.FAILED
    assert summary.failure_reason is FailureReason.MAX_STEPS_EXCEEDED
    # The run stopped well short of the port.
    assert np.linalg.norm(summary.final_secondary.position_m) > 5.0
    assert any(isinstance(e, AnomalyEvent) for e in session.event_log)


async def test_divergence_guard_fails_run():
    """max_range_m is a hard bound: exceed it and the run fails DIVERGED."""
    session = await _run(make_request(position=(200.0, 0.0, 0.0), max_steps=600, max_range_m=100.0))
    summary = session.summary
    assert summary.status == "failed"
    assert summary.stop_reason is StopReason.FAILED
    assert summary.failure_reason is FailureReason.DIVERGED
    assert isinstance(session.event_log[-1], FailedEvent)


async def test_omega_guard_fails_tumbling_run():
    """A tumbling chaser (|ω| > max_omega_radps) fails DIVERGED, not crash."""
    request = make_request(max_steps=600, max_omega_radps=0.05)
    # Bypass request validation to exercise the runtime guard for an evolved state.
    request.secondary.angular_velocity_radps = [0.3, 0.0, 0.0]
    session = await _run(request)
    summary = session.summary
    assert summary.status == "failed"
    assert summary.failure_reason is FailureReason.DIVERGED
    assert "rotation rate 0.300 rad/s" in summary.error
    assert "0.05 rad/s tumble limit" in summary.error
    assert summary.metrics.total_llm_calls == 0
    assert not any(e.type == "planning" for e in session.event_log)


async def test_fuel_exhaustion_fails_run():
    request = make_request(position=(800.0, 0.0, 0.0), max_steps=400)
    request.secondary.propellant_capacity_kg = 0.01
    session = await _run(request)
    summary = session.summary
    assert summary.status == "failed"
    assert summary.failure_reason is FailureReason.FUEL_EXHAUSTED
    assert isinstance(session.event_log[-1], FailedEvent)


async def test_max_time_exceeded():
    session = await _run(
        make_request(
            position=(1000.0, 0.0, 0.0),
            max_steps=1000,
            max_time_s=100.0,
        )
    )
    summary = session.summary
    assert summary.status == "failed"
    assert summary.failure_reason is FailureReason.MAX_TIME_EXCEEDED


@pytest.mark.parametrize("max_range", [1000, None])
async def test_one_kilometre_guard_also_applies_when_range_option_is_omitted(max_range):
    session = await _run(
        make_request(
            position=(999.99, 0, 0),
            velocity=(0.1, 0, 0),
            llm_enabled=False,
            max_range_m=max_range,
            max_thrust_n=2.5,
            max_acceleration_mps2=0.005,
            max_steps=10,
        )
    )
    assert session.summary.failure_reason is FailureReason.DIVERGED
    assert session.summary.steps_completed == 1


async def test_session_finished_event_set():
    session = await _run(make_request(max_steps=200))
    assert session.finished.is_set()


async def test_metrics_accumulate_sane_values():
    session = await _run(make_request(position=(50.0, 0.0, 0.0), max_steps=400))
    m = session.summary.metrics
    assert m.delta_v_mps > 0.0
    assert m.ise > 0.0
    # Per-axis saturation is 50 N; the vector norm can reach 50*sqrt(3).
    assert m.max_commanded_thrust_n <= 50.0 * np.sqrt(3) + 1e-9
    assert m.anomaly_events_count == 0


@pytest.mark.parametrize("initial", [(50.0, 0.0, 0.0), (0.0, 50.0, 0.0), (0.0, 0.0, 50.0)])
async def test_docks_from_all_axes(initial):
    session = await _run(make_request(position=initial, max_steps=400))
    assert session.summary.status == "docked"
