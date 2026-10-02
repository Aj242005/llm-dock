"""One capture gate and one velocity envelope used by API, tools, and training."""

import numpy as np

from app.schemas.docking import MotionLimits
from app.simulation.dynamics import Command, attitude_error_deg, propagate_chaser

CAPTURE_RANGE_M = 1.25


def limit_velocity(velocity, limits: MotionLimits):
    velocity = np.asarray(velocity, dtype=float).copy()
    velocity[2] = np.clip(
        velocity[2], -limits.max_vertical_speed_mps, limits.max_vertical_speed_mps
    )
    horizontal = np.linalg.norm(velocity[:2])
    if horizontal > limits.max_horizontal_speed_mps:
        velocity[:2] *= limits.max_horizontal_speed_mps / horizontal
    speed = np.linalg.norm(velocity)
    if speed > limits.max_speed_mps:
        velocity *= limits.max_speed_mps / speed
    return velocity


def capture_checks(
    state,
    position_tol=1.25,
    velocity_tol=0.1,
    attitude_tol=2.0,
    omega_tol=0.05,
    primary_radius=1.25,
    secondary_radius=1.25,
):
    """Each port must be inside the other port's capture radius."""
    radius = min(CAPTURE_RANGE_M, position_tol, primary_radius, secondary_radius)
    checks = {
        "range": float(np.linalg.norm(state.position)) <= radius,
        "relative_speed": float(np.linalg.norm(state.velocity)) <= velocity_tol,
        "alignment": attitude_error_deg(state.quat, np.array([1.0, 0.0, 0.0, 0.0])) <= attitude_tol,
        "rotation_rate": float(np.linalg.norm(state.omega)) <= omega_tol,
    }
    if not all(
        np.isfinite(values).all()
        for values in [state.position, state.velocity, state.quat, state.omega]
    ):
        checks = {key: False for key in checks}
    return {"eligible": all(checks.values()), "checks": checks, "shared_range_m": radius}


def enforce_command(
    state,
    command,
    dt,
    n,
    primary_velocity,
    limits,
    max_thrust_n=86.6025403784,
    max_acceleration_mps2=1.0,
    max_relative_speed_mps=None,
):
    """Adjust force before propagation; never silently clip the physical state."""
    primary_velocity = np.asarray(primary_velocity)
    force = np.clip(command.force_n, -50.0, 50.0)
    magnitude = float(np.linalg.norm(force))
    if magnitude > max_thrust_n:
        force *= max_thrust_n / magnitude
    torque = np.clip(command.torque_nm, -20.0, 20.0)
    drift = (propagate_chaser(state, dt, n, Command()).velocity - state.velocity) / dt
    # Brake toward the envelope when it narrows. Holding the current velocity
    # would leave no feasible baseline once the stopping-distance cap decreases.
    absolute_velocity = state.velocity + primary_velocity
    desired_velocity = limit_velocity(absolute_velocity, limits) - primary_velocity
    if max_relative_speed_mps is not None:
        speed = np.linalg.norm(desired_velocity)
        if speed > max_relative_speed_mps:
            desired_velocity *= max_relative_speed_mps / speed
    desired_acceleration = (desired_velocity - state.velocity) / dt
    acceleration_magnitude = float(np.linalg.norm(desired_acceleration))
    if acceleration_magnitude > max_acceleration_mps2:
        desired_acceleration *= max_acceleration_mps2 / acceleration_magnitude
    baseline = np.clip((desired_acceleration - drift) * state.mass_kg, -50.0, 50.0)
    baseline_magnitude = float(np.linalg.norm(baseline))
    if baseline_magnitude > max_thrust_n:
        baseline *= max_thrust_n / baseline_magnitude

    def feasible(candidate):
        velocity = state.velocity + (drift + candidate / state.mass_kg) * dt + primary_velocity
        acceleration = drift + candidate / state.mass_kg
        relative_ok = (
            max_relative_speed_mps is None
            or np.linalg.norm(velocity - primary_velocity) <= max_relative_speed_mps + 1e-9
        )
        return (
            relative_ok
            and np.linalg.norm(acceleration) <= max_acceleration_mps2 + 1e-9
            and np.allclose(velocity, limit_velocity(velocity, limits), atol=1e-9, rtol=0)
        )

    # Bisection stays within both the convex velocity envelope and actuator bounds.
    if not feasible(force):
        if feasible(baseline):
            low, high = 0.0, 1.0
            for _ in range(30):
                fraction = (low + high) / 2
                candidate = baseline + fraction * (force - baseline)
                if feasible(candidate):
                    low = fraction
                else:
                    high = fraction
            force = baseline + low * (force - baseline)
        else:
            force = baseline  # Best bounded braking; runner checks actual hard limits.
    adjusted = not np.allclose(force, command.force_n) or not np.allclose(torque, command.torque_nm)
    return Command(force_n=force, torque_nm=torque), adjusted
