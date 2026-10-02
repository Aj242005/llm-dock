"""Controller interface.

Every low-level controller (PID, LQR, and the future RL/PPO policy) implements
the ``Controller`` protocol below. The simulation loop only ever talks to:

    controller.compute(state, subgoal, dt) -> Command

No other subsystem knows which concrete controller is running, so a third
implementation (RL policy) can be dropped into ``app/simulation/controllers/``
and registered in the ``build_controller`` factory without touching the loop.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np

from app.schemas.docking import ControllerType
from app.schemas.events import LlmSubgoal
from app.simulation.dynamics import Command, RigidBodyState, quat_conjugate, quat_multiply


def approach_force(state, subgoal, dt, n=0.0):
    """Track an approach velocity continuously; brake as the port distance closes.

    Position waypoints describe direction, not mandatory intermediate stops.
    The runner independently applies thrust, speed and stopping-distance limits.
    """
    offset = np.asarray(subgoal.target_position_m) - state.position
    distance = float(np.linalg.norm(offset))
    requested = max(subgoal.closing_speed_mps, float(np.linalg.norm(subgoal.target_velocity_mps)))
    if requested < 1e-9:
        requested = min(2.0, np.sqrt(0.1 * distance))
    speed = min(requested, 0.2 * distance)
    desired = offset / max(distance, 1e-9) * speed
    x, _, z = state.position
    vx, vy, _ = state.velocity
    drift = np.array([2 * n * vy + 3 * n * n * x, -2 * n * vx, -n * n * z])
    return state.mass_kg * ((desired - state.velocity) / max(1.0, dt) - drift)


def attitude_error(state, subgoal):
    """Shortest current-to-target attitude error and body-rate error."""
    error = quat_multiply(quat_conjugate(np.asarray(subgoal.target_orientation_quat)), state.quat)
    if error[0] < 0:
        error = -error
    length = np.linalg.norm(error[1:])
    rotation = error[1:] * (2 * np.arctan2(length, error[0]) / max(length, 1e-12))
    return rotation, state.omega - np.asarray(subgoal.target_angular_velocity_radps)


def attitude_torque(state, subgoal):
    """Damp a tumble first, then slew toward the port at a bounded body rate."""
    rotation, _ = attitude_error(state, subgoal)
    if np.linalg.norm(state.omega) > 0.1:
        # Dissipate rotational energy before trying to chase a moving attitude.
        desired_rate = np.zeros(3)
    else:
        desired_rate = -rotation * 0.15 + np.asarray(subgoal.target_angular_velocity_radps)
        speed = np.linalg.norm(desired_rate)
        if speed > 0.05:
            desired_rate *= 0.05 / speed
    return np.clip(state.inertia * (desired_rate - state.omega) * 0.5, -20, 20)


class ControlContext:
    """Per-controller bookkeeping a controller may keep between calls.

    PID uses it for the integral term; LQR ignores everything except the
    gain matrix (which it caches on construction). A future RL controller
    would hold its policy weights here.
    """

    def __init__(self) -> None:
        # PID integral of position error [m·s], reset per sub-goal.
        self.position_integral: np.ndarray = np.zeros(3)
        self.last_position_error: np.ndarray | None = None
        # Closed-loop gain for LQR (computed once at build time, cached).
        self.lqr_gain: np.ndarray | None = None
        # LQR continuous-time solver working matrices (cached).
        self.lqr_solver_state: tuple | None = None


class Controller(ABC):
    """Common interface for low-level controllers."""

    name: ControllerType

    def __init__(self, mass_kg: float, inertia: np.ndarray) -> None:
        self.mass_kg = float(mass_kg)
        self.inertia = np.asarray(inertia, dtype=float).copy()

    @abstractmethod
    def compute(
        self, state: RigidBodyState, subgoal: LlmSubgoal, dt: float, ctx: ControlContext
    ) -> Command:
        """Compute the thruster command to track ``subgoal`` from ``state``."""

    @abstractmethod
    def reset(self, ctx: ControlContext) -> None:
        """Reset internal state (called when a new LLM sub-goal arrives)."""


def build_controller(
    controller_type: ControllerType,
    mass_kg: float,
    inertia: np.ndarray,
    n: float,
) -> Controller:
    """Factory: maps a ControllerType to a concrete Controller instance.

    A future RL/PPO controller adds an ``elif controller_type is ControllerType.RL``
    branch here (plus the enum member in the schema). Nothing else changes.
    """
    if isinstance(controller_type, str):
        controller_type = ControllerType(controller_type)

    if controller_type is ControllerType.PID:
        from app.simulation.controllers.pid import PidController

        return PidController(mass_kg=mass_kg, inertia=inertia)
    if controller_type is ControllerType.LQR:
        from app.simulation.controllers.lqr import LqrController

        return LqrController(mass_kg=mass_kg, inertia=inertia, n=n)
    if controller_type is ControllerType.RL:
        from app.simulation.controllers.rl import RlController

        return RlController(mass_kg=mass_kg, inertia=inertia)
    raise ValueError(f"Unknown controller type: {controller_type}")
