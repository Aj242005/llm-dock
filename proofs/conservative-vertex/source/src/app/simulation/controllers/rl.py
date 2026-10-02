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

import numpy as np

from app.config import get_settings
from app.schemas.docking import ControllerType
from app.schemas.events import LlmSubgoal
from app.simulation.controllers.base import ControlContext, Controller
from app.simulation.dynamics import Command, RigidBodyState
from app.simulation.rl.docking_env import (
    MAX_ACCEL_MPS2,
    MAX_TORQUE_NM,
    DockingEnv,
    build_rl_observation,
)


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

        import torch
        from stable_baselines3 import PPO  # deferred: optional dependency
        from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize

        # Small MLP inference is faster with few threads and leaves CPU capacity
        # for the simulator, event stream and browser.
        torch.set_num_threads(2)

        self._model = PPO.load(self.model_path, device=device)
        # VecNormalize.load re-wraps a venv (only used for its spaces/attrs;
        # the running stats come from the saved pickle).
        dummy = DummyVecEnv([lambda: DockingEnv(seed=0)])
        self._vecnorm = VecNormalize.load(self.normalize_path, dummy)
        self._vecnorm.training = False  # freeze the running stats at inference

    def compute(
        self, state: RigidBodyState, subgoal: LlmSubgoal, dt: float, ctx: ControlContext
    ) -> Command:
        obs = build_rl_observation(state, subgoal)[np.newaxis, :].astype(np.float32)
        obs_norm = self._vecnorm.normalize_obs(obs)
        action, _ = self._model.predict(obs_norm, deterministic=True)
        a = np.clip(np.asarray(action[0], dtype=float), -1.0, 1.0)

        accel = a[:3] * MAX_ACCEL_MPS2
        torque = a[3:] * MAX_TORQUE_NM
        return Command(force_n=accel * self.mass_kg, torque_nm=torque)

    def reset(self, ctx: ControlContext) -> None:
        pass  # stateless policy: nothing to reset between sub-goals
