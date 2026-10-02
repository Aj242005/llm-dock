"""RL/PPO low-level controller: wraps a trained Stable-Baselines3 policy.

Implements the same ``Controller.compute(state, subgoal, dt, ctx)`` interface
as PID and LQR, so the runner treats it identically. The policy was trained
(``app/simulation/rl/train_ppo.py``) on the 14-dim observation built by
``build_rl_observation`` — relative position/velocity to the current sub-goal,
quaternion, angular velocity, fuel fraction — and normalized with the
``VecNormalize`` stats saved next to the checkpoint.

**Both files must be loaded together.** Feeding unnormalized observations to
the policy silently produces near-random actions, because the network learned
on normalized inputs. The conformance test in ``tests/test_rl.py`` enforces
that the observation builder used here is byte-identical to the one used in
training.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.schemas.docking import ControllerType
from app.schemas.events import LlmSubgoal
from app.simulation.controllers.base import ControlContext, Controller
from app.simulation.dynamics import Command, RigidBodyState
from app.simulation.rl.docking_env import (
    ACTION_DIM,
    MAX_ACCEL_MPS2,
    MAX_TORQUE_NM,
    OBS_DIM,
    DockingEnv,
    build_rl_observation,
)


@lru_cache(maxsize=4)
def _load_policy(model_path, normalize_path, device, model_version, normalize_version):
    """Reuse frozen inference artifacts; file versions invalidate replaced checkpoints."""
    import torch
    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

    torch.set_num_threads(2)
    model = PPO.load(model_path, device=device)
    if model.observation_space.shape != (OBS_DIM,) or model.action_space.shape != (ACTION_DIM,):
        raise ValueError("Policy requires 14 observations and 6 actuator actions")
    dummy = DummyVecEnv([lambda: DockingEnv(seed=0)])
    try:
        vecnorm = VecNormalize.load(normalize_path, dummy)
        if not vecnorm.norm_obs or vecnorm.obs_rms.mean.shape != (OBS_DIM,):
            raise ValueError("Policy requires matching 14-dimensional observation normalization")
        if (
            not np.isfinite(vecnorm.obs_rms.mean).all()
            or not np.isfinite(vecnorm.obs_rms.var).all()
        ):
            raise ValueError("Normalization statistics must be finite")
        if np.any(vecnorm.obs_rms.var < 0):
            raise ValueError("Normalization variances must be non-negative")
        vecnorm.training = False
        vecnorm.norm_reward = False
        return model, vecnorm
    finally:
        dummy.close()


class RlController(Controller):
    name = ControllerType.RL

    def __init__(
        self,
        mass_kg: float,
        inertia: np.ndarray,
        model_path: str | None = None,
        normalize_path: str | None = None,
        device: str = "cpu",
    ) -> None:
        super().__init__(mass_kg=float(mass_kg), inertia=np.asarray(inertia, dtype=float))
        settings = get_settings()
        self.model_path = model_path or settings.rl_model_path
        self.normalize_path = normalize_path or settings.rl_normalize_path
        if not self.model_path or not self.normalize_path:
            raise ValueError(
                "controller='rl' requires LLM_DOCKING_RL_MODEL_PATH and "
                "LLM_DOCKING_RL_NORMALIZE_PATH (train a policy with "
                "`python -m app.simulation.rl.train_ppo` first)"
            )

        model_file, normalize_file = (
            Path(self.model_path).resolve(),
            Path(self.normalize_path).resolve(),
        )
        versions = [(p.stat().st_mtime_ns, p.stat().st_size) for p in (model_file, normalize_file)]
        self._model, self._vecnorm = _load_policy(
            str(model_file), str(normalize_file), device, *versions
        )

    def compute(
        self, state: RigidBodyState, subgoal: LlmSubgoal, dt: float, ctx: ControlContext
    ) -> Command:
        obs = build_rl_observation(state, subgoal)[np.newaxis, :].astype(np.float32)
        obs_norm = self._vecnorm.normalize_obs(obs)
        action, _ = self._model.predict(obs_norm, deterministic=True)
        a = np.asarray(action[0], dtype=float)
        if a.shape != (ACTION_DIM,) or not np.isfinite(a).all():
            raise ValueError("Policy returned an invalid actuator command")
        a = np.clip(a, -1.0, 1.0)

        accel = a[:3] * MAX_ACCEL_MPS2
        torque = a[3:] * MAX_TORQUE_NM
        return Command(force_n=accel * state.mass_kg, torque_nm=torque)

    def reset(self, ctx: ControlContext) -> None:
        pass  # stateless policy: nothing to reset between sub-goals
