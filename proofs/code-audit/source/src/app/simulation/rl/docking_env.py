"""Gymnasium environment for RL/PPO docking.

Wraps the **same physics the service runner uses** — ``propagate_chaser``,
the fuel-burn rule, and the exact docked/diverged conditions — so a policy
trained here behaves identically at inference inside ``SimulationRunner``.

Observation (14-dim, relative to the current sub-goal):
    [rel_pos(3), rel_vel(3), quat(4), ang_vel(3), fuel_frac(1)]

The sub-goal is *not* a fixed origin: at runtime it is whatever the reasoning
layer (LLM or heuristic) last issued, so the policy is trained to drive
``(state - subgoal)`` to zero. The sub-goal itself is re-issued periodically
by the same ``HeuristicAgent.plan`` the service uses, giving the policy the
same moving-target distribution it will see in production.

Action (6-dim continuous in [-1, 1]):
    [ax, ay, az, tx, ty, tz]  — scaled internally to real actuator limits
    (MAX_ACCEL_MPS2 = 50 N / 500 kg, MAX_TORQUE_NM = 20 N·m).

Reward (per spec Eq. 9–11):
    r = -w1‖Δp‖ - w2‖Δv‖ - w3‖Δq‖ + r_success - w4‖u‖ + potential shaping

Design notes (the failure modes this is built to avoid):

* **Divergence guard + penalty.** A random early-training policy can fling the
  chaser to extreme positions, which explodes PPO's value loss. Episodes
  terminate with a large negative penalty when ``‖r‖ > diverged_bound_m``, and
  the penalty is larger than the worst accumulated in-episode cost of a
  mediocre-but-surviving run — otherwise PPO learns to *fail fast and cheap*
  (fly away immediately) rather than learn to dock, producing a clean-looking
  improving reward curve while doing the opposite of the task.

* **Potential-based shaping.** On top of the absolute error penalty, a shaping
  term rewards reducing ‖Δp‖ step-over-step, giving early training a clearer
  gradient toward the target.
"""

from __future__ import annotations

import math

import gymnasium as gym
import numpy as np
from gymnasium import spaces

from app.llm.reasoning_agent import HeuristicAgent, ReasoningInput
from app.schemas.docking import MotionLimits
from app.schemas.events import LlmSubgoal
from app.simulation.dynamics import (
    DEFAULT_INERTIA,
    Command,
    RigidBodyState,
    attitude_error_deg,
    classify_phase,
    propagate_chaser,
)
from app.simulation.safety import capture_checks, enforce_command, limit_velocity

# Actuator limits shared with the PID/LQR controllers and the runner.
MAX_FORCE_N = 50.0  # per-axis thruster saturation [N]
MAX_TORQUE_NM = 20.0  # per-axis torque saturation [N·m]
MAX_ACCEL_MPS2 = MAX_FORCE_N / 500.0  # 0.1 m/s² on the nominal 500 kg chaser

# Docking-port frame (body +X aligned with port).
_IDENTITY_QUAT = np.array([1.0, 0.0, 0.0, 0.0])

OBS_DIM = 14
ACTION_DIM = 6

DEFAULT_REWARD_WEIGHTS = {"w_pos": 1.0, "w_vel": 1.0, "w_att": 1.0, "w_ctrl": 0.1}


def build_rl_observation(state: RigidBodyState, subgoal: LlmSubgoal) -> np.ndarray:
    """The 14-dim observation, expressed relative to the current sub-goal.

    Must be byte-identical between training (env) and inference
    (RlController) — a conformance test enforces this.
    """
    dp = np.asarray(state.position, dtype=float) - np.asarray(
        subgoal.target_position_m, dtype=float
    )
    dv = np.asarray(state.velocity, dtype=float) - np.asarray(
        subgoal.target_velocity_mps, dtype=float
    )
    return np.concatenate(
        [
            dp,
            dv,
            np.asarray(state.quat, dtype=float),
            np.asarray(state.omega, dtype=float),
            [state.fuel_pct / 100.0],
        ]
    ).astype(np.float32)


class DockingEnv(gym.Env):
    """Relative-position + attitude docking task (Hill/RSW, quaternion)."""

    metadata = {"render_modes": []}

    def __init__(
        self,
        *,
        mean_motion_radps: float = 1.1e-3,
        dt: float = 1.0,
        max_steps: int = 300,
        mass_kg: float = 500.0,
        inertia: np.ndarray | None = None,
        max_accel_mps2: float = MAX_ACCEL_MPS2,
        max_torque_nm: float = MAX_TORQUE_NM,
        subgoal_cadence_steps: int = 10,
        dock_position_tol_m: float = 1.25,
        dock_velocity_tol_mps: float = 0.1,
        dock_attitude_tol_deg: float = 2.0,
        dock_omega_tol_radps: float = 0.05,
        diverged_bound_m: float = 1500.0,
        max_omega_radps: float = 5.0,  # tumble guard, mirrors runner max_omega_radps
        reward_weights: dict[str, float] | None = None,
        success_reward: float = 10.0,
        diverged_penalty: float = 50.0,
        fuel_out_penalty: float = 10.0,
        shaping_scale: float = 1.0,
        fuel_consumption_rate_pct_per_s: float = 0.05,
        initial_range_m: tuple[float, float] = (20.0, 400.0),
        motion_limits: MotionLimits | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.n = float(mean_motion_radps)
        self.dt = float(dt)
        self.max_steps = int(max_steps)
        self.mass_kg = float(mass_kg)
        self.inertia = np.asarray(inertia if inertia is not None else DEFAULT_INERTIA, dtype=float)
        self.max_accel = float(max_accel_mps2)
        self.max_torque = float(max_torque_nm)
        self.subgoal_cadence_steps = int(subgoal_cadence_steps)
        self.dock_position_tol = float(dock_position_tol_m)
        self.dock_velocity_tol = float(dock_velocity_tol_mps)
        self.dock_attitude_tol_deg = float(dock_attitude_tol_deg)
        self.dock_omega_tol = float(dock_omega_tol_radps)
        self.diverged_bound = float(diverged_bound_m)
        self.max_omega_radps = float(max_omega_radps)
        self.reward_weights = dict(reward_weights or DEFAULT_REWARD_WEIGHTS)
        self.success_reward = float(success_reward)
        self.diverged_penalty = float(diverged_penalty)
        self.fuel_out_penalty = float(fuel_out_penalty)
        self.shaping_scale = float(shaping_scale)
        self.fuel_rate = float(fuel_consumption_rate_pct_per_s)
        self.initial_range = tuple(initial_range_m)
        self.motion_limits = motion_limits

        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(OBS_DIM,), dtype=np.float32
        )
        self.action_space = spaces.Box(low=-1.0, high=1.0, shape=(ACTION_DIM,), dtype=np.float32)

        self._rng = np.random.default_rng(seed)
        self._planner = HeuristicAgent()
        self._state: RigidBodyState | None = None
        self._subgoal: LlmSubgoal | None = None
        self._step = 0
        self._prev_range_err = 0.0

    # ------------------------------------------------------------------
    # Gymnasium API
    # ------------------------------------------------------------------

    def reset(self, *, seed: int | None = None, options: dict | None = None):
        super().reset(seed=seed)
        if seed is not None:
            self._rng = np.random.default_rng(seed)

        range_m = float(self._rng.uniform(*self.initial_range))
        direction = self._rng.normal(size=3)
        direction /= max(float(np.linalg.norm(direction)), 1e-12)
        pos = direction * range_m
        vel = self._rng.normal(0.0, 0.5, 3)
        if self.motion_limits is not None:
            vel = limit_velocity(vel, self.motion_limits)
        quat = self._random_unit_quat()
        omega = self._rng.normal(0.0, 0.02, 3)

        self._state = RigidBodyState(
            position=pos,
            velocity=vel,
            quat=quat,
            omega=omega,
            fuel_pct=100.0,
            mass_kg=self.mass_kg,
            inertia=self.inertia,
        )
        self._subgoal = self._plan_subgoal()
        self._step = 0
        self._prev_range_err = self._range_error()
        return self._observe(), {}

    def step(self, action):
        action = np.clip(np.asarray(action, dtype=float), -1.0, 1.0)
        accel = action[:3] * self.max_accel
        torque = action[3:] * self.max_torque
        command = Command(force_n=accel * self.mass_kg, torque_nm=torque)
        if self.motion_limits is not None:
            command, _ = enforce_command(
                self._state, command, self.dt, self.n, np.zeros(3), self.motion_limits
            )

        self._state = propagate_chaser(self._state, self.dt, self.n, command)
        if np.linalg.norm(command.force_n) > 1e-6:
            self._state.fuel_pct = max(0.0, self._state.fuel_pct - self.fuel_rate * self.dt)
        self._step += 1

        # Re-issue the sub-goal on the same cadence the service uses, so the
        # policy sees the same moving-target distribution at inference.
        if self._step % self.subgoal_cadence_steps == 0:
            self._subgoal = self._plan_subgoal()

        reward, terminated, reason = self._reward(action)
        truncated = (self._step >= self.max_steps) and not terminated
        obs = self._observe()
        info = {
            "is_success": reason == "docked",
            "termination": reason,
            "range_m": float(np.linalg.norm(self._state.position)),
            "subgoal_target_m": [float(v) for v in self._subgoal.target_position_m],
        }
        return obs, float(reward), bool(terminated), bool(truncated), info

    # ------------------------------------------------------------------
    # Reward / termination
    # ------------------------------------------------------------------

    def _reward(self, action: np.ndarray) -> tuple[float, bool, str | None]:
        s = self._state
        w = self.reward_weights
        range_err = self._range_error()
        shaping = self.shaping_scale * (self._prev_range_err - range_err)
        self._prev_range_err = range_err

        dv = s.velocity - np.asarray(self._subgoal.target_velocity_mps, dtype=float)
        att_err_rad = math.radians(attitude_error_deg(s.quat, _IDENTITY_QUAT))

        r = (
            -w["w_pos"] * min(range_err, 10.0) * 0.02
            - w["w_vel"] * float(np.linalg.norm(dv))
            - w["w_att"] * att_err_rad
            - w["w_ctrl"] * float(np.linalg.norm(action))
            + shaping
        )

        if self._is_docked(s):
            return r + max(100.0, self.success_reward), True, "docked"
        if (
            float(np.linalg.norm(s.position)) > self.diverged_bound
            or float(np.linalg.norm(s.omega)) > self.max_omega_radps
        ):
            return r - self.diverged_penalty, True, "diverged"
        if s.fuel_pct <= 0.0:
            return r - self.fuel_out_penalty, True, "fuel_out"
        return r, False, None

    def _is_docked(self, s: RigidBodyState) -> bool:
        return capture_checks(
            s,
            self.dock_position_tol,
            self.dock_velocity_tol,
            self.dock_attitude_tol_deg,
            self.dock_omega_tol,
        )["eligible"]

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _observe(self) -> np.ndarray:
        return build_rl_observation(self._state, self._subgoal)

    def _range_error(self) -> float:
        """‖state - subgoal_target‖, the primary tracking error."""
        return float(
            np.linalg.norm(
                np.asarray(self._state.position, dtype=float)
                - np.asarray(self._subgoal.target_position_m, dtype=float)
            )
        )

    def _plan_subgoal(self) -> LlmSubgoal:
        s = self._state
        inp = ReasoningInput(
            step=self._step,
            sim_time_s=self._step * self.dt,
            phase=classify_phase(float(np.linalg.norm(s.position))),
            range_m=float(np.linalg.norm(s.position)),
            position_m=[float(v) for v in s.position],
            velocity_mps=[float(v) for v in s.velocity],
            orientation_quat=[float(v) for v in s.quat],
            angular_velocity_radps=[float(v) for v in s.omega],
            fuel_remaining_pct=s.fuel_pct,
            controller="rl",
            anomaly_context=[],
            priority_change=None,
        )
        return self._planner.plan(inp)

    def _random_unit_quat(self) -> np.ndarray:
        q = self._rng.normal(size=4)
        norm = float(np.linalg.norm(q))
        q = q / norm if norm > 0.0 else np.array([1.0, 0.0, 0.0, 0.0])
        if q[0] < 0.0:  # convention: scalar part >= 0
            q = -q
        return q

    # ------------------------------------------------------------------
    # Expert-hook (used by the BC warm-start in train_ppo.py)
    # ------------------------------------------------------------------

    @property
    def current_state(self) -> RigidBodyState:
        return self._state

    @property
    def current_subgoal(self) -> LlmSubgoal:
        return self._subgoal

    def command_to_action(self, command: Command) -> np.ndarray:
        """Convert a controller Command (N, N·m) to the env's [-1,1] action."""
        accel = np.asarray(command.force_n, dtype=float) / self.mass_kg
        torque = np.asarray(command.torque_nm, dtype=float)
        action = np.concatenate([accel / self.max_accel, torque / self.max_torque])
        return np.clip(action, -1.0, 1.0).astype(np.float32)
