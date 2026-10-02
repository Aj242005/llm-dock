"""Low-level controller tests: bounded commands, reset semantics, convergence."""

from __future__ import annotations

import numpy as np

from app.schemas.events import LlmSubgoal
from app.simulation.controllers import ControlContext, build_controller
from app.simulation.controllers.lqr import MAX_FORCE_N as LQR_MAX_FORCE_N
from app.simulation.controllers.pid import MAX_FORCE_N as PID_MAX_FORCE_N
from app.simulation.dynamics import DEFAULT_INERTIA, RigidBodyState

SUBGOAL = LlmSubgoal(
    target_position_m=[0.0, 0.0, 0.0],
    target_velocity_mps=[0.0, 0.0, 0.0],
    closing_speed_mps=0.0,
    rationale="test",
)


def _make_state(position=(10.0, 0.0, 0.0), velocity=(0.0, 0.0, 0.0)) -> RigidBodyState:
    return RigidBodyState(
        position=np.asarray(position, dtype=float),
        velocity=np.asarray(velocity, dtype=float),
        inertia=DEFAULT_INERTIA.copy(),
    )


def _make_controllers():
    pid = build_controller("pid", 500.0, DEFAULT_INERTIA.copy(), n=1.1e-3)
    lqr = build_controller("lqr", 500.0, DEFAULT_INERTIA.copy(), n=1.1e-3)
    return pid, lqr


def test_pid_command_bounded():
    pid, _ = _make_controllers()
    cmd = pid.compute(_make_state(), SUBGOAL, 1.0, ControlContext())
    assert np.all(np.abs(cmd.force_n) <= PID_MAX_FORCE_N + 1e-9)
    assert np.all(np.abs(cmd.torque_nm) <= 20.0 + 1e-9)


def test_lqr_command_bounded():
    _, lqr = _make_controllers()
    cmd = lqr.compute(_make_state(), SUBGOAL, 1.0, ControlContext())
    assert np.all(np.abs(cmd.force_n) <= LQR_MAX_FORCE_N + 1e-9)
    assert np.all(np.abs(cmd.torque_nm) <= 20.0 + 1e-9)


def test_pid_reset_clears_integral():
    pid, _ = _make_controllers()
    ctx = ControlContext()
    pid.compute(_make_state(), SUBGOAL, 1.0, ctx)
    assert np.any(ctx.position_integral != 0.0)
    pid.reset(ctx)
    assert np.all(ctx.position_integral == 0.0)


def test_pid_pushes_toward_origin():
    """From +X with a zero target, the force must point in -X."""
    pid, _ = _make_controllers()
    cmd = pid.compute(_make_state(position=(10.0, 0.0, 0.0)), SUBGOAL, 1.0, ControlContext())
    assert cmd.force_n[0] < 0.0


def test_pid_handles_anti_aligned_attitude():
    """180°-misaligned start must still command a nonzero torque (no zero-cmd bug)."""
    pid, _ = _make_controllers()
    state = _make_state(position=(10.0, 0.0, 0.0))
    # Body +X pointing away from the closing direction.
    state.quat = np.array([0.0, 0.0, 1.0, 0.0])  # 180° about +Y
    cmd = pid.compute(state, SUBGOAL, 1.0, ControlContext())
    assert np.linalg.norm(cmd.torque_nm) > 0.0
    assert np.linalg.norm(cmd.force_n) > 0.0


def test_lqr_gain_is_stabilizing():
    """The closed-loop A - B K must be Hurwitz (all eigenvalues < 0 real part)."""
    _, lqr = _make_controllers()
    K = lqr.gain
    A, B, _, _ = lqr._assembly
    eig = np.linalg.eigvals(A - B @ K)
    assert np.max(eig.real) < -1e-6
