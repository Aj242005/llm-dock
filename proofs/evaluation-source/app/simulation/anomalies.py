"""Anomaly injection.

Each configured anomaly is applied at its ``step`` inside the simulation loop:

  * sensor_dropout   — the reported relative state seen by the LLM and the
                       controller is withheld (gap) or corrupted with Gaussian
                       noise for ``duration_steps``. The *truth* state still
                       propagates physically; only the observed state is wrong.
  * velocity_impulse — an unmodeled instantaneous Δv is applied to the truth
                       state (clamped to a sane envelope).
  * priority_change  — an instruction (abort) is injected into the LLM context
                       only; it does not touch physics.

The anomaly manager is structured so a future frontend/eval harness can see the
exact same data: every anomaly also produces an ``AnomalyDetail`` that the
runner embeds into the SSE ``anomaly`` event and into the LLM prompt context.
"""

from __future__ import annotations

import numpy as np

from app.schemas.docking import AnomalyConfig, AnomalyType
from app.schemas.events import AnomalyDetail
from app.simulation.dynamics import RigidBodyState


class AnomalyState:
    """Bookkeeping for one injected anomaly."""

    def __init__(self, config: AnomalyConfig, rng: np.random.Generator) -> None:
        self.config = config
        self.rng = rng
        self.active_remaining_steps = 0
        self.fired = False
        self.current_detail: AnomalyDetail | None = None
        self.since_last_event_steps = 0
        self._impulse_applied = False

    def tick(self, step: int, truth: RigidBodyState) -> AnomalyDetail | None:
        """Advance one physics step. Returns a new AnomalyDetail only when the
        anomaly fires or when its effect ends (dropout restoration), so the
        stream isn't spammed with redundant anomaly events."""
        self.since_last_event_steps += 1
        detail: AnomalyDetail | None = None

        if not self.fired and step >= self.config.step:
            self.fired = True
            self.active_remaining_steps = self.config.duration_steps or 0
            self.since_last_event_steps = 0
            base = {
                "type": self.config.type,
                "detail": self.config.detail,
                "step": step,
            }
            if self.config.type is AnomalyType.SENSOR_DROPOUT:
                detail = AnomalyDetail(
                    **base,
                    sensor="relative_state",
                    impulse_mps=None,
                    priority_change=None,
                )
                self.current_detail = detail
            elif self.config.type is AnomalyType.VELOCITY_IMPULSE:
                detail = AnomalyDetail(
                    **base, sensor=None, impulse_mps=self.config.impulse_mps, priority_change=None
                )
                self.current_detail = detail
            elif self.config.type is AnomalyType.PRIORITY_CHANGE:
                detail = AnomalyDetail(
                    **base,
                    sensor=None,
                    impulse_mps=None,
                    priority_change=self.config.priority_change,
                )
                self.current_detail = detail
        elif self.fired and self.active_remaining_steps > 0:
            self.active_remaining_steps -= 1

        # Emit a second event when a sensor-dropout window ends (restored).
        if (
            self.config.type is AnomalyType.SENSOR_DROPOUT
            and self.fired
            and self.active_remaining_steps == 0
            and self.since_last_event_steps >= 2
            and detail is None
        ):
            detail = AnomalyDetail(
                type=self.config.type,
                detail=f"sensor restored after {self.config.duration_steps} steps",
                step=step,
                sensor="relative_state",
                impulse_mps=None,
                priority_change=None,
            )
            self.since_last_event_steps = 0
            self.current_detail = detail

        return detail

    @property
    def active(self) -> bool:
        return self.fired and (
            self.active_remaining_steps > 0 or self.config.duration_steps is None
        )

    @property
    def observing_dropout(self) -> bool:
        return self.config.type is AnomalyType.SENSOR_DROPOUT and self.active


class AnomalyManager:
    """Applies configured anomalies to the truth state and produces the
    observed state that the LLM + controller act on."""

    def __init__(self, configs: list[AnomalyConfig], rng: np.random.Generator) -> None:
        self.states = [AnomalyState(c, rng) for c in configs]
        self.rng = rng
        # Noise scale used to corrupt sensor readings (fraction of signal).
        self.corruption_fraction = 0.05

    def advance(
        self, step: int, truth: RigidBodyState
    ) -> tuple[RigidBodyState, list[AnomalyDetail]]:
        """Advance anomaly timelines; return (observed_state, new_anomaly_details)."""
        observed = truth.deep_copy()
        details: list[AnomalyDetail] = []

        for st in self.states:
            evt = st.tick(step, truth)
            if evt is not None:
                details.append(evt)

            if st.observing_dropout:
                if st.config.corrupt:
                    self._corrupt_observed(observed)
                else:
                    self._withhold_observed(observed)

            if (
                st.config.type is AnomalyType.VELOCITY_IMPULSE
                and st.fired
                and st.active_remaining_steps >= 0
            ):
                # Apply impulses on the step they fire and while active (once).
                if getattr(st, "_impulse_applied", False) is False:
                    impulse = np.asarray(st.config.impulse_mps, dtype=float)
                    truth.velocity = truth.velocity + impulse
                    observed.velocity = observed.velocity + impulse
                    st._impulse_applied = True

        if not any(st.observing_dropout for st in self.states):
            self._last_known_good = truth.deep_copy()

        return observed, details

    def priority_change_active(self, step: int) -> str | None:
        """If a priority-change/abort instruction is active at this step, return it."""
        for st in self.states:
            if (
                st.config.type is AnomalyType.PRIORITY_CHANGE
                and st.fired
                and (st.active_remaining_steps > 0 or st.config.duration_steps is None)
            ):
                return st.config.priority_change or "abort"
        return None

    # ------------------------------------------------------------------

    def _corrupt_observed(self, observed: RigidBodyState) -> None:
        """Add Gaussian noise to the reported relative state."""
        noise_scale = np.array([10.0, 10.0, 10.0]) * self.corruption_fraction
        observed.position = observed.position + self.rng.normal(0.0, noise_scale, 3)
        observed.velocity = observed.velocity + self.rng.normal(0.0, 0.05, 3)

    def _withhold_observed(self, observed: RigidBodyState) -> None:
        """Withhold the reading: report the last-known-good state (frozen)."""
        # The runner freezes observed state before propagation decisions anyway;
        # here we simply mark it as stale by holding the previous value.
        # Since `observed` is a deep-copy of `truth`, the freeze is applied by
        # the runner copying the pre-dropout snapshot into it. We do that here
        # by keeping a private last-valid copy.

        if getattr(self, "_last_known_good", None) is None:
            self._last_known_good = observed.deep_copy()
        else:
            # 'observed' currently equals truth; overwrite with the frozen copy.
            frozen = self._last_known_good
            observed.position = frozen.position.copy()
            observed.velocity = frozen.velocity.copy()
            observed.quat = frozen.quat.copy()
            observed.omega = frozen.omega.copy()

    def snapshot_last_known_good(self, state: RigidBodyState) -> None:
        """Called by the runner once at dropout start — captures the pre-dropout state."""
        if not hasattr(self, "_last_known_good"):
            self._last_known_good = state.deep_copy()

    @property
    def total_fired(self) -> int:
        return sum(1 for st in self.states if st.fired)

    def active_detail(self) -> AnomalyDetail | None:
        for st in self.states:
            if st.fired and st.current_detail is not None:
                return st.current_detail
        return None
