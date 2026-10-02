"""FastAPI application entrypoint.

Run locally with::

    uvicorn app.main:app --reload

or via Docker (see Dockerfile / docker-compose.yml).
"""

from __future__ import annotations

import logging
import sys
import time
import uuid
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import __version__
from app.api.routes import router
from app.config import get_settings

# ---------------------------------------------------------------------------
# Logging: stdlib plumbing + structlog rendering
# ---------------------------------------------------------------------------


def _configure_logging() -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=logging.INFO,
        force=True,
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


_configure_logging()
log = structlog.get_logger("llm_docking.main")

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info(
        "startup",
        mode=settings.mode,
        model=settings.llm_model if settings.mode != "heuristic" else "heuristic (no network)",
        controller=settings.sim_default_controller,
    )
    yield
    log.info("shutdown")


app = FastAPI(
    title="LLM Docking API",
    description=(
        "Backend for an LLM-augmented autonomous satellite rendezvous-and-docking "
        "agent: the reasoning layer re-plans structured sub-goals, low-level "
        "PID/LQR controllers track them, and every step streams over SSE."
    ),
    version=__version__,
    lifespan=lifespan,
)

app.include_router(router)


@app.middleware("http")
async def request_context_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    structlog.contextvars.bind_contextvars(request_id=request_id)
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000.0
    structlog.contextvars.clear_contextvars()
    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


@app.get("/", include_in_schema=False)
async def root() -> JSONResponse:
    return JSONResponse(
        {
            "service": "llm-docking",
            "version": __version__,
            "mode": settings.mode,
            "docs": "/docs",
            "health": "/api/v1/health",
            "simulate": "POST /api/v1/docking/simulate",
        }
    )
