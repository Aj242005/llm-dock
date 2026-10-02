"""PID low-level controller.

    u(t) = Kp·e(t) + Ki·∫e dt + Kd·de/dt

Tracks the LLM sub-goal: position error is relative to ``target_position_m``
and velocity error to ``target_velocity_mps``. Two separate PID loops run:
one for translation (force), one for attitude (torque, tracking a zero-relative
rate and a level attitude derived from the closing direction).

Gains are mass-scaled (spring-damper with ωn ≈ 0.09 rad/s, ζ = 0.9 for a
generic chaser) and phase-scaled so the controller is gentle at range and
firm close in, which keeps the maneuver stable across the full far -> docked
range while a single fixed gain set would oscillate or stall.

The attitude loop drives the *full* attitude to the docking-port frame
(identity quat) with nulled body rates. Translation is commanded in the Hill
frame, so attitude alignment and docking are decoupled and reachable from any
approach direction.
"""

from __future__ import annotations

import math

import numpy as np

from app.schemas.docking import ControllerType
from app.schemas.events import LlmSubgoal
from app.simulation.controllers.base import ControlContext, Controller
from app.simulation.dynamics import (
    Command,
    RigidBodyState,
    quat_conjugate,
    quat_multiply,
)

# Docking-port frame: Hill-frame aligned (identity quat) with nulled rates.
_IDENTITY_QUAT = np.array([1.0, 0.0, 0.0, 0.0])

# Translation loop: mass-scaled spring-damper (ωn², damping ratio ζ).
POS_OMEGA2 = 0.008  # ωn ≈ 0.089 rad/s for the nominal 500 kg chaser
POS_ZETA = 0.9
KI_POS = 0.002  # integral gain, N per (m·s) of accumulated error

# Attitude gains (per rad of error / rad/s of rate error).
KP_ATT = 2.0
KD_ATT = 1.0

MAX_FORCE_N = 50.0  # per-axis thruster saturation [N]
MAX_TORQUE_NM = 20.0

# Phase-scaling envelope: gain multiplier ramps from `_FAR_SCALE` at range to
# 1.0 as the chaser reaches the port (proximity factor below).
_FAR_SCALE = 0.35
_PROXIMITY_DECAY_M = 25.0


class PidController(Controller):
    name = ControllerType.PID

    def __init__(self, mass_kg: float, inertia: np.ndarray) -> None:
        super().__init__(mass_kg=float(mass_kg), inertia=np.asarray(inertia, dtype=float))
        # Mass-scaled proportional/damping gains [N/m] and [N/(m/s)].
        self._kp_pos = self.mass_kg * POS_OMEGA2
        self._kd_pos = self.mass_kg * 2.0 * POS_ZETA * math.sqrt(POS_OMEGA2)

    def compute(
        self, state: RigidBodyState, subgoal: LlmSubgoal, dt: float, ctx: ControlContext
    ) -> Command:
        pos_err = np.asarray(subgoal.target_position_m, dtype=float) - state.position

        # Phase-dependent scaling: gentle far, firm close-in.
        range_m = float(np.linalg.norm(state.position))
        prox = float(math.exp(-range_m / _PROXIMITY_DECAY_M))  # 1 at port -> 0 far away
        kp = self._kp_pos * (_FAR_SCALE + (1.0 - _FAR_SCALE) * prox)
        kd = self._kd_pos * (_FAR_SCALE + (1.0 - _FAR_SCALE) * prox)
        ki = KI_POS * (_FAR_SCALE + (1.0 - _FAR_SCALE) * prox)

        # Integral term (reset by the runner via reset() when a new sub-goal arrives).
        ctx.position_integral += pos_err * dt
        ctx.position_integral = np.clip(ctx.position_integral, -200.0, 200.0)

        # Velocity error relative to the sub-goal's closing-rate envelope.
        target_vel = np.asarray(subgoal.target_velocity_mps, dtype=float)
        vel_err = target_vel - state.velocity

        force = kp * pos_err + ki * ctx.position_integral + kd * vel_err
        force = np.clip(force, -MAX_FORCE_N, MAX_FORCE_N)

        # ---- attitude loop: drive the full attitude to the docking-port
        #      frame (identity quat), nulling body rates. The rotation vector
        #      via atan2 handles 180° errors exactly.
        dq = quat_multiply(quat_conjugate(state.quat), _IDENTITY_QUAT)
        if dq[0] < 0:
            dq = -dq
        w = float(dq[0])
        v = dq[1:]
        v_norm = float(np.linalg.norm(v))
        if v_norm > 1e-12:
            rot_vec = (2.0 * np.arctan2(v_norm, w)) * (v / v_norm)
        else:
            rot_vec = np.zeros(3)
        torque = state.inertia * (0.008 * rot_vec - 0.18 * state.omega)
        torque = np.clip(torque, -MAX_TORQUE_NM, MAX_TORQUE_NM)

        return Command(force_n=force, torque_nm=torque)

    def reset(self, ctx: ControlContext) -> None:
        ctx.position_integral = np.zeros(3)
        ctx.last_position_error = None
