"""Anomaly-injection tests: observed-vs-truth separation, impulse, priority change."""

from __future__ import annotations

import numpy as np

from app.schemas.docking import AnomalyConfig, AnomalyType
from app.simulation.anomalies import AnomalyManager
from app.simulation.dynamics import RigidBodyState


def _truth(position=(50.0, 0.0, 0.0), velocity=(0.0, 0.0, 0.0)) -> RigidBodyState:
    return RigidBodyState(
        position=np.asarray(position, dtype=float),
        velocity=np.asarray(velocity, dtype=float),
    )


def test_sensor_dropout_corrupts_observed_but_not_truth():
    manager = AnomalyManager(
        [AnomalyConfig(type=AnomalyType.SENSOR_DROPOUT, step=3, duration_steps=3)],
        rng=np.random.default_rng(0),
    )
    truth = _truth()
    observed, details = manager.advance(3, truth)
    assert len(details) == 1
    assert details[0].type is AnomalyType.SENSOR_DROPOUT
    # Observed position is corrupted; truth is untouched.
    assert not np.array_equal(observed.position, truth.position)
    assert np.array_equal(truth.position, np.array([50.0, 0.0, 0.0]))

    # After the window the reported state matches truth again.
    for step in range(4, 8):
        observed, details = manager.advance(step, truth)
    assert np.array_equal(observed.position, truth.position)


def test_dropout_withhold_freezes_reported_state():
    manager = AnomalyManager(
        [AnomalyConfig(type=AnomalyType.SENSOR_DROPOUT, step=1, duration_steps=2, corrupt=False)],
        rng=np.random.default_rng(0),
    )
    truth = _truth()
    observed, _ = manager.advance(1, truth)
    frozen = observed.position.copy()
    truth.position = np.array([49.0, 1.0, 0.0])  # truth moved
    observed, _ = manager.advance(2, truth)
    assert np.array_equal(observed.position, frozen)
    assert np.array_equal(truth.position, np.array([49.0, 1.0, 0.0]))


def test_velocity_impulse_hits_truth():
    manager = AnomalyManager(
        [AnomalyConfig(type=AnomalyType.VELOCITY_IMPULSE, step=2, impulse_mps=[0.5, 0.0, 0.0])],
        rng=np.random.default_rng(0),
    )
    truth = _truth()
    observed, details = manager.advance(2, truth)
    assert len(details) == 1
    assert truth.velocity[0] == 0.5
    assert observed.velocity[0] == 0.5
    # Not applied twice.
    observed, details = manager.advance(3, truth)
    assert truth.velocity[0] == 0.5


def test_priority_change_surfaces():
    manager = AnomalyManager(
        [AnomalyConfig(type=AnomalyType.PRIORITY_CHANGE, step=5, priority_change="abort")],
        rng=np.random.default_rng(0),
    )
    assert manager.priority_change_active(4) is None
    manager.advance(5, _truth())
    assert manager.priority_change_active(5) == "abort"
    assert manager.priority_change_active(100) == "abort"  # persists
