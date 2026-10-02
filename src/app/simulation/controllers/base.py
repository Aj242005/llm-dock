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
from app.simulation.dynamics import Command, RigidBodyState


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
