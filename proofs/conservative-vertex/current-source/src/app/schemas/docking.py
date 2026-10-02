"""Request, state and summary schemas for the docking API.

Units are explicit and consistent everywhere:
  * positions  : meters (m), Hill/RSW frame, origin at the primary satellite
  * velocities : meters/second (m/s)
  * quaternions: [w, x, y, z] (w = scalar part first)
  * angular    : radians/second (rad/s)
  * fuel       : percentage remaining [0..100]
  * time       : seconds (s) for the step interval; total elapsed sim time in s
Fields are validated so a malformed request fails fast with a 422 before a
session is created.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

# ---------------------------------------------------------------------------
# Primitive types
# ---------------------------------------------------------------------------


def _valid_unit_quaternion(v: list[float]) -> bool:
    if len(v) != 4:
        return False
    if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in v):
        return False
    return abs(math.sqrt(sum(x * x for x in v)) - 1.0) < 1e-3


Vector3 = Annotated[
    list[float],
    Field(min_length=3, max_length=3, description="3-vector, e.g. position [x,y,z] in meters"),
]

Quaternion = Annotated[
    list[float],
    Field(min_length=4, max_length=4, description="Unit quaternion [w,x,y,z]"),
]


class ControllerType(StrEnum):
    """Selectable low-level controllers."""

    PID = "pid"
    LQR = "lqr"
    RL = "rl"  # trained Stable-Baselines3 PPO policy (see app/simulation/rl/)


class AnomalyType(StrEnum):
    """Supported injectable anomalies.

    * SENSOR_DROPOUT  -> corrupt or withhold a sensor reading for `duration_steps`
    * VELOCITY_IMPULSE -> apply an unmodeled velocity impulse (m/s)
    * PRIORITY_CHANGE  -> inject a "priority change / abort" instruction that the
                          LLM layer must interpret (it is *not* fed to the controller)
    """

    SENSOR_DROPOUT = "sensor_dropout"
    VELOCITY_IMPULSE = "velocity_impulse"
    PRIORITY_CHANGE = "priority_change"


class DockingPhase(StrEnum):
    """Docking phase classification by relative range (see README)."""

    FAR_RENDEZVOUS = "far_rendezvous"  # > 1000 m
    CLOSING = "closing"  # 1000 – 30 m
    FINAL_APPROACH = "final_approach"  # 30 – 5 m
    PROXIMITY = "proximity"  # 5 – 0 m
    DOCKED = "docked"  # within position + attitude tolerance


class FailureReason(StrEnum):
    CANCELLED = "cancelled"
    LIMIT_EXCEEDED = "limit_exceeded"
    FUEL_EXHAUSTED = "fuel_exhausted"
    MAX_STEPS_EXCEEDED = "max_steps_exceeded"
    MAX_TIME_EXCEEDED = "max_time_exceeded"
    DIVERGED = "diverged"  # relative range exceeded max_range_m (unstable/unrecoverable)
    UNRECOVERABLE_ANOMALY = "unrecoverable_anomaly"


class StopReason(StrEnum):
    DOCKED = "docked"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Orbital / state schemas
# ---------------------------------------------------------------------------


class OrbitalElements(BaseModel):
    """Classical orbital elements of a satellite; used to derive mean motion n.

    ``mean_motion_radps`` is optional — if present it overrides the value
    computed from ``semi_major_axis_m`` + gravitational parameter. This lets
    callers model unusual orbits (e.g. non-circular) without changing physics.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    semi_major_axis_m: float = Field(gt=0, description="Semi-major axis of the orbit [m]")
    eccentricity: float = Field(default=0.0, ge=0.0, lt=1.0)
    inclination_deg: float = Field(default=0.0, ge=-90.0, le=180.0)
    raan_deg: float = Field(default=0.0)
    arg_periapsis_deg: float = Field(default=0.0)
    true_anomaly_deg: float = Field(default=0.0)
    mean_motion_radps: float | None = Field(
        default=None, gt=0.0, description="Optional explicit mean motion [rad/s]"
    )


class MotionLimits(BaseModel):
    """Speed limits in the local frame; Z is vertical, XY is horizontal."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    min_speed_mps: float = Field(default=0.0, ge=0.0)
    max_speed_mps: float = Field(default=2.0, gt=0.0, le=20.0)
    max_horizontal_speed_mps: float = Field(default=2.0, gt=0.0, le=20.0)
    max_vertical_speed_mps: float = Field(default=1.0, gt=0.0, le=20.0)

    @model_validator(mode="after")
    def validate_minimum(self):
        if self.min_speed_mps > min(self.max_speed_mps, self.max_horizontal_speed_mps):
            raise ValueError("Minimum transit speed must fit the speed envelope")
        return self


class SatelliteState(BaseModel):
    """Full inertial-ish state of one satellite.

    Positions/velocities are the *relative Hill/RSW* state when used for the
    secondary (chaser) — i.e. relative to the primary — while the primary is
    always at [0,0,0] in the Hill frame. The primary additionally carries an
    inertial position (ECI) that the future frontend can use to anchor the
    camera/orbit rendering.
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    position_m: Vector3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    velocity_mps: Vector3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation_quat: Quaternion = Field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    angular_velocity_radps: Vector3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    fuel_remaining_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    orbital_elements: OrbitalElements | None = None
    inertia_kg_m2: list[float] | None = Field(
        default=None,
        min_length=3,
        max_length=3,
        description="Principal moments of inertia [Ix, Iy, Iz] in kg·m² (defaults used if unset)",
    )
    mass_kg: float = Field(default=500.0, gt=0.0)
    name: str = Field(default="Spacecraft", min_length=1, max_length=80)
    capture_radius_m: float = Field(default=1.25, gt=0.0, le=1.25)
    motion_limits: MotionLimits = Field(default_factory=MotionLimits)
    # Inertial (ECI) position of the primary, for orbit/camera rendering.
    inertial_position_m: Vector3 | None = Field(default=None, min_length=3, max_length=3)

    @model_validator(mode="after")
    def _validate(self) -> SatelliteState:
        if not _valid_unit_quaternion(self.orientation_quat):
            raise ValueError("orientation_quat must be a unit quaternion (norm within 1e-3 of 1)")
        if self.inertia_kg_m2 is not None and any(v <= 0 for v in self.inertia_kg_m2):
            raise ValueError("Moments of inertia must be positive")
        return self


# ---------------------------------------------------------------------------
# Simulation config
# ---------------------------------------------------------------------------


class AnomalyConfig(BaseModel):
    """A single anomaly to inject. ``None`` per type means "not injected"."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    type: AnomalyType
    step: int = Field(ge=0, description="Physics step index at which the anomaly fires")
    detail: str = Field(
        default="",
        max_length=500,
        description="Free-form detail surfaced in the anomaly event + LLM context",
    )

    # sensor_dropout
    duration_steps: int | None = Field(default=None, ge=1)
    corrupt: bool = Field(
        default=True,
        description="If False, withhold the reading (gap); if True, corrupt it with noise",
    )

    # velocity_impulse
    impulse_mps: list[float] | None = Field(default=None, min_length=3, max_length=3)

    # priority_change
    priority_change: Literal["abort"] | None = Field(
        default=None, description="'abort' means the LLM is told the mission is aborted"
    )

    @model_validator(mode="after")
    def _validate(self) -> AnomalyConfig:
        if self.type is AnomalyType.VELOCITY_IMPULSE and self.impulse_mps is None:
            raise ValueError("velocity_impulse requires impulse_mps [vx,vy,vz]")
        if self.type is AnomalyType.SENSOR_DROPOUT and self.duration_steps is None:
            raise ValueError("sensor_dropout requires duration_steps")
        return self


class SimulationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    controller: ControllerType = ControllerType.LQR
    step_interval_s: float = Field(default=1.0, gt=0.0, le=1.0)
    max_steps: int = Field(default=600, ge=1, le=100_000)
    max_time_s: float | None = Field(default=None, gt=0.0)
    llm_enabled: bool = True
    llm_cadence_steps: int = Field(
        default=10, ge=1, le=1000, description="Re-plan every N physics steps"
    )
    # LLM x RL hybrid: when true, each replan feeds the reasoning layer an
    # advisory sub-goal computed from the trained RL policy (requires the same
    # LLM_DOCKING_RL_MODEL_PATH / _NORMALIZE_PATH artifacts as controller="rl").
    rl_advisor_enabled: bool = Field(
        default=False,
        description="The LLM planner receives a suggestion from the trained RL policy",
    )
    rl_advisor_lookahead_s: float = Field(
        default=4.0,
        gt=0.0,
        le=60.0,
        description="How far ahead the RL advisor projects its commanded acceleration",
    )
    anomalies: list[AnomalyConfig] = Field(default_factory=list, max_length=10)
    # Tolerances for the "docked" condition.
    dock_position_tol_m: float = Field(default=1.25, gt=0.0, le=1.25)
    dock_velocity_tol_mps: float = Field(default=0.1, gt=0.0)
    dock_attitude_tol_deg: float = Field(default=2.0, gt=0.0, le=90.0)
    # Fuel: normalized mass-flow per second of thruster use.
    fuel_consumption_rate_pct_per_s: float = Field(default=0.05, ge=0.0)
    # Divergence guards: fail the run (FailureReason.DIVERGED) if the relative
    # range exceeds ``max_range_m`` or the body rate exceeds ``max_omega_radps``
    # (an unstable policy — e.g. a bad RL checkpoint — can fling the chaser or
    # tumble it; both also protect the integrator from numerical blow-up).
    max_range_m: float | None = Field(default=10_000.0, gt=0.0)
    max_omega_radps: float = Field(default=5.0, gt=0.0)
    # Optional wall-clock delay between SSE events (demo pacing for a watching
    # frontend; 0 = stream as fast as the sim produces events).
    stream_pacing_s: float = Field(default=0.0, ge=0.0, le=1.0)
    seed: int | None = Field(default=None, description="RNG seed for reproducible noise/impulses")
    provider: Literal["vertex", "heuristic", "openai", "openrouter", "groq", "anthropic"] | None = (
        None
    )
    model: str | None = Field(default=None, min_length=1, max_length=120)
    auto_dock: bool = True
    playback_speed: float | None = Field(
        default=None,
        gt=0,
        le=1000,
        description="Simulation seconds per wall second; 1 is real time. None uses legacy stream pacing.",
    )
    max_thrust_n: float = Field(
        default=86.6025403784,
        gt=0,
        le=100,
        description="Maximum total translational thrust in newtons",
    )
    max_acceleration_mps2: float = Field(
        default=1.0,
        gt=0,
        le=1,
        description="Maximum translational acceleration, including orbital drift",
    )
    near_port_speed_mps: float = Field(
        default=0.05,
        gt=0,
        le=0.1,
        description="Relative speed ceiling within five metres, including braking approach",
    )
    planner_reserve_s: float = Field(
        default=5.0,
        ge=0,
        le=120,
        description="Extra stopping-time margin for conservative approaches",
    )
    initial_separation_range_m: tuple[float, float] | None = Field(
        default=None,
        description="Optional inclusive starting port-distance bounds [minimum, maximum] in metres",
    )


# ---------------------------------------------------------------------------
# Request / response
# ---------------------------------------------------------------------------


class SimulateRequest(BaseModel):
    """POST /api/v1/docking/simulate body."""

    model_config = ConfigDict(extra="forbid")

    primary: SatelliteState
    secondary: SatelliteState
    config: SimulationConfig

    @model_validator(mode="after")
    def _validate(self) -> SimulateRequest:
        if self.config.initial_separation_range_m is not None:
            minimum, maximum = self.config.initial_separation_range_m
            if not 0 < minimum <= maximum:
                raise ValueError("Initial separation bounds must satisfy 0 < minimum <= maximum")
            separation = math.dist(self.primary.position_m, self.secondary.position_m)
            if not minimum <= separation <= maximum:
                raise ValueError(
                    f"Initial port separation must be between {minimum:g} and {maximum:g} m "
                    f"(received {separation:.3f} m)"
                )
        for satellite in [self.primary, self.secondary]:
            speed = math.sqrt(sum(v * v for v in satellite.velocity_mps))
            horizontal = math.hypot(*satellite.velocity_mps[:2])
            limits = satellite.motion_limits
            if (
                speed > limits.max_speed_mps
                or horizontal > limits.max_horizontal_speed_mps
                or abs(satellite.velocity_mps[2]) > limits.max_vertical_speed_mps
            ):
                raise ValueError("Initial velocity exceeds spacecraft motion limits")
        if self.secondary.orbital_elements is None and self.primary.orbital_elements is not None:
            # Secondary inherits the primary's orbit (same orbital regime in Hill frame).
            self.secondary.orbital_elements = self.primary.orbital_elements
        if self.primary.orbital_elements is None and self.secondary.orbital_elements is None:
            raise ValueError(
                "At least one satellite must specify orbital_elements so mean motion n can be derived"
            )
        return self


class SimulateResponse(BaseModel):
    """HTTP 202 response returned immediately; the SSE stream carries the rest."""

    session_id: str
    stream_url: str
    summary_url: str


# ---------------------------------------------------------------------------
# Session summary (polling endpoint)
# ---------------------------------------------------------------------------


class Metrics(BaseModel):
    """Accumulated cost/error metrics for the run (evaluation harness data)."""

    delta_v_mps: float = 0.0
    ise: float = 0.0  # integral of squared position error (m²·s)
    max_commanded_thrust_n: float = 0.0
    total_llm_calls: int = 0
    llm_fallback_calls: int = 0
    anomaly_events_count: int = 0


class SessionSummary(BaseModel):
    """GET /api/v1/docking/sessions/{session_id} response."""

    session_id: str
    status: Literal["running", "docked", "failed"]
    stop_reason: StopReason | None = None
    failure_reason: FailureReason | None = None
    steps_completed: int = 0
    sim_time_s: float = 0.0
    phase: DockingPhase | None = None
    final_secondary: SatelliteState | None = None
    controller: ControllerType
    metrics: Metrics = Field(default_factory=Metrics)
    events_emitted: int = 0
    llm_enabled: bool = True
    error: str | None = None
