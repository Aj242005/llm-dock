"""Read-only geometry tools. Only the runner can apply actuator commands."""

import numpy as np
from langchain_core.tools import tool


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
        }

    @tool
    def inspect_capture_gate() -> dict:
        """Read the shared 1.25 metre gate and speed, attitude, rotation checks."""
        return snapshot.capture

    @tool
    def inspect_actuators() -> dict:
        """Read thruster limits and the configured primary and secondary motion envelopes."""
        return {
            "force_per_axis_n": 50.0,
            "torque_per_axis_nm": 20.0,
            "primary_limits": snapshot.primary_limits,
            "secondary_limits": snapshot.secondary_limits,
            "minimum_speed_rule": "Transit preference; braking and capture may use zero speed.",
        }

    @tool
    def inspect_rl_heuristic() -> dict:
        """Read the learned PPO policy proposal, if a trained model is configured."""
        return {
            "available": snapshot.rl_advisor is not None,
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
        }

    return [
        measure_distance,
        inspect_capture_gate,
        inspect_actuators,
        inspect_rl_heuristic,
        preview_maneuver,
    ]
