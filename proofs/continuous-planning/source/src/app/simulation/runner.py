"""Simulation runner: the loop that drives one docking session.

The runner owns the per-session execution flow:

  * converts the request's ``SatelliteState`` into the internal physics state,
  * derives the mean motion ``n`` from the orbital elements,
  * advances the anomaly manager (dropout / impulse / priority change),
  * calls the reasoning layer every ``llm_cadence_steps`` for a new sub-goal,
  * computes the low-level controller command and propagates the dynamics,
  * accumulates evaluation metrics (Δv, ISE, peak thrust, LLM call counts),
  * emits the SSE event stream and terminates on docked / failure conditions.

All events are appended to one ordered log; each SSE client reads its own cursor.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Any

import numpy as np

from app.config import Settings
from app.llm.reasoning_agent import (
    HeuristicAgent,
    ReasoningAgent,
    ReasoningAgentFactory,
    ReasoningInput,
    with_retry_heuristic_fallback,
)
from app.llm.rl_advisor import RlAdvisor
from app.llm.tools import docking_tools
from app.schemas.docking import (
    DockingPhase,
    FailureReason,
    Metrics,
    MotionLimits,
    SatelliteState,
    SessionSummary,
    SimulateRequest,
    StopReason,
)
from app.schemas.events import (
    AnomalyEvent,
    DockedEvent,
    FailedEvent,
    LlmDecisionEvent,
    LlmSubgoal,
    PlanningEvent,
    PrimaryFrame,
    RlAdvisorSuggestion,
    TelemetryEvent,
)
from app.sessions.store import Session
from app.simulation.anomalies import AnomalyManager
from app.simulation.controllers import ControlContext, build_controller
from app.simulation.dynamics import (
    DEFAULT_INERTIA,
    Command,
    RigidBodyState,
    classify_phase,
    mean_motion_radps,
    propagate_chaser,
)
from app.simulation.safety import capture_checks, enforce_command, limit_velocity

logger = logging.getLogger("llm_docking.runner")

# Reference attitude: the docking port frame (body +X aligned with port).

# Static sub-goal used when the LLM layer is disabled: direct homing.
_STATIC_SUBGOAL = LlmSubgoal(
    target_position_m=[0.0, 0.0, 0.0],
    target_velocity_mps=[0.0, 0.0, 0.0],
    closing_speed_mps=0.0,
    rationale="LLM disabled: direct homing to the docking port.",
)


class SimulationRunner:
    """Runs one simulation session to completion and writes its summary."""

    def __init__(
        self,
        session: Session,
        request: SimulateRequest,
        settings: Settings | None = None,
        agent: ReasoningAgent | None = None,
        heuristic: HeuristicAgent | None = None,
    ) -> None:
        self.session = session
        self.request = request
        self.settings = settings or _default_settings()
        self.agent = agent or ReasoningAgentFactory.build(
            request.config.provider, model=request.config.model
        )
        self.heuristic = heuristic or ReasoningAgentFactory.heuristic()

        self._metrics = Metrics()
        self._last_phase: DockingPhase | None = None
        self._last_source: str | None = None
        self._last_truth: RigidBodyState | None = None
        self._current_step = 0
        self._current_time = 0.0
        # Primary frame anchors every telemetry event (frontend camera).
        self._primary_frame = PrimaryFrame(
            position_m=request.primary.position_m, orientation_quat=request.primary.orientation_quat
        )
        self.session.request_data = request.model_dump(mode="json")
        self._command_limited = False
        self._planning_task: asyncio.Task | None = None
        self._guidance_mode = "coasting"
        # Lazy RL advisor (hybrid mode: the LLM planner sees a suggestion from
        # the trained policy). None = not requested or unavailable.
        self._rl_advisor: RlAdvisor | None = None
        self._rl_advisor_unavailable = False

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Drive the simulation to a terminal event and finalize the summary."""
        try:
            self._build_initial_summary()

            await self._run_loop()
        except Exception as exc:  # noqa: BLE001 - degrade to a failed summary
            logger.exception("simulation_crashed", extra={"session_id": self.session.session_id})
            await self._fail(
                step=self._current_step,
                sim_time=self._current_time,
                reason=FailureReason.UNRECOVERABLE_ANOMALY,
                error=str(exc),
            )
        finally:
            if self._planning_task is not None:
                self._planning_task.cancel()
                with suppress(asyncio.CancelledError, Exception):
                    await self._planning_task
            self.session.finished.set()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _run_loop(self) -> None:
        cfg = self.request.config
        dt = cfg.step_interval_s

        orbital = self.request.primary.orbital_elements or self.request.secondary.orbital_elements
        assert orbital is not None  # guaranteed by SimulateRequest validation
        n = orbital.mean_motion_radps or mean_motion_radps(orbital.semi_major_axis_m)

        truth = self._to_rigid_body(self.request.secondary)
        primary = self.request.primary
        truth.position -= np.asarray(primary.position_m)
        truth.velocity -= np.asarray(primary.velocity_mps)
        from app.simulation.dynamics import quat_conjugate, quat_multiply

        truth.quat = quat_multiply(quat_conjugate(np.asarray(primary.orientation_quat)), truth.quat)
        truth.omega -= np.asarray(primary.angular_velocity_radps)
        rng = np.random.default_rng(cfg.seed)
        controller = build_controller(cfg.controller, truth.mass_kg, truth.inertia, n)
        ctx = ControlContext()
        anomalies = AnomalyManager(cfg.anomalies, rng)

        subgoal: LlmSubgoal | None = None
        step = 0
        sim_time = 0.0
        next_plan_step = 0
        self._current_step = step
        self._current_time = sim_time

        # Initial state snapshot before any control.
        await self._emit_telemetry(truth, step, sim_time, None, self._last_source)

        while True:
            self._last_truth = truth.deep_copy()
            self.session.capture = self._capture(truth)
            if self.session.cancel_requested:
                await self._fail(step, sim_time, FailureReason.CANCELLED)
                return
            # ---- advance anomaly timelines (fires configured anomalies) ----
            observed, new_details = anomalies.advance(step, truth)
            for detail in new_details:
                await self._emit(AnomalyEvent(anomaly=detail, step=step, sim_time_s=sim_time))
                self._metrics.anomaly_events_count += 1

            aborting = anomalies.priority_change_active(step) == "abort"
            sensor_stale = any(s.observing_dropout for s in anomalies.states)
            if (
                not aborting
                and not sensor_stale
                and self.session.capture["eligible"]
                and (cfg.auto_dock or self.session.dock_requested)
            ):
                await self._docked(truth, step, sim_time)
                return

            # Consume a completed provider response without ever waiting for it.
            if self._planning_task is not None and self._planning_task.done():
                completed = self._planning_task
                self._planning_task = None
                result = completed.result()
                subgoal, applied = await self._accept_plan(
                    result, observed, step, sim_time, anomalies
                )
                controller.reset(ctx)
                if not applied:
                    next_plan_step = step

            if new_details:
                next_plan_step = step

            # Local rules are cheap and deterministic. Network providers run in
            # one background task; overlapping requests are coalesced.
            if cfg.llm_enabled and self._planning_task is None and step >= next_plan_step:
                await self._emit(
                    PlanningEvent(
                        step=step,
                        sim_time_s=sim_time,
                        provider=cfg.provider or self.settings.mode,
                        status="started",
                    )
                )
                next_plan_step = step + cfg.llm_cadence_steps
                if isinstance(self.agent, HeuristicAgent):
                    result = await self._plan(observed, step, sim_time, anomalies, subgoal)
                    subgoal, _ = await self._accept_plan(
                        result, observed, step, sim_time, anomalies
                    )
                    controller.reset(ctx)
                else:
                    self._planning_task = asyncio.create_task(
                        self._plan(observed.deep_copy(), step, sim_time, anomalies, subgoal)
                    )
                    # Give the task a turn to capture its input before advancing faults.
                    await asyncio.sleep(0)
            elif not cfg.llm_enabled and subgoal is None:
                subgoal = _STATIC_SUBGOAL
                self._last_source = None
                controller.reset(ctx)

            # ---- low-level control from the *observed* state ----
            active_subgoal = subgoal
            self._guidance_mode = "active_plan" if subgoal is not None else "coasting"
            if aborting or sensor_stale:
                # Fault response never waits for a network plan or trusts an old one.
                active_subgoal = LlmSubgoal(
                    target_position_m=observed.position.tolist(),
                    target_velocity_mps=[0, 0, 0],
                    closing_speed_mps=0,
                    rationale="Local safety controller: brake during abort or sensor loss.",
                )
                self._guidance_mode = "abort_braking" if aborting else "sensor_braking"
            command = (
                controller.compute(observed, active_subgoal, dt, ctx)
                if active_subgoal is not None
                else Command()
            )
            # Reserve enough distance to brake before the shared capture envelope.
            # Apply this to actual motion, not just to the LLM's velocity proposal.
            limits = self._motion_envelope(truth)
            command, self._command_limited = enforce_command(
                truth,
                command,
                dt,
                n,
                self.request.primary.velocity_mps,
                limits,
                cfg.max_thrust_n,
                cfg.max_acceleration_mps2,
            )

            # ---- metrics on truth (physical state), pre-propagation ----
            self._metrics.ise += float(np.dot(truth.position, truth.position)) * dt
            self._metrics.delta_v_mps += float(np.linalg.norm(command.force_n)) / truth.mass_kg * dt
            self._metrics.max_commanded_thrust_n = max(
                self._metrics.max_commanded_thrust_n, float(np.linalg.norm(command.force_n))
            )

            # ---- divergence guards BEFORE propagating: an unstable command
            #      (e.g. from a bad RL policy) must never push the state into
            #      numerical blow-up — fail the run cleanly instead ----
            if (float(np.linalg.norm(truth.position)) > (cfg.max_range_m or 1000)) or float(
                np.linalg.norm(truth.omega)
            ) > cfg.max_omega_radps:
                await self._fail(step, sim_time, FailureReason.DIVERGED)
                return

            # ---- propagate truth, burn fuel ----
            previous_velocity = truth.velocity.copy()
            truth = propagate_chaser(truth, dt, n, command)
            if (
                np.linalg.norm((truth.velocity - previous_velocity) / dt)
                > cfg.max_acceleration_mps2 + 1e-6
            ):
                await self._fail(step, sim_time, FailureReason.LIMIT_EXCEEDED)
                return
            if np.linalg.norm(command.force_n) > 1e-6:
                truth.fuel_pct = max(0.0, truth.fuel_pct - cfg.fuel_consumption_rate_pct_per_s * dt)

            step += 1
            sim_time = step * dt
            self._current_step = step
            self._current_time = sim_time

            # The cooperative primary follows its configured constant angular rate.
            from app.simulation.dynamics import quat_from_axis_angle, quat_multiply

            primary_rate = np.asarray(self.request.primary.angular_velocity_radps)
            rate = float(np.linalg.norm(primary_rate))
            if rate > 1e-12:
                rotation = quat_from_axis_angle(primary_rate / rate, rate * sim_time)
                self._primary_frame.orientation_quat = quat_multiply(
                    np.asarray(self.request.primary.orientation_quat), rotation
                ).tolist()

            self._last_truth = truth.deep_copy()
            if float(np.linalg.norm(truth.position)) > (cfg.max_range_m or 1000):
                await self._fail(step, sim_time, FailureReason.DIVERGED)
                return
            self._primary_frame.position_m = (
                np.asarray(self.request.primary.position_m)
                + np.asarray(self.request.primary.velocity_mps) * sim_time
            ).tolist()
            self.session.capture = self._capture(truth)
            absolute_velocity = truth.velocity + np.asarray(self.request.primary.velocity_mps)
            if not np.all(np.isfinite(truth.position)) or not np.all(np.isfinite(truth.velocity)):
                await self._fail(step, sim_time, FailureReason.DIVERGED)
                return
            if not np.allclose(
                absolute_velocity,
                limit_velocity(absolute_velocity, self.request.secondary.motion_limits),
                atol=1e-6,
            ):
                await self._fail(step, sim_time, FailureReason.LIMIT_EXCEEDED)
                return
            await self._emit_telemetry(truth, step, sim_time, command, self._last_source)
            # ---- terminal conditions ----
            if (
                not aborting
                and not sensor_stale
                and self._is_docked(truth)
                and (cfg.auto_dock or self.session.dock_requested)
            ):
                await self._docked(truth, step, sim_time)
                return
            if truth.fuel_pct <= 0.0:
                await self._fail(step, sim_time, FailureReason.FUEL_EXHAUSTED)
                return
            if cfg.max_time_s is not None and sim_time >= cfg.max_time_s:
                await self._fail(step, sim_time, FailureReason.MAX_TIME_EXCEEDED)
                return
            if step >= cfg.max_steps:
                await self._fail(step, sim_time, FailureReason.MAX_STEPS_EXCEEDED)
                return

            delay = (
                dt / cfg.playback_speed if cfg.playback_speed is not None else cfg.stream_pacing_s
            )
            # Interruptible pacing keeps Stop responsive even at 1× playback.
            until = asyncio.get_running_loop().time() + delay
            while not self.session.cancel_requested and asyncio.get_running_loop().time() < until:
                await asyncio.sleep(min(0.1, until - asyncio.get_running_loop().time()))
            # Unpaced experiments must also let provider tasks and Stop make progress.
            await asyncio.sleep(0)

    # ------------------------------------------------------------------
    # Planning
    # ------------------------------------------------------------------

    async def _accept_plan(self, result, observed, step, sim_time, anomalies):
        """Recheck a returned snapshot against the current state before applying it."""
        subgoal, source, rl_sugg, snapshot, tools, notes = result
        cfg = self.request.config
        current_details = [
            d for d in (st.current_detail for st in anomalies.states) if d is not None
        ]
        current = snapshot.model_copy(
            update={
                "step": step,
                "sim_time_s": sim_time,
                "phase": classify_phase(float(np.linalg.norm(observed.position))),
                "range_m": float(np.linalg.norm(observed.position)),
                "position_m": observed.position.tolist(),
                "velocity_mps": observed.velocity.tolist(),
                "orientation_quat": observed.quat.tolist(),
                "angular_velocity_radps": observed.omega.tolist(),
                "fuel_remaining_pct": observed.fuel_pct,
                "anomaly_context": current_details,
                "priority_change": anomalies.priority_change_active(step),
                "capture": self._capture(observed),
            }
        )
        age = sim_time - snapshot.sim_time_s
        max_age = cfg.step_interval_s * cfg.llm_cadence_steps + cfg.planner_reserve_s
        fault_changed = (
            snapshot.priority_change != current.priority_change
            or snapshot.anomaly_context != current_details
        )
        applied = age <= max_age and not fault_changed
        if applied:
            subgoal, source, fresh_notes = self._bound_plan(subgoal, source, current, observed)
            notes = list(dict.fromkeys(notes + fresh_notes))
        else:
            notes.append(
                "Response discarded: snapshot expired or fault context changed. Local braking applied."
            )
        self._metrics.total_llm_calls += 1
        if source == "heuristic_fallback":
            self._metrics.llm_fallback_calls += 1
        self._last_source = source if applied else "local_safety"
        await self._emit(
            PlanningEvent(step=step, sim_time_s=sim_time, provider=source, status="completed")
        )
        await self._emit(
            LlmDecisionEvent(
                step=step,
                sim_time_s=sim_time,
                phase=self._phase_of(observed),
                subgoal=subgoal,
                source=source,
                anomaly_context=current_details,
                priority_change=current.priority_change,
                metrics_so_far=self._metrics.model_copy(deep=True),
                rl_advisor=rl_sugg,
                tool_results=tools,
                safety_notes=notes,
                snapshot_step=snapshot.step,
                snapshot_sim_time_s=snapshot.sim_time_s,
                plan_age_s=age,
                applied=applied,
            )
        )
        if not applied:
            subgoal = LlmSubgoal(
                target_position_m=observed.position.tolist(),
                target_velocity_mps=[0, 0, 0],
                closing_speed_mps=0,
                rationale="Local braking while fresh guidance is requested.",
            )
        return subgoal, applied

    def _motion_envelope(self, state: RigidBodyState) -> MotionLimits:
        """Bound applied velocity by speed limits and conservative stopping distance."""
        cfg = self.request.config
        limits = self.request.secondary.motion_limits.model_copy()
        distance = float(np.linalg.norm(state.position))
        if distance > 5:
            orbital = (
                self.request.primary.orbital_elements or self.request.secondary.orbital_elements
            )
            n = orbital.mean_motion_radps or mean_motion_radps(orbital.semi_major_axis_m)
            drift = (
                propagate_chaser(state, cfg.step_interval_s, n).velocity - state.velocity
            ) / cfg.step_interval_s
            braking = max(
                1e-6,
                min(cfg.max_acceleration_mps2, cfg.max_thrust_n / state.mass_kg)
                - float(np.linalg.norm(drift)),
            )
            reserve = cfg.planner_reserve_s + cfg.step_interval_s * cfg.llm_cadence_steps
            available = max(0, distance - 5)
            cap = -braking * reserve + np.sqrt(
                (braking * reserve) ** 2 + cfg.near_port_speed_mps**2 + 2 * braking * available
            )
        else:
            cap = min(cfg.near_port_speed_mps, cfg.dock_velocity_tol_mps * 0.95)
        # Configured envelopes apply to absolute velocity; approach braking is
        # relative to the primary. A moving primary needs its own velocity offset.
        absolute_cap = cap + float(np.linalg.norm(self.request.primary.velocity_mps))
        limits.max_speed_mps = min(limits.max_speed_mps, absolute_cap)
        return limits

    async def _plan(
        self,
        observed: RigidBodyState,
        step: int,
        sim_time: float,
        anomalies: AnomalyManager,
        current_subgoal: LlmSubgoal | None,
    ) -> tuple:
        range_m = float(np.linalg.norm(observed.position))
        anomaly_details = [
            d for d in (st.current_detail for st in anomalies.states) if d is not None
        ]
        priority_change = anomalies.priority_change_active(step)
        # Hybrid mode: ask the trained RL policy for an advisory sub-goal.
        # Model loading/inference must not block SSE, status requests or Stop.
        rl_sugg = (
            await asyncio.to_thread(self._advisor_suggestion, observed, current_subgoal)
            if self.request.config.rl_advisor_enabled
            else None
        )
        inp = ReasoningInput(
            step=step,
            sim_time_s=sim_time,
            phase=classify_phase(range_m),
            range_m=range_m,
            position_m=[float(v) for v in observed.position],
            velocity_mps=[float(v) for v in observed.velocity],
            orientation_quat=[float(v) for v in observed.quat],
            angular_velocity_radps=[float(v) for v in observed.omega],
            fuel_remaining_pct=observed.fuel_pct,
            controller=self.request.config.controller.value,
            anomaly_context=anomaly_details,
            priority_change=priority_change,
            rl_advisor=rl_sugg,
            capture=self._capture(observed),
            primary_limits=self.request.primary.motion_limits.model_dump(),
            secondary_limits=self.request.secondary.motion_limits.model_dump(),
            max_thrust_n=self.request.config.max_thrust_n,
            max_acceleration_mps2=self.request.config.max_acceleration_mps2,
            mass_kg=observed.mass_kg,
            primary_velocity_mps=self.request.primary.velocity_mps,
        )
        tools = [{"name": t.name, "result": t.invoke({})} for t in docking_tools(inp)[:4]]
        if isinstance(self.agent, HeuristicAgent):
            subgoal, source = await self.agent.reason(inp)
        else:
            subgoal, source = await with_retry_heuristic_fallback(
                self.agent,
                inp,
                self.heuristic,
                max_retries=self.settings.llm_max_retries,
                backoff_s=self.settings.llm_retry_backoff_s,
            )
            tools = self.agent.last_tools or tools
        subgoal, source, notes = self._bound_plan(subgoal, source, inp, observed)
        return subgoal, source, rl_sugg, inp, tools, notes

    def _bound_plan(self, subgoal, source, inp, observed):
        """Apply the same target and speed rules at request and response time."""
        range_m = float(np.linalg.norm(observed.position))
        anomaly_details = inp.anomaly_context
        notes = []
        target = np.asarray(subgoal.target_position_m)
        if not np.isfinite(target).all() or np.linalg.norm(target) > max(range_m * 1.1, 1.25):
            subgoal = self.heuristic.plan(inp)
            source = "heuristic_fallback"
            notes.append("Rejected non-finite or diverging target.")
            target = np.asarray(subgoal.target_position_m)
        limits = self._motion_envelope(observed)
        relative_limits = MotionLimits(
            max_speed_mps=min(
                limits.max_speed_mps, self.heuristic.phase_speed_caps.get(inp.phase, 1.0)
            ),
            max_horizontal_speed_mps=limits.max_horizontal_speed_mps,
            max_vertical_speed_mps=limits.max_vertical_speed_mps,
        )
        desired_velocity = np.asarray(subgoal.target_velocity_mps)
        distance_to_goal = float(np.linalg.norm(target - observed.position))
        if (
            limits.min_speed_mps > 0
            and range_m > 5.0
            and inp.priority_change != "abort"
            and not anomaly_details
            and np.linalg.norm(desired_velocity) > 1e-9
            and np.dot(desired_velocity, observed.position) < 0
        ):
            # Minimum is a transit preference, bounded by braking distance and phase limits.
            transit_speed = min(
                limits.min_speed_mps,
                np.sqrt(2 * 0.05 * distance_to_goal),
                relative_limits.max_speed_mps,
            )
            if np.linalg.norm(desired_velocity) < transit_speed:
                desired_velocity *= transit_speed / np.linalg.norm(desired_velocity)
        velocity = limit_velocity(desired_velocity, relative_limits)
        if not np.allclose(velocity, subgoal.target_velocity_mps):
            notes.append("Target velocity reduced to the configured and phase envelope.")
        subgoal.target_velocity_mps = velocity.tolist()
        subgoal.closing_speed_mps = min(subgoal.closing_speed_mps, float(np.linalg.norm(velocity)))
        if (
            range_m <= 5
            and range_m > 0
            and inp.priority_change != "abort"
            and not anomaly_details
            and np.dot(velocity, observed.position) < 0
        ):
            # Learned lateral advice must not create a near-port orbit. Finish
            # along the measured port vector, below the capture speed tolerance.
            speed = min(float(np.linalg.norm(velocity)), limits.max_speed_mps)
            subgoal.target_position_m = [0.0, 0.0, 0.0]
            subgoal.target_velocity_mps = (-observed.position / range_m * speed).tolist()
            subgoal.closing_speed_mps = speed
            notes.append(
                "Final approach aligned with the measured port vector, with capture-speed margin."
            )
        # The position controller stops at its waypoint. A short RL lookahead
        # point must not stall a long approach between planner calls.
        travel = (
            np.linalg.norm(velocity)
            * self.request.config.step_interval_s
            * self.request.config.llm_cadence_steps
        )
        if (
            range_m > 5
            and inp.priority_change != "abort"
            and not anomaly_details
            and np.dot(velocity, observed.position) < 0
            and distance_to_goal < min(range_m * 0.5, travel * 1.5)
        ):
            subgoal.target_position_m = (observed.position * 0.5).tolist()
            notes.append("Extended the inward waypoint to sustain motion until the next replan.")
        if not subgoal.alternatives:
            subgoal.alternatives = [
                "Faster approach rejected: braking margin decreases.",
                "Immediate capture rejected until all capture checks pass.",
            ]
        if not subgoal.rl_assessment:
            subgoal.rl_assessment = (
                "Learned velocity advice was adopted and bounded by the motion envelope."
                if "RL advisor adopted" in subgoal.rationale
                else "Learned advice was available; the planner used a bounded port-directed maneuver."
                if inp.rl_advisor
                else "No learned proposal was supplied for this decision."
            )
        return subgoal, source, notes

    def _advisor_suggestion(
        self,
        observed: RigidBodyState,
        current_subgoal: LlmSubgoal | None,
    ) -> RlAdvisorSuggestion | None:
        cfg = self.request.config
        if not cfg.rl_advisor_enabled or self._rl_advisor_unavailable:
            return None
        if self._rl_advisor is None:
            self._rl_advisor = RlAdvisor(
                mass_kg=observed.mass_kg,
                inertia=observed.inertia,
                lookahead_s=cfg.rl_advisor_lookahead_s,
            )
        baseline = self.heuristic.plan(
            ReasoningInput(
                step=self._current_step,
                sim_time_s=self._current_time,
                phase=classify_phase(float(np.linalg.norm(observed.position))),
                range_m=float(np.linalg.norm(observed.position)),
                position_m=observed.position.tolist(),
                velocity_mps=observed.velocity.tolist(),
                orientation_quat=observed.quat.tolist(),
                angular_velocity_radps=observed.omega.tolist(),
                fuel_remaining_pct=observed.fuel_pct,
                controller=cfg.controller.value,
            )
        )
        suggestion = self._rl_advisor.suggest(observed, baseline)
        if suggestion is None:
            self._rl_advisor_unavailable = True  # stop retrying every replan
        return suggestion

    # ------------------------------------------------------------------
    # Terminal events + summary
    # ------------------------------------------------------------------

    async def _docked(self, truth: RigidBodyState, step: int, sim_time: float) -> None:
        final = self._to_satellite(truth)
        self._last_phase = DockingPhase.DOCKED
        await self._emit(
            DockedEvent(
                step=step,
                sim_time_s=sim_time,
                final_secondary=final,
                metrics=self._metrics.model_copy(deep=True),
            )
        )
        summary = self.session.summary
        assert summary is not None
        summary.status = "docked"
        summary.stop_reason = StopReason.DOCKED
        summary.failure_reason = None
        summary.steps_completed = step
        summary.sim_time_s = sim_time
        summary.phase = self._last_phase or DockingPhase.DOCKED
        summary.final_secondary = final
        summary.metrics = self._metrics.model_copy(deep=True)
        summary.error = None

    async def _fail(
        self,
        step: int,
        sim_time: float,
        reason: FailureReason,
        error: str | None = None,
    ) -> None:
        final = self._to_satellite(self._last_truth) if self._last_truth is not None else None
        await self._emit(
            FailedEvent(
                step=step,
                sim_time_s=sim_time,
                failure_reason=reason,
                error=error,
                final_secondary=final,
                metrics=self._metrics.model_copy(deep=True),
            )
        )
        summary = self.session.summary
        assert summary is not None
        summary.status = "failed"
        summary.stop_reason = StopReason.FAILED
        summary.failure_reason = reason
        summary.steps_completed = step
        summary.sim_time_s = sim_time
        summary.phase = self._last_phase
        summary.final_secondary = final
        summary.metrics = self._metrics.model_copy(deep=True)
        summary.error = error

    def _build_initial_summary(self) -> None:
        self.session.summary = SessionSummary(
            session_id=self.session.session_id,
            status="running",
            controller=self.request.config.controller,
            llm_enabled=self.request.config.llm_enabled,
            metrics=self._metrics,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _emit_telemetry(
        self,
        state: RigidBodyState,
        step: int,
        sim_time: float,
        command: Any,
        llm_source: str | None,
    ) -> None:
        range_m = float(np.linalg.norm(state.position))
        phase = self._phase_of(state)
        self._last_phase = phase
        self._last_truth = state.deep_copy()
        await self._emit(
            TelemetryEvent(
                step=step,
                sim_time_s=sim_time,
                phase=phase,
                position_m=[float(v) for v in state.position],
                velocity_mps=[float(v) for v in state.velocity],
                range_m=range_m,
                closing_speed_mps=self._closing_speed(state),
                fuel_pct=state.fuel_pct,
                controller=self.request.config.controller,
                llm_source=llm_source,
                command_force_n=[float(v) for v in command.force_n]
                if command is not None
                else None,
                command_torque_nm=[float(v) for v in command.torque_nm]
                if command is not None
                else None,
                primary=self._primary_frame.model_copy(deep=True),
                metrics_so_far=self._metrics.model_copy(deep=True),
                orientation_quat=state.quat.tolist(),
                angular_velocity_radps=state.omega.tolist(),
                primary_velocity_mps=self.request.primary.velocity_mps,
                secondary_velocity_mps=(
                    state.velocity + np.asarray(self.request.primary.velocity_mps)
                ).tolist(),
                capture=self._capture(state),
                command_limited=self._command_limited,
                planning_pending=self._planning_task is not None,
                guidance_mode=self._guidance_mode,
            )
        )
        summary = self.session.summary
        if summary is not None:
            summary.steps_completed = step
            summary.sim_time_s = sim_time
            summary.phase = phase

    async def _emit(self, event: Any) -> None:
        await self.session.append(event)

    @staticmethod
    def _closing_speed(state: RigidBodyState) -> float:
        r = state.position
        norm = float(np.linalg.norm(r))
        if norm < 1e-9:
            return 0.0
        # Radial closing rate: negative radial velocity, clamped at zero.
        return max(0.0, -float(np.dot(state.velocity, r) / norm))

    def _capture(self, state):
        cfg = self.request.config
        return capture_checks(
            state,
            cfg.dock_position_tol_m,
            cfg.dock_velocity_tol_mps,
            cfg.dock_attitude_tol_deg,
            primary_radius=self.request.primary.capture_radius_m,
            secondary_radius=self.request.secondary.capture_radius_m,
        )

    def _is_docked(self, state):
        return self._capture(state)["eligible"]

    @staticmethod
    def _phase_of(state: RigidBodyState) -> DockingPhase:
        return DockingPhase(classify_phase(float(np.linalg.norm(state.position))))

    @staticmethod
    def _to_rigid_body(s: SatelliteState) -> RigidBodyState:
        inertia = (
            np.asarray(s.inertia_kg_m2, dtype=float)
            if s.inertia_kg_m2 is not None
            else DEFAULT_INERTIA.copy()
        )
        return RigidBodyState(
            position=np.asarray(s.position_m, dtype=float),
            velocity=np.asarray(s.velocity_mps, dtype=float),
            quat=np.asarray(s.orientation_quat, dtype=float),
            omega=np.asarray(s.angular_velocity_radps, dtype=float),
            fuel_pct=s.fuel_remaining_pct,
            mass_kg=s.mass_kg,
            inertia=inertia,
        )

    @staticmethod
    def _to_satellite(s: RigidBodyState) -> SatelliteState:
        return SatelliteState(
            position_m=[float(v) for v in s.position],
            velocity_mps=[float(v) for v in s.velocity],
            orientation_quat=[float(v) for v in s.quat],
            angular_velocity_radps=[float(v) for v in s.omega],
            fuel_remaining_pct=s.fuel_pct,
            mass_kg=s.mass_kg,
            inertia_kg_m2=[float(v) for v in s.inertia],
        )


def _default_settings() -> Settings:
    from app.config import get_settings

    return get_settings()
