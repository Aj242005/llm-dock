"""Shared fixtures for the test suite.

A default scenario: a 500 km LEO primary with the chaser 50 m away along the
radial (+X) axis, at rest, identity attitude — a clean straight-in approach.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.config import get_settings
from app.schemas.docking import OrbitalElements, SatelliteState, SimulateRequest, SimulationConfig


@pytest.fixture(autouse=True)
def _pin_heuristic_mode(monkeypatch):
    """Keep the suite deterministic and offline.

    The on-disk .env may point at a real LLM provider (e.g. local Ollama);
    without this, runner/API tests would make real, slow model calls. The
    provider-chain tests override the env themselves and clear the settings
    cache in their own try/finally.
    """
    monkeypatch.setenv("LLM_DOCKING_MODE", "heuristic")
    # The on-disk .env may also wire RL artifact paths that exist; empty-string
    # process env (higher priority than the dotenv file) means "not configured".
    # Tests that need real artifacts set their own paths and clear the cache.
    monkeypatch.setenv("LLM_DOCKING_RL_MODEL_PATH", "")
    monkeypatch.setenv("LLM_DOCKING_RL_NORMALIZE_PATH", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# 500 km altitude circular LEO: semi-major axis [m].
LEO_SMA_M = 6_878_000.0


def make_orbital() -> OrbitalElements:
    return OrbitalElements(semi_major_axis_m=LEO_SMA_M)


def make_request(
    position: tuple[float, float, float] = (50.0, 0.0, 0.0),
    velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    angular_velocity: tuple[float, float, float] = (0.0, 0.0, 0.0),
    **config_kwargs: Any,
) -> SimulateRequest:
    orbit = make_orbital()
    primary = SatelliteState(orbital_elements=orbit)
    secondary = SatelliteState(
        position_m=list(position),
        velocity_mps=list(velocity),
        angular_velocity_radps=list(angular_velocity),
        orbital_elements=orbit,
    )
    return SimulateRequest(
        primary=primary,
        secondary=secondary,
        config=SimulationConfig(**config_kwargs),
    )


@pytest.fixture
def sim_request() -> SimulateRequest:
    return make_request()
