"""HTTP API tests: session lifecycle, SSE stream, summary polling, event dump."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from app.main import app

BASE = "http://test"

PAYLOAD = {
    "primary": {"orbital_elements": {"semi_major_axis_m": 6_878_000.0}},
    "secondary": {
        "position_m": [50.0, 0.0, 0.0],
        "orbital_elements": {"semi_major_axis_m": 6_878_000.0},
    },
    "config": {"max_steps": 300},
}


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url=BASE) as c:
        yield c


def _parse_sse(text: str) -> list[dict]:
    """Parse an SSE body (CRLF or LF frames) into the JSON payloads."""
    events = []
    for frame in text.replace("\r\n", "\n").split("\n\n"):
        data_lines = [
            line[len("data: ") :] for line in frame.split("\n") if line.startswith("data: ")
        ]
        if data_lines:
            events.append(json.loads("\n".join(data_lines)))
    return events


async def test_health(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


async def test_root_info(client):
    resp = await client.get("/api")
    body = resp.json()
    assert body["service"] == "llm-docking"
    assert body["simulate"] == "POST /api/v1/docking/simulate"


async def test_start_simulation_returns_202(client):
    resp = await client.post("/api/v1/docking/simulate", json=PAYLOAD)
    assert resp.status_code == 202
    body = resp.json()
    assert body["session_id"]
    assert body["stream_url"].endswith("/stream")
    assert "/api/v1/docking/sessions/" in body["summary_url"]


async def test_validation_error_is_422(client):
    bad = {
        "primary": {"orbital_elements": {"semi_major_axis_m": 6_878_000.0}},
        "secondary": {"position_m": [1.0, 0.0, 0.0]},
        "config": {"controller": "bogus"},
    }
    resp = await client.post("/api/v1/docking/simulate", json=bad)
    assert resp.status_code == 422


async def test_summary_polls_to_docked(client):
    body = (await client.post("/api/v1/docking/simulate", json=PAYLOAD)).json()
    session_id = body["session_id"]

    summary = None
    for _ in range(200):
        resp = await client.get(f"/api/v1/docking/sessions/{session_id}")
        assert resp.status_code == 200
        summary = resp.json()
        if summary["status"] != "running":
            break
        await asyncio.sleep(0.02)
    assert summary is not None
    assert summary["status"] == "docked"
    assert summary["stop_reason"] == "docked"
    assert summary["steps_completed"] > 0
    assert summary["controller"] == "lqr"
    assert summary["metrics"]["total_llm_calls"] > 0


async def test_unknown_session_404(client):
    resp = await client.get("/api/v1/docking/sessions/does-not-exist")
    assert resp.status_code == 404


async def test_rl_advisor_requires_policy(client, monkeypatch):
    """rl_advisor_enabled=True without trained artifacts -> 400."""
    from app.config import get_settings

    # Empty-string process env (not delenv) — the on-disk .env may configure
    # paths that exist, and pydantic falls back to the dotenv file otherwise.
    monkeypatch.setenv("LLM_DOCKING_RL_MODEL_PATH", "")
    monkeypatch.setenv("LLM_DOCKING_RL_NORMALIZE_PATH", "")
    get_settings.cache_clear()
    payload = json.loads(json.dumps(PAYLOAD))
    payload["config"]["rl_advisor_enabled"] = True
    resp = await client.post("/api/v1/docking/simulate", json=payload)
    assert resp.status_code == 400
    assert "rl_advisor_enabled" in resp.json()["detail"]
    get_settings.cache_clear()


async def test_sse_stream_ends_with_docked(client):
    body = (await client.post("/api/v1/docking/simulate", json=PAYLOAD)).json()
    session_id = body["session_id"]

    resp = await client.get(f"/api/v1/docking/sessions/{session_id}/stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    events = _parse_sse(resp.text)
    assert events, "stream should not be empty"
    assert events[-1]["type"] == "docked"
    types = {e["type"] for e in events}
    assert "telemetry" in types
    assert "llm_decision" in types
    # Monotonic step ordering.
    steps = [e.get("step", 0) for e in events]
    assert steps == sorted(steps)
    # Wire contract: every event is versioned and self-describing.
    assert all(e["schema_version"] == "1.0" for e in events)
    assert all(e["session_id"] == session_id for e in events)
    telemetry = [e for e in events if e["type"] == "telemetry"]
    assert telemetry
    assert "primary" in telemetry[0]
    assert telemetry[0]["primary"]["orientation_quat"] == [1.0, 0.0, 0.0, 0.0]
    assert "metrics_so_far" in telemetry[0]
    assert telemetry[-1]["metrics_so_far"]["delta_v_mps"] > 0.0


async def test_event_log_dump(client):
    body = (await client.post("/api/v1/docking/simulate", json=PAYLOAD)).json()
    session_id = body["session_id"]

    # Wait for completion.
    for _ in range(200):
        summary = (await client.get(f"/api/v1/docking/sessions/{session_id}")).json()
        if summary["status"] != "running":
            break
        await asyncio.sleep(0.02)

    resp = await client.get(f"/api/v1/docking/sessions/{session_id}/events")
    assert resp.status_code == 200
    events = resp.json()
    assert events, "event log should not be empty"
    assert events[-1]["type"] == "docked"
    # First event is the initial telemetry snapshot.
    assert events[0]["type"] == "telemetry"
    assert events[0]["step"] == 0
