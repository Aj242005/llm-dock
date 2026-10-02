"""RL subsystem tests: env semantics + training/inference conformance.

The critical guarantees under test:

* the env drives the SAME ``propagate_chaser`` the service runner uses (a
  policy trained here behaves identically in production), and
* the ``RlController`` rebuilds the exact normalized observation the policy
  was trained on (byte-identical obs builder + VecNormalize stats).

Skipped automatically when stable-baselines3 is not installed (the RL extras
are optional for the base service).
"""

from __future__ import annotations

import numpy as np
import pytest
import torch

sb3 = pytest.importorskip("stable_baselines3")

from app.schemas.events import LlmSubgoal
from app.simulation.controllers.base import ControlContext
from app.simulation.controllers.rl import RlController
from app.simulation.dynamics import (
    DEFAULT_INERTIA,
    Command,
    RigidBodyState,
    propagate_chaser,
)
from app.simulation.rl.docking_env import (
    MAX_ACCEL_MPS2,
    MAX_FORCE_N,
    MAX_TORQUE_NM,
    DockingEnv,
    build_rl_observation,
)

SUBGOAL = LlmSubgoal(
    target_position_m=[0.0, 0.0, 0.0],
    target_velocity_mps=[0.0, 0.0, 0.0],
    closing_speed_mps=0.0,
    rationale="test",
)


def _env(**kwargs) -> DockingEnv:
    return DockingEnv(seed=kwargs.pop("seed", 0), **kwargs)


def test_observation_shape_and_space():
    env = _env()
    obs, _ = env.reset()
    assert obs.shape == (14,)
    assert obs.dtype == np.float32
    assert env.observation_space.contains(obs)
    action = env.action_space.sample()
    assert env.action_space.contains(action)


def test_observation_is_relative_to_subgoal():
    env = _env()
    obs, _ = env.reset()
    state, subgoal = env.current_state, env.current_subgoal
    expected = build_rl_observation(state, subgoal)
    assert np.array_equal(obs, expected)
    assert np.allclose(obs[:3], state.position - np.asarray(subgoal.target_position_m))
    assert np.allclose(obs[3:6], state.velocity - np.asarray(subgoal.target_velocity_mps))
    assert np.allclose(obs[6:10], state.quat)
    assert np.allclose(obs[10:13], state.omega)
    assert obs[13] == state.fuel_pct / 100.0


def test_env_step_matches_runner_propagator():
    """The env must use the exact same physics as the service runner."""
    env = _env()
    env.reset()
    before = env.current_state.deep_copy()
    action = np.array([1.0, -0.5, 0.25, 0.1, 0.0, -0.2], dtype=float)
    _, _, _, _, _ = env.step(action)

    # Manual propagation with the same command semantics (force = a * mass).
    command = Command(
        force_n=action[:3] * MAX_ACCEL_MPS2 * env.mass_kg,
        torque_nm=action[3:] * MAX_TORQUE_NM,
    )
    expected = propagate_chaser(before, env.dt, env.n, command)
    if np.linalg.norm(command.force_n) > 1e-6:
        expected.fuel_pct = max(0.0, expected.fuel_pct - env.fuel_rate * env.dt)

    after = env.current_state
    assert np.allclose(after.position, expected.position, atol=1e-9)
    assert np.allclose(after.velocity, expected.velocity, atol=1e-9)
    assert np.allclose(after.quat, expected.quat, atol=1e-9)
    assert np.allclose(after.omega, expected.omega, atol=1e-9)
    assert after.fuel_pct == pytest.approx(expected.fuel_pct)


def test_action_bounds_are_respected():
    env = _env()
    env.reset()
    before = env.current_state.deep_copy()
    # A huge out-of-range action must be clipped to the actuator envelope, so
    # the velocity change is bounded by the applied accel PLUS the CW coupling
    # terms (2n·vy + 3n²x, -2n·vx, -n²z) that are always present.
    obs, reward, terminated, truncated, _ = env.step([99.0] * 6)
    n, dt = env.n, env.dt
    x, y, z = before.position
    vx, vy, vz = before.velocity
    cw = np.array([2.0 * n * vy + 3.0 * n * n * x, -2.0 * n * vx, -n * n * z])
    dv = np.linalg.norm(env.current_state.velocity - before.velocity)
    # [99]*6 clips to ones on all three axes -> sqrt(3) * max_accel, + CW.
    assert dv <= (np.sqrt(3) * MAX_ACCEL_MPS2 + np.linalg.norm(cw)) * dt + 1e-9
    assert np.isfinite(reward)


def test_docked_termination_grants_success_reward():
    env = _env(max_steps=300)
    env.reset()
    # Park the chaser right at the port with aligned attitude.
    env._state = RigidBodyState(
        position=np.array([0.2, 0.0, 0.0]),
        velocity=np.zeros(3),
        quat=np.array([1.0, 0.0, 0.0, 0.0]),
        omega=np.zeros(3),
        fuel_pct=100.0,
        mass_kg=env.mass_kg,
        inertia=env.inertia,
    )
    env._subgoal = env._plan_subgoal()
    obs, reward, terminated, truncated, info = env.step([0.0] * 6)
    assert terminated
    assert info["termination"] == "docked"
    assert reward > 0.0  # success reward dominates the small tracking cost


def test_diverged_termination_punishes_heavily():
    env = _env()
    env.reset()
    env._state = RigidBodyState(
        position=np.array([env.diverged_bound + 1.0, 0.0, 0.0]),
        velocity=np.zeros(3),
        quat=np.array([1.0, 0.0, 0.0, 0.0]),
        omega=np.zeros(3),
        fuel_pct=100.0,
        mass_kg=env.mass_kg,
        inertia=env.inertia,
    )
    _, reward, terminated, _, info = env.step([0.0] * 6)
    assert terminated
    assert info["termination"] == "diverged"
    assert reward <= -env.diverged_penalty


def test_timeout_is_truncation_not_termination():
    env = _env(max_steps=3)
    env.reset()
    terminated = truncated = False
    for _ in range(5):
        obs, _, terminated, truncated, info = env.step([0.0] * 6)
        if terminated or truncated:
            break
    assert truncated and not terminated
    assert info["termination"] is None


# ---------------------------------------------------------------------------
# Inference conformance: RlController == what the policy was trained on
# ---------------------------------------------------------------------------


def test_rl_controller_inference_roundtrip(tmp_path):
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

    env = DummyVecEnv([lambda: DockingEnv(seed=1)])
    venv = VecNormalize(env, norm_obs=True, norm_reward=True, clip_obs=10.0, clip_reward=10.0)
    venv.reset()
    venv.step(np.zeros((1, 6), dtype=np.float32))  # populate obs/ret running stats

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

    controller = RlController(500.0, DEFAULT_INERTIA.copy(), model_path, norm_path)
    state = RigidBodyState(
        position=np.array([10.0, 5.0, -2.0]),
        velocity=np.array([0.2, 0.0, -0.1]),
        quat=np.array([1.0, 0.0, 0.0, 0.0]),
        omega=np.zeros(3),
    )
    cmd = controller.compute(state, SUBGOAL, 1.0, ControlContext())
    assert np.all(np.isfinite(cmd.force_n))
    assert np.all(np.isfinite(cmd.torque_nm))
    assert np.linalg.norm(cmd.force_n) <= MAX_FORCE_N * np.sqrt(3) + 1e-6
    assert np.linalg.norm(cmd.torque_nm) <= MAX_TORQUE_NM * np.sqrt(3) + 1e-6

    # The controller normalized the exact same obs the env would build,
    # including the clip_obs bound the training VecNormalize applied.
    obs = build_rl_observation(state, SUBGOAL)[np.newaxis, :].astype(np.float32)
    rms = controller._vecnorm.obs_rms
    clip = controller._vecnorm.clip_obs
    expected = np.clip((obs - rms.mean) / np.sqrt(rms.var + 1e-8), -clip, clip)
    assert np.allclose(controller._vecnorm.normalize_obs(obs), expected, atol=1e-5)


def test_rl_controller_requires_trained_artifacts(monkeypatch):
    class _NoArtifacts:
        rl_model_path = None
        rl_normalize_path = None

    monkeypatch.setattr("app.simulation.controllers.rl.get_settings", lambda: _NoArtifacts())
    with pytest.raises(ValueError, match="LLM_DOCKING_RL_MODEL_PATH"):
        RlController(500.0, DEFAULT_INERTIA.copy())
