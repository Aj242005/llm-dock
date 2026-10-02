"""LQR low-level controller.

    J = ∫₀^∞ (xᵀQx + uᵀRu) dt   =>   u* = -K x

The state is the full 12-DOF stacked vector
    x = [delta_r (3), delta_v (3), delta_angle (3), delta_omega (3)]
with errors relative to the LLM sub-goal (position/velocity target). The
attitude error uses the rotation-vector (axis·angle) representation, so the
whole controller is a single continuous-time LQR over the linearized CW +
quaternion kinematics — no Euler angles.

The algebraic Riccati equation is solved numerically with the scipy port
``scipy.linalg.solve_continuous_are`` when scipy is available, otherwise a
hand-rolled iterative (Kleinman) solver is used. Only numpy is a hard
dependency.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np

from app.schemas.docking import ControllerType
from app.schemas.events import LlmSubgoal
from app.simulation.controllers.base import (
    ControlContext,
    Controller,
    approach_force,
    attitude_error,
    attitude_torque,
)
from app.simulation.controllers.lqr_riccati import solve_continuous_are
from app.simulation.dynamics import Command, RigidBodyState

# ---------------------------------------------------------------------------
# Tuning. Q penalizes position/velocity errors; R penalizes control effort.
# ---------------------------------------------------------------------------
Q_TRANSLATION = 1.0  # per m²  (position error)
Q_VELOCITY = 0.2  # per (m/s)²
Q_ANGLE = 8.0  # per rad² (attitude error)
Q_RATE = 0.5  # per (rad/s)²
R_FORCE = 1e-3  # per N²
R_TORQUE = 0.1  # per (N·m)²

MAX_FORCE_N = 50.0
MAX_TORQUE_NM = 20.0


class LqrController(Controller):
    name = ControllerType.LQR

    def __init__(self, mass_kg: float, inertia: np.ndarray, n: float) -> None:
        super().__init__(mass_kg=float(mass_kg), inertia=np.asarray(inertia, dtype=float))
        self.n = float(n)
        self._assembly = self._build_linear_system()

    # ------------------------------------------------------------------
    # Linear-time-invariant model assembly (CW + q-kinematics, cached)
    # ------------------------------------------------------------------

    def _build_linear_system(self) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """Return (A, B, Q, R) for the continuous-time LTI system ẋ = Ax + Bu."""
        n = self.n
        mass = self.mass_kg
        Ix, Iy, Iz = self.inertia

        # -- Translational: CW — ẋ = A_t x_t + B_t u_t,  x_t = [r; v] --
        A_t = np.array(
            [
                [0.0, 0.0, 0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 0.0, 0.0, 1.0],
                [3.0 * n * n, 0.0, 0.0, 0.0, 2.0 * n, 0.0],
                [0.0, 0.0, 0.0, -2.0 * n, 0.0, 0.0],
                [0.0, 0.0, -n * n, 0.0, 0.0, 0.0],
            ]
        )
        B_t = np.zeros((6, 3))
        B_t[3:, :] = np.eye(3) / mass

        # -- Rotational: δθ dynamics from q-kinematics linearized about zero
        #    (δθ' ≈ δω, I δω' ≈ -ω×(Iω) + τ, linearized δω' = I⁻¹ τ).
        A_r = np.zeros((6, 6))
        A_r[0:3, 3:6] = np.eye(3)
        B_r = np.vstack((np.zeros((3, 3)), np.diag(1.0 / np.array([Ix, Iy, Iz]))))

        # -- Combine: 12-state LTI --
        A = np.zeros((12, 12))
        A[:6, :6] = A_t
        A[6:, 6:] = A_r
        B = np.zeros((12, 6))
        B[:6, :3] = B_t
        B[6:, 3:] = B_r

        # -- Cost matrices --
        Q = np.zeros((12, 12))
        Q[0, 0] = Q[1, 1] = Q[2, 2] = Q_TRANSLATION
        Q[3, 3] = Q[4, 4] = Q[5, 5] = Q_VELOCITY
        Q[6, 6] = Q[7, 7] = Q[8, 8] = Q_ANGLE
        Q[9, 9] = Q[10, 10] = Q[11, 11] = Q_RATE

        R = np.zeros((6, 6))
        R[0, 0] = R[1, 1] = R[2, 2] = R_FORCE
        R[3, 3] = R[4, 4] = R[5, 5] = R_TORQUE

        return A, B, Q, R

    @property
    def gain(self) -> np.ndarray:
        """Close-loop gain K (6x12) solving the CARE, cached per controller."""
        key = (self.n, self.mass_kg, *self.inertia)
        return self._gain_cached(*key)

    @staticmethod
    @lru_cache(maxsize=64)
    def _gain_cached(n: float, mass: float, ix: float, iy: float, iz: float) -> np.ndarray:
        inst = LqrController(mass_kg=mass, inertia=np.array([ix, iy, iz]), n=n)
        A, B, Q, R = inst._assembly
        P = solve_continuous_are(A, B, Q, R)
        return np.linalg.solve(R, B.T @ P)

    def compute(
        self, state: RigidBodyState, subgoal: LlmSubgoal, dt: float, ctx: ControlContext
    ) -> Command:
        # -- Translational error state: error = state - target, so the error
        #    obeys the same CW dynamics as the state (targets are constant)
        #    and the LTI model ẋ = Ax + Bu has consistent signs. Without this
        #    convention the closed loop is anti-damped (positive feedback).
        r_err = state.position - np.asarray(subgoal.target_position_m, dtype=float)
        v_err = state.velocity - np.asarray(subgoal.target_velocity_mps, dtype=float)

        # -- Attitude error state: rotation vector of the current attitude
        #    relative to the docking-port frame (identity quat), so ψ̇ = ω and
        #    the rotational block is a driven double integrator. atan2 keeps
        #    180° errors exact and lets the LQR null roll as well as pointing.
        angle_err, omega_err = attitude_error(state, subgoal)

        x = np.concatenate([r_err, v_err, angle_err, omega_err])

        u = -self.gain @ x
        force = np.clip(
            approach_force(state, subgoal, dt, self.n)
            if subgoal.maneuver_mode == "approach"
            else u[:3],
            -MAX_FORCE_N,
            MAX_FORCE_N,
        )
        torque = attitude_torque(state, subgoal)
        return Command(force_n=force, torque_nm=torque)

    def reset(self, ctx: ControlContext) -> None:
        ctx.position_integral = np.zeros(3)
        ctx.last_position_error = None
