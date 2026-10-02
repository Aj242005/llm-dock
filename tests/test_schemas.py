"""Schema contract tests: fast-fail validation of malformed requests."""

from __future__ import annotations

import pytest
from conftest import make_request
from pydantic import BaseModel, ValidationError

from app.schemas.docking import (
    AnomalyConfig,
    AnomalyType,
    DockingPhase,
    OrbitalElements,
    SatelliteState,
    SimulateRequest,
    SimulationConfig,
)
from app.schemas.events import AnomalyDetail, DockingEvent, LlmSubgoal, TelemetryEvent


def test_valid_request_accepts_secondary_inheriting_primary_orbit():
    orbit = OrbitalElements(semi_major_axis_m=6_878_000.0)
    primary = SatelliteState(orbital_elements=orbit)
    secondary = SatelliteState(position_m=[10.0, 0.0, 0.0])  # no orbital elements
    req = SimulateRequest(primary=primary, secondary=secondary, config=SimulationConfig())
    # The validator inherits the primary's orbit onto the secondary.
    assert req.secondary.orbital_elements is orbit


@pytest.mark.parametrize("distance", [5.0, 7.5, 10.0])
def test_initial_separation_includes_both_endpoints(distance):
    request = make_request(position=(distance, 0, 0), initial_separation_range_m=(5, 10))
    assert request.secondary.position_m[0] == distance


@pytest.mark.parametrize("position", [(4.99, 0, 0), (10.01, 0, 0), (0, 0, -11)])
def test_initial_separation_rejects_outside_band(position):
    with pytest.raises(ValidationError, match="Initial port separation"):
        make_request(position=position, initial_separation_range_m=(5, 10))


@pytest.mark.parametrize("bounds", [(0, 10), (-5, 10), (10, 5)])
def test_invalid_initial_separation_bounds_are_rejected(bounds):
    with pytest.raises(ValidationError, match="Initial separation bounds"):
        make_request(position=(7.5, 0, 0), initial_separation_range_m=bounds)


def test_initial_separation_uses_both_positions_in_three_dimensions():
    SimulateRequest(
        primary=SatelliteState(
            position_m=[100, 200, 300],
            orbital_elements=OrbitalElements(semi_major_axis_m=6_878_000),
        ),
        secondary=SatelliteState(position_m=[103, 204, 300]),
        config=SimulationConfig(initial_separation_range_m=(5, 10)),
    )


@pytest.mark.parametrize("distance", [0.02, 0.035, 100, 1000])
def test_full_starting_distance_envelope_accepts_boundaries(distance):
    assert make_request(position=(distance, 0, 0)).secondary.position_m[0] == distance


@pytest.mark.parametrize("distance", [0, 0.0199, 1000.001])
def test_starting_distance_limits_apply_without_custom_bounds(distance):
    with pytest.raises(ValidationError, match="Initial port separation"):
        make_request(position=(distance, 0, 0))


def test_two_centimetre_boundary_with_translated_primary():
    SimulateRequest(
        primary=SatelliteState(
            position_m=[100, 200, 300],
            orbital_elements=OrbitalElements(semi_major_axis_m=6_878_000),
        ),
        secondary=SatelliteState(position_m=[100.02, 200, 300]),
        config=SimulationConfig(initial_separation_range_m=(0.02, 1000)),
    )


@pytest.mark.parametrize("bounds", [(0.01, 1000), (0.02, 1001)])
def test_custom_bounds_cannot_exceed_distance_envelope(bounds):
    with pytest.raises(ValidationError, match="Initial separation bounds"):
        make_request(initial_separation_range_m=bounds)


def test_request_without_orbit_is_rejected():
    with pytest.raises(ValidationError):
        SimulateRequest(
            primary=SatelliteState(),
            secondary=SatelliteState(),
            config=SimulationConfig(),
        )


def test_non_unit_quaternion_is_rejected():
    orbit = OrbitalElements(semi_major_axis_m=6_878_000.0)
    # norm of [0.5, 0.5, 0.5, 0.0] is sqrt(0.75) != 1
    with pytest.raises(ValidationError):
        SatelliteState(
            position_m=[1.0, 0.0, 0.0],
            orientation_quat=[0.5, 0.5, 0.5, 0.0],
            orbital_elements=orbit,
        )


def test_velocity_impulse_requires_impulse_vector():
    with pytest.raises(ValidationError):
        AnomalyConfig(type=AnomalyType.VELOCITY_IMPULSE, step=5)


def test_sensor_dropout_requires_duration():
    with pytest.raises(ValidationError):
        AnomalyConfig(type=AnomalyType.SENSOR_DROPOUT, step=5)


def test_extra_fields_rejected():
    with pytest.raises(ValidationError):
        make_request(bogus_field=123)


def test_llm_subgoal_parses_from_dict():
    subgoal = LlmSubgoal.model_validate(
        {
            "target_position_m": [1.0, 2.0, 3.0],
            "target_velocity_mps": [0.1, 0.0, 0.0],
            "closing_speed_mps": 0.5,
            "rationale": "test",
        }
    )
    assert subgoal.target_position_m == [1.0, 2.0, 3.0]


def test_llm_subgoal_rejects_negative_closing_speed():
    with pytest.raises(ValidationError):
        LlmSubgoal(
            target_position_m=[0.0, 0.0, 0.0],
            target_velocity_mps=[0.0, 0.0, 0.0],
            closing_speed_mps=-1.0,
        )


def test_anomaly_detail_roundtrip():
    detail = AnomalyDetail(
        type=AnomalyType.VELOCITY_IMPULSE,
        detail="boom",
        step=7,
        impulse_mps=[0.5, 0.0, 0.0],
    )
    assert detail.priority_change is None
    assert detail.sensor is None


def _telemetry() -> TelemetryEvent:
    return TelemetryEvent(
        step=0,
        sim_time_s=0.0,
        phase=DockingPhase.CLOSING,
        position_m=[50.0, 0.0, 0.0],
        velocity_mps=[0.0, 0.0, 0.0],
        range_m=50.0,
        closing_speed_mps=0.0,
        fuel_pct=100.0,
        controller="lqr",
    )


def test_docking_event_discriminates_on_type():
    class _Envelope(BaseModel):
        event: DockingEvent

    evt = _telemetry()
    parsed = _Envelope.model_validate({"event": evt.model_dump(mode="json")}).event
    assert isinstance(parsed, TelemetryEvent)
    assert parsed.type == "telemetry"


def test_every_event_carries_wire_envelope():
    """The frontend contract: schema_version + primary frame + running metrics."""
    evt = _telemetry()
    assert evt.schema_version == "1.0"
    assert evt.session_id == ""  # stamped by Session.append
    assert evt.primary.position_m == [0.0, 0.0, 0.0]
    assert evt.primary.orientation_quat == [1.0, 0.0, 0.0, 0.0]
    assert evt.metrics_so_far.delta_v_mps == 0.0
    assert evt.metrics_so_far.total_llm_calls == 0


def test_anomaly_event_requires_clock_fields():
    """Anomaly events share the step/sim_time envelope with the rest."""
    from app.schemas.events import AnomalyEvent

    evt = AnomalyEvent(
        step=7,
        sim_time_s=7.0,
        anomaly=AnomalyDetail(
            type=AnomalyType.VELOCITY_IMPULSE,
            detail="boom",
            step=7,
            impulse_mps=[0.5, 0.0, 0.0],
        ),
    )
    assert evt.schema_version == "1.0"
    assert evt.step == 7


async def test_session_stamps_session_id_on_events():
    from app.schemas.events import HeartbeatEvent
    from app.sessions.store import Session

    session = Session(session_id="abc123")
    evt = HeartbeatEvent(step=1, sim_time_s=1.0)
    await session.append(evt)
    assert evt.session_id == "abc123"
    assert session.event_log[0].session_id == "abc123"
