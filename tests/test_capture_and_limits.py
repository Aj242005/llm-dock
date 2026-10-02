"""The capture boundary, replay, cancellation, and command limits are independent of LLMs."""

import asyncio

import httpx
import numpy as np
import pytest
from conftest import make_request
from pydantic import ValidationError

from app.main import app
from app.schemas.docking import MotionLimits, SatelliteState, SimulationConfig
from app.sessions.store import Session
from app.simulation.dynamics import RigidBodyState
from app.simulation.runner import SimulationRunner
from app.simulation.safety import capture_checks


def test_capture_requires_both_ranges_and_all_checks():
    state = RigidBodyState(position=np.array([0.02, 0.0, 0.0]))
    assert capture_checks(state)["eligible"]
    state.position[0] = 0.020001
    assert not capture_checks(state)["eligible"]
    state.position[0] = 0.015
    assert not capture_checks(state, secondary_radius=0.01)["eligible"]
    state.velocity[0] = 0.005001
    assert not capture_checks(state)["eligible"]


def test_configuration_rejects_nonfinite_and_invalid_limits():
    with pytest.raises(ValidationError):
        SatelliteState(position_m=[float("nan"), 0, 0])
    with pytest.raises(ValidationError):
        SimulationConfig(dock_position_tol_m=1.26)
    with pytest.raises(ValidationError):
        MotionLimits(min_speed_mps=3, max_speed_mps=2)
    with pytest.raises(ValidationError):
        make_request(velocity=(3.0, 0.0, 0.0))


async def test_motion_limits_are_enforced_on_applied_commands():
    request = make_request(position=(15.0, 8.0, 5.0), max_steps=150)
    request.secondary.motion_limits = MotionLimits(
        max_speed_mps=0.25, max_horizontal_speed_mps=0.2, max_vertical_speed_mps=0.1
    )
    session = Session("limited")
    await SimulationRunner(session, request).run()
    telemetry = [e for e in session.event_log if e.type == "telemetry"]
    assert telemetry
    for event in telemetry:
        velocity = event.secondary_velocity_mps
        assert np.linalg.norm(velocity) <= 0.25 + 1e-6
        assert np.linalg.norm(velocity[:2]) <= 0.2 + 1e-6
        assert abs(velocity[2]) <= 0.1 + 1e-6
    assert any(e.command_limited for e in telemetry)


async def test_nonzero_primary_origin_is_respected():
    request = make_request(position=(51.0, 10.0, 3.0), max_steps=600)
    request.primary.position_m = [50.0, 10.0, 3.0]
    session = Session("origin")
    await SimulationRunner(session, request).run()
    assert session.event_log[0].position_m == [1.0, 0.0, 0.0]
    assert session.summary.status == "docked"


async def test_primary_angular_rate_changes_telemetry_orientation():
    request = make_request(position=(20.0, 0.0, 0.0), max_steps=3)
    request.primary.angular_velocity_radps = [0.0, 0.0, 0.01]
    session = Session("rotating-primary")
    await SimulationRunner(session, request).run()
    telemetry = [e for e in session.event_log if e.type == "telemetry"]
    assert telemetry[0].primary.orientation_quat == [1.0, 0.0, 0.0, 0.0]
    assert not np.allclose(telemetry[-1].primary.orientation_quat, [1.0, 0.0, 0.0, 0.0])


async def test_abort_at_capture_position_cannot_auto_dock():
    from app.schemas.docking import AnomalyConfig

    request = make_request(
        position=(1.0, 0.0, 0.0),
        max_steps=5,
        anomalies=[AnomalyConfig(type="priority_change", step=0, priority_change="abort")],
    )
    session = Session("abort-capture")
    await SimulationRunner(session, request).run()
    assert session.summary.status == "failed"


async def test_sse_replays_for_each_viewer_and_resumes_by_id():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/api/v1/docking/simulate",
            json=make_request(position=(1.0, 0.0, 0.0)).model_dump(mode="json"),
        )
        urls = response.json()
        first = await client.get(urls["stream_url"])
        second = await client.get(urls["stream_url"])
        assert first.text == second.text
        assert "id: 1" in first.text and "event: docked" in first.text
        resumed = await client.get(urls["stream_url"], headers={"Last-Event-ID": "1"})
        assert "id: 1\r\n" not in resumed.text
        assert "event: docked" in resumed.text


async def test_manual_capture_rechecks_and_stop_finishes():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        request = make_request(position=(0.02, 0.0, 0.0), auto_dock=False, stream_pacing_s=0.01)
        urls = (
            await client.post("/api/v1/docking/simulate", json=request.model_dump(mode="json"))
        ).json()
        await asyncio.sleep(0.03)
        accepted = await client.post(urls["summary_url"] + "/dock")
        assert accepted.status_code == 200
        events = await client.get(urls["stream_url"])
        assert "event: docked" in events.text
        request = make_request(position=(50.0, 0.0, 0.0), stream_pacing_s=0.01)
        urls = (
            await client.post("/api/v1/docking/simulate", json=request.model_dump(mode="json"))
        ).json()
        assert (await client.post(urls["summary_url"] + "/dock")).status_code == 409
        await client.post(urls["summary_url"] + "/cancel")
        events = await client.get(urls["stream_url"])
        assert '"failure_reason":"cancelled"' in events.text
