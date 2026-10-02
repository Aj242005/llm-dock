"""API routes for the docking simulator.

Session lifecycle
-----------------
``POST /api/v1/docking/simulate`` validates the request, creates a session,
and starts the simulation as a background task; it returns 202 immediately
with the session id and the stream/summary URLs. The simulation then pushes
events into the session's queue, which the SSE endpoint streams to the client
until the terminal ``docked``/``failed`` event is emitted.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.schemas.docking import ControllerType, SessionSummary, SimulateRequest, SimulateResponse
from app.sessions.store import InMemorySessionStore, Session
from app.simulation.runner import SimulationRunner

logger = logging.getLogger("llm_docking.api")

router = APIRouter(prefix="/api/v1", tags=["docking"])

# Single in-memory store for the process. Swappable for a Redis-backed store
# behind the same SessionStore interface.
store = InMemorySessionStore(queue_size=get_settings().event_buffer_size)

# How long the SSE endpoint waits for the next event before re-checking
# whether the session has finished (keeps the loop responsive to termination).
_SSE_POLL_TIMEOUT_S = 0.5


@router.post(
    "/docking/simulate",
    status_code=202,
    response_model=SimulateResponse,
    summary="Start a docking simulation",
)
async def start_simulation(request: Request, body: SimulateRequest) -> SimulateResponse:
    _validate_controller_ready(body)
    session = await store.create()
    session.stream_pacing_s = body.config.stream_pacing_s
    runner = SimulationRunner(session=session, request=body)
    session.task = asyncio.create_task(runner.run())
    logger.info("simulation_started", extra={"session_id": session.session_id})
    return SimulateResponse(
        session_id=session.session_id,
        stream_url=f"/api/v1/docking/sessions/{session.session_id}/stream",
        summary_url=f"/api/v1/docking/sessions/{session.session_id}",
    )


@router.get(
    "/docking/sessions/{session_id}/stream",
    summary="SSE stream of simulation events",
)
async def stream_events(session_id: str, after: int = 0, last_event_id: str | None = Header(default=None)) -> EventSourceResponse:
    session = await _get_session(session_id)
    try:
        cursor = int(last_event_id) if last_event_id else after
    except ValueError:
        raise HTTPException(status_code=400, detail="Last-Event-ID must be an integer") from None
    if cursor < 0 or cursor > len(session.event_log):
        raise HTTPException(status_code=400, detail="Event cursor is outside this session")

    async def event_generator() -> AsyncGenerator[dict, None]:
        index = cursor
        while True:
            while index < len(session.event_log):
                event = session.event_log[index]
                index += 1
                yield {"id": str(event.event_id), "event": event.type, "data": event.model_dump_json()}
            if session.finished.is_set():
                break
            await asyncio.sleep(0.05)
        logger.info("stream_closed", extra={"session_id": session_id})

    return EventSourceResponse(event_generator())


@router.get(
    "/docking/sessions/{session_id}",
    response_model=SessionSummary,
    summary="Poll the session summary",
)
async def get_summary(session_id: str) -> SessionSummary:
    session = await _get_session(session_id)
    if session.summary is None:
        raise HTTPException(status_code=404, detail="Session has no summary yet")
    return session.summary


@router.get(
    "/docking/sessions/{session_id}/events",
    summary="Dump the full ordered event log",
)
async def get_events(session_id: str) -> list[dict]:
    session = await _get_session(session_id)
    return [e.model_dump(mode="json") for e in session.event_log]


@router.get("/health", summary="Liveness probe")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@router.get("/capabilities")
async def capabilities():
    from app.llm.reasoning_agent import provider_has_key
    settings = get_settings()
    return {"providers": {p: provider_has_key(p) for p in ["heuristic", "openai", "openrouter", "groq", "anthropic"]},
            "default_provider": settings.mode,
            "rl_available": bool(settings.rl_model_path and settings.rl_normalize_path and
                                 os.path.isfile(settings.rl_model_path) and os.path.isfile(settings.rl_normalize_path)),
            "capture_range_m": 1.25}


@router.post("/docking/sessions/{session_id}/cancel")
async def cancel_session(session_id: str):
    session = await _get_session(session_id)
    if session.finished.is_set():
        raise HTTPException(status_code=409, detail="Session has already finished")
    session.cancel_requested = True
    return {"status": "cancellation_requested"}


@router.post("/docking/sessions/{session_id}/dock")
async def request_docking(session_id: str):
    session = await _get_session(session_id)
    if session.finished.is_set() or not session.capture.get("eligible"):
        raise HTTPException(status_code=409, detail={"message": "Capture gate is not satisfied", "capture": session.capture})
    session.dock_requested = True
    return {"status": "capture_requested", "capture": session.capture}


@router.get("/docking/sessions/{session_id}/export")
async def export_session(session_id: str):
    session = await _get_session(session_id)
    return JSONResponse({"schema_version": "1.0", "summary": session.summary.model_dump(mode="json") if session.summary else None,
                         "request": getattr(session, "request_data", None),
                         "events": [e.model_dump(mode="json") for e in session.event_log]},
                        headers={"Content-Disposition": f'attachment; filename="docking-{session_id}.json"'})


async def _get_session(session_id: str) -> Session:
    session = await store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail=f"Unknown session: {session_id}")
    return session


def _validate_controller_ready(body: SimulateRequest) -> None:
    """Fail fast (400) when the requested run needs RL artifacts it hasn't got.

    Both ``controller="rl"`` and ``rl_advisor_enabled=True`` require the
    trained policy + VecNormalize stats (process-wide settings).
    """
    needs_rl = body.config.controller is ControllerType.RL or body.config.rl_advisor_enabled
    if not needs_rl:
        return
    settings = get_settings()
    missing = [
        name for name, path in (
            ("LLM_DOCKING_RL_MODEL_PATH", settings.rl_model_path),
            ("LLM_DOCKING_RL_NORMALIZE_PATH", settings.rl_normalize_path),
        ) if not path or not os.path.isfile(path)
    ]
    if missing:
        reason = (
            "controller='rl'" if body.config.controller is ControllerType.RL
            else "rl_advisor_enabled=True"
        )
        raise HTTPException(
            status_code=400,
            detail=(
                f"{reason} requires a trained policy: set "
                + " and ".join(missing)
                + " (train with `python -m app.simulation.rl.train_ppo`)"
            ),
        )
