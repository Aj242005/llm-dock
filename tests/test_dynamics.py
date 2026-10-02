"""Unit tests for the dynamics module: quaternion algebra, mean motion,
phase classification, and the CW + attitude propagator."""

from __future__ import annotations

import math

import numpy as np
import pytest

from app.simulation.dynamics import (
    MU_EARTH_M3_S2,
    Command,
    RigidBodyState,
    attitude_error_deg,
    classify_phase,
    mean_motion_radps,
    propagate_chaser,
    quat_conjugate,
    quat_from_axis_angle,
    quat_multiply,
    quat_normalize,
    quat_rotate,
)


def test_mean_motion_matches_formula():
    a = 6_878_000.0
    n = mean_motion_radps(a)
    assert n == pytest.approx(math.sqrt(MU_EARTH_M3_S2 / a**3))
    # ~1.1e-3 rad/s for LEO.
    assert 1.0e-3 < n < 1.3e-3


def test_mean_motion_explicit_override_is_used_by_runner_path():
    # Just sanity-check the module-level formula; the explicit override is
    # exercised end-to-end in the runner tests.
    assert mean_motion_radps(6_878_000.0) > 0


def test_quat_rotate_roundtrip():
    q = quat_from_axis_angle(np.array([0.0, 0.0, 1.0]), math.pi / 2.0)
    v = np.array([1.0, 0.0, 0.0])
    rotated = quat_rotate(q, v)
    assert rotated == pytest.approx([0.0, 1.0, 0.0], abs=1e-9)


def test_quat_multiply_is_identity_for_conjugate():
    q = quat_normalize(np.array([0.3, 0.4, 0.5, 0.6]))
    product = quat_multiply(q, quat_conjugate(q))
    assert product == pytest.approx([1.0, 0.0, 0.0, 0.0], abs=1e-9)


def test_attitude_error_deg():
    q1 = np.array([1.0, 0.0, 0.0, 0.0])
    q2 = quat_from_axis_angle(np.array([0.0, 1.0, 0.0]), math.pi / 2.0)
    assert attitude_error_deg(q1, q2) == pytest.approx(90.0, abs=1e-6)


def test_classify_phase_boundaries():
    assert classify_phase(2000.0) == "far_rendezvous"
    assert classify_phase(1000.0) == "closing"
    assert classify_phase(30.0) == "final_approach"
    assert classify_phase(5.0) == "proximity"
    assert classify_phase(0.1) == "proximity"
    assert classify_phase(0.0) == "docked"


def test_propagation_without_control_stays_bounded():
    """Free CW drift must stay bounded (oscillatory, not divergent)."""
    n = mean_motion_radps(6_878_000.0)
    state = RigidBodyState(position=np.array([100.0, 0.0, 0.0]))
    max_range = 0.0
    for _ in range(200):
        state = propagate_chaser(state, 1.0, n)
        max_range = max(max_range, float(np.linalg.norm(state.position)))
    # CW drift from pure radial offset oscillates within ~2x the initial range.
    assert max_range < 400.0
    assert np.all(np.isfinite(state.position))


def test_propagation_applies_force():
    n = mean_motion_radps(6_878_000.0)
    state = RigidBodyState(position=np.array([10.0, 0.0, 0.0]), velocity=np.zeros(3))
    cmd = Command(force_n=np.array([50.0, 0.0, 0.0]))
    state = propagate_chaser(state, 1.0, n, cmd)
    # 50 N on 500 kg for 1 s -> ~0.1 m/s of Δv (plus CW coupling).
    assert state.velocity[0] == pytest.approx(0.1, abs=0.01)


def test_rotational_integration_does_not_blow_up():
    """Gyroscopic Euler must not compound exponentially under sustained spin.

    Without sub-stepping, explicit Euler on the ω×(Iω) term amplifies the
    transverse spin rate by ~√(1+(ω·dt)²) per step — with ω=2 rad/s and
    dt=1 s that compounds to ~1e24 over 300 steps. Sub-stepping keeps |ω|
    growing only linearly under the small applied torque.
    """
    n = mean_motion_radps(6_878_000.0)
    state = RigidBodyState(
        position=np.zeros(3),
        quat=quat_from_axis_angle(np.array([0.0, 1.0, 0.0]), 0.3),
        omega=np.array([2.0, 0.0, 0.0]),
    )
    cmd = Command(torque_nm=np.array([0.0, 0.5, 0.0]))
    max_omega = 0.0
    for _ in range(300):
        state = propagate_chaser(state, 1.0, n, cmd)
        max_omega = max(max_omega, float(np.linalg.norm(state.omega)))
    assert max_omega < 20.0


def test_propagation_keeps_quat_normalized():
    n = mean_motion_radps(6_878_000.0)
    state = RigidBodyState(
        position=np.zeros(3),
        quat=quat_from_axis_angle(np.array([1.0, 0.0, 0.0]), 0.7),
        omega=np.array([0.1, 0.0, 0.0]),
    )
    for _ in range(50):
        state = propagate_chaser(state, 1.0, n)
    assert np.linalg.norm(state.quat) == pytest.approx(1.0, abs=1e-9)
