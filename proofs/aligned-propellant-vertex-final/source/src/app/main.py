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
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

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
        model=(
            settings.llm_model_vertex
            if settings.mode == "vertex"
            else settings.llm_model
            if settings.mode != "heuristic"
            else "heuristic (no network)"
        ),
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


@app.get("/api", include_in_schema=False)
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


project_root = Path(__file__).resolve().parents[2]
if not (project_root / "frontend").exists():
    project_root = Path.cwd()
frontend = project_root / "frontend" / "dist"
proofs = project_root / "proofs"
if proofs.is_dir():
    app.mount("/proofs/files", StaticFiles(directory=proofs), name="proof_files")


@app.get("/proofs/", include_in_schema=False)
async def proof_index():
    from fastapi.responses import HTMLResponse

    files = [
        p
        for p in proofs.rglob("*")
        if p.is_file() and p.suffix in {".json", ".csv", ".png", ".md", ".txt"}
    ]
    from html import escape

    links = "".join(
        f'<li><a href="/proofs/files/{p.relative_to(proofs).as_posix()}">{escape(p.relative_to(proofs).as_posix())}</a></li>'
        for p in files
    )
    return HTMLResponse(
        '<html lang="en"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Docking evidence</title>'
        '<body style="font-family:system-ui;max-width:900px;margin:40px auto;padding:20px"><a href="/">Dashboard</a>'
        "<h1>Training & evaluation evidence</h1><p>Measured artifacts, parameters, and hashes from actual runs.</p><ul>"
        + links
        + "</ul></body></html>"
    )


if frontend.is_dir():
    app.mount("/", StaticFiles(directory=frontend, html=True), name="dashboard")
else:
    app.add_api_route("/", root, include_in_schema=False)
