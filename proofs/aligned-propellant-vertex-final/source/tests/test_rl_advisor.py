"""LLM x RL advisor tests.

The hybrid mode hands the reasoning layer an advisory sub-goal from the
trained RL policy. These tests pin the contract:

* the heuristic fallback adopts a *safe* suggestion, rejects an unsafe one,
  and never adopts on abort;
* the suggestion is serialized into the LLM prompt;
* missing artifacts degrade to no-advice (run continues, events say `null`)
  rather than failing the run;
* with a real (tiny) policy, the advisor produces a finite suggestion and the
  runner surfaces it on `llm_decision` events.
"""

from __future__ import annotations

import asyncio

import numpy as np
import pytest

from app.config import get_settings
from app.llm.reasoning_agent import HeuristicAgent, ReasoningInput, build_prompt
from app.llm.rl_advisor import RlAdvisor
from app.schemas.events import LlmSubgoal, RlAdvisorSuggestion
from app.simulation.dynamics import RigidBodyState

HEURISTIC = HeuristicAgent()


def _input(position=(50.0, 0.0, 0.0), priority_change=None, rl_advisor=None) -> ReasoningInput:
    return ReasoningInput(
        step=10,
        sim_time_s=10.0,
        phase="closing",
        range_m=float(np.linalg.norm(position)),
        position_m=list(position),
        velocity_mps=[0.0, 0.0, 0.0],
        orientation_quat=[1.0, 0.0, 0.0, 0.0],
        angular_velocity_radps=[0.0, 0.0, 0.0],
        fuel_remaining_pct=100.0,
        controller="lqr",
        anomaly_context=[],
        priority_change=priority_change,
        rl_advisor=rl_advisor,
    )


def _suggestion(
    position=(20.0, 0.0, 0.0), velocity=(-0.5, 0.0, 0.0), closing=0.5
) -> RlAdvisorSuggestion:
    return RlAdvisorSuggestion(
        suggested_position_m=list(position),
        suggested_velocity_mps=list(velocity),
        closing_speed_mps=closing,
        lookahead_s=4.0,
    )


def test_heuristic_adopts_safe_rl_suggestion():
    """A suggestion that reduces range is adopted (velocity capped per phase)."""
    subgoal = HEURISTIC.plan(
        _input(position=(50.0, 0.0, 0.0), rl_advisor=_suggestion(position=(20.0, 0.0, 0.0)))
    )
    assert subgoal.target_position_m == [25.0, 0.0, 0.0]
    assert "RL advisor adopted" in subgoal.rationale
    # Closing capped to the closing-phase cap (2.0 m/s).
    assert subgoal.closing_speed_mps <= 2.0 + 1e-9


def test_heuristic_rejects_range_increasing_suggestion():
    """A suggestion that would increase range is ignored (heuristic fallback)."""
    subgoal = HEURISTIC.plan(
        _input(position=(50.0, 0.0, 0.0), rl_advisor=_suggestion(position=(200.0, 0.0, 0.0)))
    )
    assert "RL advisor adopted" not in subgoal.rationale
    assert np.linalg.norm(subgoal.target_position_m) < 50.0  # heuristic target


def test_abort_always_overrides_advisor():
    """On abort the RL suggestion (the policy knows nothing of priority changes) is ignored."""
    subgoal = HEURISTIC.plan(
        _input(position=(50.0, 0.0, 0.0), priority_change="abort", rl_advisor=_suggestion())
    )
    assert "ABORT" in subgoal.rationale
    assert subgoal.target_position_m == [50.0, 0.0, 0.0]  # hold position


def test_prompt_serializes_advisor_suggestion():
    inp = _input(position=(50.0, 0.0, 0.0), rl_advisor=_suggestion())
    prompt = build_prompt(inp)
    assert "rl_advisor=" in prompt
    assert '"suggested_position_m"' in prompt
    # Without a suggestion the line is explicit "none".
    assert "rl_advisor=none" in build_prompt(_input())


def test_advisor_without_artifacts_returns_none_gracefully():
    """No policy configured -> no advice, no exception (also: no SB3 import)."""
    advisor = RlAdvisor(model_path=None, normalize_path=None)
    state = RigidBodyState(position=np.array([50.0, 0.0, 0.0]))
    subgoal = LlmSubgoal(
        target_position_m=[0.0, 0.0, 0.0],
        target_velocity_mps=[0.0, 0.0, 0.0],
        closing_speed_mps=0.0,
        rationale="t",
    )
    assert advisor.suggest(state, subgoal) is None


# ---------------------------------------------------------------------------
# With a real (tiny) policy — SB3-gated
# ---------------------------------------------------------------------------


def _tiny_policy(tmp_path):
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

    from app.simulation.rl.docking_env import DockingEnv

    env = DummyVecEnv([lambda: DockingEnv(seed=3)])
    venv = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.0, clip_reward=10.0)
    venv.reset()
    venv.step(np.zeros((1, 6), dtype=np.float32))
    model_path = str(tmp_path / "mini.zip")
    norm_path = str(tmp_path / "mini_vecnormalize.pkl")
    PPO(
        "MlpPolicy",
        venv,
        policy_kwargs=dict(net_arch=[64, 64], activation_fn=torch.nn.Tanh),
        n_steps=1024,
        batch_size=128,
        seed=0,
    ).save(model_path)
    venv.save(norm_path)
    return model_path, norm_path


def test_advisor_suggests_with_trained_policy(tmp_path):
    pytest.importorskip("stable_baselines3")
    model_path, norm_path = _tiny_policy(tmp_path)
    advisor = RlAdvisor(
        mass_kg=500.0, lookahead_s=4.0, model_path=model_path, normalize_path=norm_path
    )
    state = RigidBodyState(position=np.array([50.0, 0.0, 0.0]))
    subgoal = LlmSubgoal(
        target_position_m=[25.0, 0.0, 0.0],
        target_velocity_mps=[-0.5, 0.0, 0.0],
        closing_speed_mps=0.5,
        rationale="t",
    )
    sugg = advisor.suggest(state, subgoal)
    assert sugg is not None
    assert len(sugg.suggested_position_m) == 3
    assert len(sugg.suggested_velocity_mps) == 3
    assert np.all(np.isfinite(sugg.suggested_position_m))
    assert sugg.lookahead_s == 4.0


def test_runner_hybrid_mode_surfaces_advisor(tmp_path, monkeypatch):
    """Full run with rl_advisor_enabled: decisions carry the suggestion, no crash."""
    pytest.importorskip("stable_baselines3")
    from conftest import make_request

    from app.sessions.store import Session
    from app.simulation.runner import SimulationRunner

    model_path, norm_path = _tiny_policy(tmp_path)
    monkeypatch.setenv("LLM_DOCKING_RL_MODEL_PATH", model_path)
    monkeypatch.setenv("LLM_DOCKING_RL_NORMALIZE_PATH", norm_path)
    get_settings.cache_clear()  # Settings is lru_cached; pick up the env

    session = Session(session_id="hybrid")
    runner = SimulationRunner(
        session=session,
        request=make_request(position=(50.0, 0.0, 0.0), max_steps=300, rl_advisor_enabled=True),
    )
    asyncio.run(runner.run())
    decisions = [e for e in session.event_log if e.type == "llm_decision"]
    assert decisions, "expected llm_decision events"
    assert any(e.rl_advisor is not None for e in decisions)
    assert session.summary.status in ("docked", "failed")
    get_settings.cache_clear()  # don't leak the env'd settings into later tests


def test_runner_hybrid_mode_without_policy_still_runs(monkeypatch):
    """Enabled but no artifacts: decisions carry rl_advisor=None, run completes."""
    from conftest import make_request

    from app.sessions.store import Session
    from app.simulation.runner import SimulationRunner

    # Empty-string process env (not delenv): the on-disk .env may configure
    # paths that exist, and pydantic falls back to the dotenv file otherwise.
    monkeypatch.setenv("LLM_DOCKING_RL_MODEL_PATH", "")
    monkeypatch.setenv("LLM_DOCKING_RL_NORMALIZE_PATH", "")
    get_settings.cache_clear()

    session = Session(session_id="hybrid-none")
    runner = SimulationRunner(
        session=session,
        request=make_request(position=(50.0, 0.0, 0.0), max_steps=300, rl_advisor_enabled=True),
    )
    asyncio.run(runner.run())
    assert session.summary.status == "docked"
    decisions = [e for e in session.event_log if e.type == "llm_decision"]
    assert decisions
    assert all(e.rl_advisor is None for e in decisions)
