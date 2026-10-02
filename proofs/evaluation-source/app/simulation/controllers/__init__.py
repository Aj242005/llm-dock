"""Low-level controllers. All implement the ``Controller`` protocol.

PID, LQR, and the RL/PPO policy controller are interchangeable behind
``build_controller`` — the runner never knows which one is running.
"""

from app.simulation.controllers.base import Controller, ControlContext, build_controller
from app.simulation.controllers.lqr import LqrController
from app.simulation.controllers.pid import PidController
from app.simulation.controllers.rl import RlController

__all__ = ["Controller", "ControlContext", "build_controller", "LqrController", "PidController", "RlController"]
