"""Event schemas emitted on the SSE stream.

Every simulation produces an ordered stream of ``DockingEvent`` members — the
single wire contract the frontend and the eval harness consume. Events are
discriminated by their ``type`` field:

  * ``telemetry``    — per-step observed state + the commanded thrust
  * ``heartbeat``    — periodic liveness marker while the run is active
  * ``llm_decision`` — a new LLM sub-goal (replan), with its source
  * ``anomaly``      — an injected anomaly fired or restored
  * ``docked``       — terminal success event (with final state + metrics)
  * ``failed``       — terminal failure event (with reason + metrics)

Every event carries a shared envelope (``StreamEventBase``): ``schema_version``
(so the frontend can assert compatibility before parsing), ``session_id`` (so a
client multiplexing several runs can route events without external state), and
the sim ``step`` / ``sim_time_s`` (so a reconnecting client can resume and
re-order). ``AnomalyDetail`` and ``LlmSubgoal`` are shared payloads also
embedded in the LLM prompt context and the controller interface respectively.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.docking import (
    AnomalyType,
    ControllerType,
    DockingPhase,
    FailureReason,
    Metrics,
    Quaternion,
    SatelliteState,
    Vector3,
)

# ---------------------------------------------------------------------------
# Shared envelope
# ---------------------------------------------------------------------------


class StreamEventBase(BaseModel):
    """Fields present on every stream event (schema version + routing/clock)."""

    schema_version: Literal["1.0"] = "1.0"
    session_id: str = ""
    event_id: int = 0
    step: int = Field(ge=0)
    sim_time_s: float = Field(ge=0.0)


class PrimaryFrame(BaseModel):
    """The primary satellite's frame, for frontend camera/orbit rendering.

    The primary is the Hill-frame origin, so its relative position is always
    [0, 0, 0]; its attitude (and any inertial position) anchors the scene.
    """

    position_m: Vector3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    orientation_quat: Quaternion = Field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])


# ---------------------------------------------------------------------------
# Shared payloads
# ---------------------------------------------------------------------------


class AnomalyDetail(BaseModel):
    """One anomaly occurrence, surfaced both on the stream and to the LLM."""

    type: AnomalyType
    detail: str = Field(default="", max_length=500)
    step: int = Field(ge=0)
    sensor: str | None = None
    impulse_mps: Vector3 | None = None
    priority_change: Literal["abort"] | None = None


class LlmSubgoal(BaseModel):
    """Structured sub-goal emitted by the reasoning layer (LLM or heuristic).

    The low-level controller tracks ``target_position_m`` / ``target_velocity_mps``
    until the next replan; ``closing_speed_mps`` is the envelope magnitude the
    planner committed to, and ``rationale`` is the human-readable justification
    (this is the event's ``llm_reasoning_summary`` — the natural-language
    justification the reasoning layer produced).
    """

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    target_position_m: Vector3
    target_velocity_mps: Vector3
    closing_speed_mps: float = Field(ge=0.0)
    rationale: str = Field(default="", max_length=500)
    alternatives: list[str] = Field(default_factory=list, max_length=4)


class RlAdvisorSuggestion(BaseModel):
    """Advisory sub-goal proposed by the trained RL policy at a replan.

    The policy is a *tracking* controller: given the current state and the
    active sub-goal it commands an acceleration, which we project forward by
    ``lookahead_s`` into a target position/velocity the policy is heading
    toward. The LLM planner receives this as informed context and may adopt
    it, cap it, or override it — its decision is what lands in
    ``llm_decision.subgoal``, and this payload is echoed on the event so the
    stream shows "RL suggested X, planner chose Y" (interpretability).
    """

    model_config = ConfigDict(allow_inf_nan=False)
    suggested_position_m: Vector3
    suggested_velocity_mps: Vector3
    closing_speed_mps: float = Field(ge=0.0)
    lookahead_s: float = Field(gt=0.0)
    policy_source: Literal["rl"] = "rl"


# ---------------------------------------------------------------------------
# Stream events
# ---------------------------------------------------------------------------


class TelemetryEvent(StreamEventBase):
    """Per-step observed state and the thruster command applied."""

    type: Literal["telemetry"] = "telemetry"
    phase: DockingPhase
    position_m: Vector3
    velocity_mps: Vector3
    range_m: float = Field(ge=0.0)
    closing_speed_mps: float = Field(ge=0.0)
    fuel_pct: float = Field(ge=0.0, le=100.0)
    controller: ControllerType
    llm_source: str | None = None
    command_force_n: Vector3 | None = None
    command_torque_nm: Vector3 | None = None
    # Frontend anchors: primary frame (origin + attitude) and running metrics
    # so a live dashboard can plot Δv/ISE without waiting for the terminal event.
    primary: PrimaryFrame = Field(default_factory=PrimaryFrame)
    metrics_so_far: Metrics = Field(default_factory=Metrics)
    orientation_quat: Quaternion = Field(default_factory=lambda: [1.0, 0.0, 0.0, 0.0])
    angular_velocity_radps: Vector3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    primary_velocity_mps: Vector3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    secondary_velocity_mps: Vector3 = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    capture: dict = Field(default_factory=dict)
    command_limited: bool = False


class HeartbeatEvent(StreamEventBase):
    """Periodic liveness marker (wall-clock interval, not sim steps)."""

    type: Literal["heartbeat"] = "heartbeat"
    status: Literal["running", "docked", "failed"] = "running"


class LlmDecisionEvent(StreamEventBase):
    """A replan: the reasoning layer (LLM or heuristic) emits a new sub-goal."""

    type: Literal["llm_decision"] = "llm_decision"
    phase: DockingPhase
    subgoal: LlmSubgoal
    source: str = Field(
        description="openai | openrouter | groq | anthropic | heuristic | heuristic_fallback"
    )
    anomaly_context: list[AnomalyDetail] = Field(default_factory=list)
    priority_change: str | None = None
    metrics_so_far: Metrics = Field(default_factory=Metrics)
    # The RL policy's advisory suggestion the planner saw (when enabled), so
    # the stream shows what the RL agent proposed vs what the planner chose.
    rl_advisor: RlAdvisorSuggestion | None = None
    tool_results: list[dict] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)


class AnomalyEvent(StreamEventBase):
    """An anomaly fired (or a sensor dropout window restored)."""

    type: Literal["anomaly"] = "anomaly"
    anomaly: AnomalyDetail


class DockedEvent(StreamEventBase):
    """Terminal success: within position/velocity/attitude tolerance."""

    type: Literal["docked"] = "docked"
    final_secondary: SatelliteState
    metrics: Metrics = Field(default_factory=Metrics)


class FailedEvent(StreamEventBase):
    """Terminal failure with the reason (fuel, steps, time, diverged, ...)."""

    type: Literal["failed"] = "failed"
    failure_reason: FailureReason
    error: str | None = None
    final_secondary: SatelliteState | None = None
    metrics: Metrics = Field(default_factory=Metrics)


DockingEvent = Annotated[
    TelemetryEvent | HeartbeatEvent | LlmDecisionEvent | AnomalyEvent | DockedEvent | FailedEvent,
    Field(discriminator="type"),
]
