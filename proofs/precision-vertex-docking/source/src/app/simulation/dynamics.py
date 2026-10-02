"""Attitude + relative orbital dynamics.

Propagation model
-----------------
Relative (Hill/RSW frame, origin at the target/primary satellite):

    x'' - 2n y' - 3n² x = a_x          (radial)
    y'' + 2n x'        = a_y          (along-track)
    z'' + n² z         = a_z          (cross-track)

with n = sqrt(mu / a³) the mean motion of the primary's circular orbit.
Numerical integration is semi-implicit symplectic Euler, which preserves the
CW drift/oscillation structure far better than explicit Euler over many
steps for this linear system.

Attitude uses quaternion kinematics (no Euler angles):

    q' = ½ Ω(ω) q
    I ω' + ω × (Iω) = τ

quaternion convention throughout: [w, x, y, z] with w the scalar part.
"""

from __future__ import annotations

import math

import numpy as np
from pydantic import BaseModel, Field

# Standard gravitational parameter of Earth [m³/s²].
MU_EARTH_M3_S2 = 3.986004418e14

# Default principal moments of inertia for a generic ~500 kg chaser [kg·m²].
DEFAULT_INERTIA = np.array([600.0, 900.0, 900.0])

# Max gyroscopic rotation per rotational sub-step [rad]. Explicit Euler on the
# ω×(Iω) term amplifies the transverse spin rate by ~√(1+(ω·dt)²) per step and
# compounds to exponential blow-up for large ω·dt; sub-stepping keeps each
# rotation small enough that Euler is accurate.
_GYRO_SUBSTEP_RAD = 0.05


def mean_motion_radps(semi_major_axis_m: float, mu: float = MU_EARTH_M3_S2) -> float:
    """Mean motion n of a circular orbit: n = sqrt(mu / a³)."""
    return float(math.sqrt(mu / (semi_major_axis_m**3)))


# ---------------------------------------------------------------------------
# Quaternion algebra (numpy, [w,x,y,z])
# ---------------------------------------------------------------------------


def quat_normalize(q: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(q)
    return q / n if n > 0.0 else np.array([1.0, 0.0, 0.0, 0.0], dtype=float)


def quat_conjugate(q: np.ndarray) -> np.ndarray:
    return np.array([q[0], -q[1], -q[2], -q[3]])


def quat_multiply(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    """Hamilton product p ⊗ q (both [w,x,y,z])."""
    pw, px, py, pz = p
    qw, qx, qy, qz = q
    return np.array(
        [
            pw * qw - px * qx - py * qy - pz * qz,
            pw * qx + px * qw + py * qz - pz * qy,
            pw * qy - px * qz + py * qw + pz * qx,
            pw * qz + px * qy - py * qx + pz * qw,
        ]
    )


def quat_rotate(q: np.ndarray, v: np.ndarray) -> np.ndarray:
    """Rotate a 3-vector by unit quaternion q ([w,x,y,z])."""
    qv = np.array([0.0, v[0], v[1], v[2]])
    q_inv = quat_conjugate(q)
    return quat_multiply(quat_multiply(q, qv), q_inv)[1:]


def quat_from_axis_angle(axis: np.ndarray, angle: float) -> np.ndarray:
    axis = np.asarray(axis, dtype=float)
    norm = np.linalg.norm(axis)
    if norm < 1e-12 or abs(angle) < 1e-12:
        return np.array([1.0, 0.0, 0.0, 0.0])
    axis = axis / norm
    half = angle / 2.0
    return np.array([math.cos(half), *(axis * math.sin(half))])


def quat_to_rotation_matrix(q: np.ndarray) -> np.ndarray:
    """Rotation matrix (body->inertial) from unit quaternion [w,x,y,z]."""
    w, x, y, z = q
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def attitude_error_deg(q1: np.ndarray, q2: np.ndarray) -> float:
    """Angle between two attitudes in degrees."""
    dq = quat_multiply(quat_conjugate(quat_normalize(q1)), quat_normalize(q2))
    return float(2.0 * math.degrees(math.acos(min(1.0, abs(dq[0])))))


# ---------------------------------------------------------------------------
# Phase classification
# ---------------------------------------------------------------------------


def classify_phase(range_m: float) -> str:
    """Classify docking phase by relative range (see README)."""
    if range_m <= 0.0:
        return "docked"
    if range_m <= 5.0:
        return "proximity"
    if range_m <= 30.0:
        return "final_approach"
    if range_m <= 1000.0:
        return "closing"
    return "far_rendezvous"


# ---------------------------------------------------------------------------
# Physics state + integration
# ---------------------------------------------------------------------------


class RigidBodyState(BaseModel):
    """Full continuous state of one satellite (Hill relative for the chaser)."""

    position: np.ndarray = Field(default_factory=lambda: np.zeros(3))
    velocity: np.ndarray = Field(default_factory=lambda: np.zeros(3))
    quat: np.ndarray = Field(default_factory=lambda: np.array([1.0, 0.0, 0.0, 0.0]))
    omega: np.ndarray = Field(default_factory=lambda: np.zeros(3))
    fuel_pct: float = Field(default=100.0)
    mass_kg: float = Field(default=500.0)
    inertia: np.ndarray = Field(default_factory=lambda: DEFAULT_INERTIA.copy())

    model_config = {"arbitrary_types_allowed": True}

    def deep_copy(self) -> RigidBodyState:
        """Return an independent copy (numpy arrays not shared)."""
        return RigidBodyState(
            position=self.position.copy(),
            velocity=self.velocity.copy(),
            quat=self.quat.copy(),
            omega=self.omega.copy(),
            fuel_pct=self.fuel_pct,
            mass_kg=self.mass_kg,
            inertia=self.inertia.copy(),
        )


class Command(BaseModel):
    """Thruster command computed by a controller (see controllers/base.py)."""

    force_n: np.ndarray = Field(default_factory=lambda: np.zeros(3))
    torque_nm: np.ndarray = Field(default_factory=lambda: np.zeros(3))

    model_config = {"arbitrary_types_allowed": True}


def propagate_chaser(
    state: RigidBodyState,
    dt: float,
    n: float,
    command: Command | None = None,
) -> RigidBodyState:
    """Propagate the chaser one fixed step via semi-implicit Euler.

    Translational: CW equations with control acceleration a = F/m.
    Rotational: q' = ½Ωq ; I ω' + ω×(Iω) = τ (Euler step on ω, exact quat step).
    """
    cmd = command or Command()
    force = np.asarray(cmd.force_n, dtype=float)
    torque = np.asarray(cmd.torque_nm, dtype=float)
    m = float(state.mass_kg)

    a = force / m

    # ---- translational: semi-implicit Euler on the CW linear system ----
    x, y, z = state.position
    vx, vy, vz = state.velocity

    ax_cw = 2.0 * n * vy + 3.0 * n * n * x
    ay_cw = -2.0 * n * vx
    az_cw = -n * n * z

    new_vx = vx + (ax_cw + a[0]) * dt
    new_vy = vy + (ay_cw + a[1]) * dt
    new_vz = vz + (az_cw + a[2]) * dt

    new_x = x + new_vx * dt
    new_y = y + new_vy * dt
    new_z = z + new_vz * dt

    # ---- rotational: quaternion kinematics + rigid-body torque ----
    omega = state.omega.copy()
    inertia = np.asarray(state.inertia, dtype=float)
    # I ω' = τ - ω × (Iω), integrated with explicit Euler sub-steps sized so
    # the gyroscopic rotation per sub-step stays ≲ _GYRO_SUBSTEP_RAD. Without
    # this, a fast-spinning chaser (e.g. from a bad policy) goes numerically
    # unstable: the ω×(Iω) term amplifies transverse spin exponentially.
    omega_norm_0 = float(np.linalg.norm(omega))
    n_sub = 1
    if np.isfinite(omega_norm_0) and omega_norm_0 > 1e-12:
        n_sub = max(1, int(math.ceil(omega_norm_0 * dt / _GYRO_SUBSTEP_RAD)))
    h = dt / n_sub
    for _ in range(n_sub):
        angular_accel = (torque - np.cross(omega, inertia * omega)) / inertia
        if not np.all(np.isfinite(angular_accel)):
            break
        omega = omega + angular_accel * h

    new_omega = omega

    # Exact quaternion step for constant ω: q_{k+1} = q_k ⊗ exp(½ ω dt)
    omega_norm = float(np.linalg.norm(new_omega))
    if np.isfinite(omega_norm) and omega_norm > 1e-12:
        half_angle = 0.5 * omega_norm * dt
        dq = np.array([math.cos(half_angle), *(new_omega / omega_norm * math.sin(half_angle))])
        new_quat = quat_normalize(quat_multiply(state.quat, dq))
    else:
        new_quat = quat_normalize(state.quat)

    return RigidBodyState(
        position=np.array([new_x, new_y, new_z]),
        velocity=np.array([new_vx, new_vy, new_vz]),
        quat=new_quat,
        omega=new_omega,
        fuel_pct=state.fuel_pct,
        mass_kg=m,
        inertia=inertia,
    )
