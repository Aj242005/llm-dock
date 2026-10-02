"""Regressions found by tracing the live Vertex session and repository entry points."""

import asyncio
import subprocess
import sys

import httpx
import numpy as np
import pytest
from conftest import make_request

from app.config import get_settings
from app.llm.reasoning_agent import HeuristicAgent
from app.llm.rl_advisor import RlAdvisor
from app.schemas.docking import MotionLimits
from app.sessions.store import Session
from app.simulation.dynamics import Command, RigidBodyState
from app.simulation.runner import SimulationRunner


@pytest.fixture
async def client():
    from app.main import app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as connection:
        yield connection


async def test_corrupt_policy_is_unavailable_and_rejected_before_start(
    client, tmp_path, monkeypatch
):
    for name in ["MODEL", "NORMALIZE"]:
        artifact = tmp_path / name
        artifact.write_bytes(b"not a policy")
        monkeypatch.setenv(f"LLM_DOCKING_RL_{name}_PATH", str(artifact))
    get_settings.cache_clear()
    try:
        capability = (await client.get("/api/v1/capabilities")).json()
        assert capability["rl_available"] is False
        assert "could not load" in capability["rl_reason"]
        payload = make_request(rl_advisor_enabled=True).model_dump(mode="json")
        response = await client.post("/api/v1/docking/simulate", json=payload)
        assert response.status_code == 400
        assert "working trained policy" in response.json()["detail"]
    finally:
        get_settings.cache_clear()


async def test_one_bad_prediction_does_not_disable_future_policy_advice():
    class SometimesFails:
        calls = 0

        def compute(self, *args, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise ValueError("transient inference failure")
            return Command(force_n=np.array([-1.0, 0, 0]))

    request = make_request(rl_advisor_enabled=True)
    runner = SimulationRunner(Session("policy-recovery"), request)
    runner._rl_advisor = RlAdvisor()
    runner._rl_advisor._controller = SometimesFails()
    state = RigidBodyState(position=np.array([50.0, 0, 0]))
    assert runner._advisor_suggestion(state, None) is None
    assert "inference failed" in runner._rl_advisor.last_error
    assert runner._advisor_suggestion(state, None) is not None
    assert runner._rl_advisor.last_error is None


async def test_disabled_advice_is_explicit_in_decision_and_tools():
    session = Session("disabled-advice")
    await SimulationRunner(session, make_request(max_steps=2)).run()
    decision = next(e for e in session.event_log if e.type == "llm_decision")
    assert decision.rl_advisor is None
    assert decision.rl_advisor_status == "disabled"
    reading = next(
        t["result"] for t in decision.tool_results if t["name"] == "inspect_rl_heuristic"
    )
    assert reading["status"] == "disabled"
    assert "switched off" in reading["reason"]


async def test_llm_disabled_does_not_require_a_provider_key(client, monkeypatch):
    monkeypatch.setenv("VERTEX_API_KEY", "")
    monkeypatch.setenv("LLM_DOCKING_MODE", "vertex")
    get_settings.cache_clear()
    try:
        response = await client.post(
            "/api/v1/docking/simulate",
            json=make_request(
                llm_enabled=False,
                provider="vertex",
                max_steps=2,
            ).model_dump(mode="json"),
        )
        assert response.status_code == 202
        await asyncio.sleep(0.02)
        events = (await client.get(response.json()["summary_url"] + "/events")).json()
        assert not any(e["type"] == "llm_decision" for e in events)
    finally:
        get_settings.cache_clear()


async def test_final_state_keeps_spacecraft_name_and_configured_limits():
    request = make_request(max_steps=2)
    request.secondary.name = "Audit chaser"
    request.secondary.capture_radius_m = 0.5
    request.secondary.motion_limits = MotionLimits(max_speed_mps=0.1)
    session = Session("summary-metadata")
    await SimulationRunner(session, request).run()
    final = session.summary.final_secondary
    assert final.name == request.secondary.name
    assert final.capture_radius_m == 0.5
    assert final.motion_limits == request.secondary.motion_limits


async def test_injected_sensor_fault_blocks_capture_and_brakes_independently(monkeypatch):
    from app.simulation.controllers import base

    original = base.build_controller

    class UnsafePolicy:
        def compute(self, *args):
            return Command(force_n=np.array([-50.0, 0, 0]))

        def reset(self, ctx):
            pass

    monkeypatch.setattr(
        "app.simulation.runner.build_controller",
        lambda kind, *args: (
            UnsafePolicy() if str(kind) in ("rl", "ControllerType.RL") else original(kind, *args)
        ),
    )
    request = make_request(
        position=(1.0, 0, 0),
        velocity=(-0.01, 0, 0),
        controller="rl",
        max_steps=2,
        anomalies=[{"type": "sensor_dropout", "step": 0, "duration_steps": 10, "corrupt": True}],
    )
    session = Session("fault-capture")
    await SimulationRunner(session, request).run()
    telemetry = [e for e in session.event_log if e.type == "telemetry" and e.step > 0]
    assert telemetry
    assert telemetry[0].command_force_n[0] > 0
    assert not telemetry[0].capture["eligible"]
    assert "blocked_reason" in session.capture
    assert session.summary.status != "docked"


def test_classical_controllers_import_without_gymnasium():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import importlib.abc, sys
sys.path.insert(0, 'src')
class BlockGym(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'gymnasium': raise ImportError('RL extras absent')
sys.meta_path.insert(0, BlockGym())
import app.simulation.runner
""",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_evaluation_cli_defaults_make_a_valid_request(monkeypatch):
    from app.simulation.rl.evaluate_policy import make_request as evaluate_request
    from app.simulation.rl.evaluate_policy import parse_args

    monkeypatch.setattr(sys, "argv", ["evaluate_policy"])
    args = parse_args()
    request = evaluate_request("lqr", 42, args.range_m, args.max_steps, args.max_range_m)
    assert request.config.max_range_m == 1000


async def test_provider_model_is_resolved_in_export_metadata():
    class NamedAgent(HeuristicAgent):
        model = "verified-test-model"

    session = Session("resolved-model")
    SimulationRunner(session, make_request(model=None), agent=NamedAgent())
    assert session.request_data["config"]["model"] == "verified-test-model"


async def test_near_port_relative_speed_limit_with_moving_primary():
    request = make_request(
        position=(4, 0, 0),
        velocity=(-0.04, 0, 0),
        max_steps=200,
        near_port_speed_mps=0.02,
        dock_velocity_tol_mps=0.005,
    )
    request.primary.velocity_mps = [0.05, 0, 0]
    request.secondary.motion_limits = MotionLimits(max_speed_mps=0.1)
    session = Session("moving-primary-speed")
    await SimulationRunner(session, request).run()
    telemetry = [e for e in session.event_log if e.type == "telemetry"]
    assert np.linalg.norm(telemetry[1].velocity_mps) < np.linalg.norm(telemetry[0].velocity_mps)
    assert all(np.linalg.norm(e.velocity_mps) <= 0.02 + 1e-6 for e in telemetry[15:])
    assert all(np.linalg.norm(e.secondary_velocity_mps) <= 0.1 + 1e-6 for e in telemetry)


async def test_slow_session_setup_does_not_block_existing_event_loop(client, monkeypatch):
    import time

    from app.api import routes

    original = routes.SimulationRunner

    def slow_setup(*args, **kwargs):
        time.sleep(0.15)
        return original(*args, **kwargs)

    monkeypatch.setattr(routes, "SimulationRunner", slow_setup)
    creation = asyncio.create_task(
        client.post(
            "/api/v1/docking/simulate",
            json=make_request(
                max_steps=2,
            ).model_dump(mode="json"),
        )
    )
    start = asyncio.get_running_loop().time()
    await asyncio.sleep(0.03)
    assert asyncio.get_running_loop().time() - start < 0.12
    assert not creation.done()
    assert (await creation).status_code == 202


def test_proof_export_rejects_missing_checkpoint_normalizer(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
sys.path.insert(0, 'src')
from app.simulation.rl.proofs import main
main()
""",
            "--run-dir",
            str(tmp_path),
            "--checkpoint",
            "other-policy",
            "--episodes",
            "1",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "checkpoint's matching VecNormalize" in result.stderr
