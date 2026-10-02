"""Read-only geometry tools. Only the runner can apply actuator commands."""

import numpy as np
from langchain_core.tools import tool

from app.schemas.docking import MotionLimits
from app.simulation.safety import limit_velocity


def docking_tools(snapshot):
    """Bind tools to one fresh state snapshot; the model cannot alter telemetry."""

    @tool
    def measure_distance() -> dict:
        """Measure docking-port separation, relative speed, and closing speed in SI units."""
        position = np.asarray(snapshot.position_m)
        velocity = np.asarray(snapshot.velocity_mps)
        distance = float(np.linalg.norm(position))
        return {
            "distance_m": distance,
            "relative_speed_mps": float(np.linalg.norm(velocity)),
            "closing_speed_mps": -float(np.dot(position, velocity)) / max(distance, 1e-9),
            "attitude_error_deg": float(
                np.degrees(2 * np.arccos(np.clip(abs(snapshot.orientation_quat[0]), 0, 1)))
            ),
            "angular_speed_radps": float(np.linalg.norm(snapshot.angular_velocity_radps)),
        }

    @tool
    def inspect_capture_gate() -> dict:
        """Read the shared centimetre capture gate and speed, attitude, rotation checks."""
        return snapshot.capture

    @tool
    def inspect_actuators() -> dict:
        """Read thruster limits and the configured primary and secondary motion envelopes."""
        return {
            "force_per_axis_n": 50.0,
            "max_total_thrust_n": snapshot.max_thrust_n,
            "max_acceleration_mps2": snapshot.max_acceleration_mps2,
            "mass_kg": snapshot.mass_kg,
            "torque_per_axis_nm": 20.0,
            "current_approach_speed_limit_mps": snapshot.approach_speed_limit_mps,
            "capture_speed_mps": snapshot.capture_speed_mps,
            "target_angular_speed_limit_radps": snapshot.max_angular_speed_radps,
            "primary_limits": snapshot.primary_limits,
            "secondary_limits": snapshot.secondary_limits,
            "minimum_speed_rule": "Transit preference; braking and capture may use zero speed.",
        }

    @tool
    def inspect_rl_heuristic() -> dict:
        """Read the learned PPO policy proposal, if a trained model is configured."""
        return {
            "available": snapshot.rl_advisor is not None,
            "status": "available" if snapshot.rl_advisor else snapshot.rl_advisor_status,
            "reason": snapshot.rl_advisor_reason,
            "proposal": snapshot.rl_advisor.model_dump() if snapshot.rl_advisor else None,
        }

    @tool
    def preview_maneuver(target_position_m: list[float], target_velocity_mps: list[float]) -> dict:
        """Compare a proposed target with current range and configured speed limits without moving."""
        if len(target_position_m) != 3 or len(target_velocity_mps) != 3:
            return {"error": "Positions and velocities must have three components"}
        if not np.isfinite(target_position_m + target_velocity_mps).all():
            return {"error": "Components must be finite"}
        return {
            "target_range_m": float(np.linalg.norm(target_position_m)),
            "reduces_range": bool(np.linalg.norm(target_position_m) < snapshot.range_m),
            "target_speed_mps": float(np.linalg.norm(target_velocity_mps)),
            "within_motion_limits": bool(
                np.allclose(
                    np.asarray(target_velocity_mps) + snapshot.primary_velocity_mps,
                    limit_velocity(
                        np.asarray(target_velocity_mps) + snapshot.primary_velocity_mps,
                        MotionLimits(**snapshot.secondary_limits),
                    ),
                )
            ),
        }

    return [
        measure_distance,
        inspect_capture_gate,
        inspect_actuators,
        inspect_rl_heuristic,
        preview_maneuver,
    ]
