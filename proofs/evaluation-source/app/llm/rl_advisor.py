"""RL advisor: the trained policy as informed context for the LLM planner.

The LLM-reasoning agent (or the deterministic heuristic fallback) is the
decision-maker, but when ``config.rl_advisor_enabled`` is set it receives an
*advisory sub-goal* computed from the trained RL policy at every replan:

  1. Run the policy on the current (state, active sub-goal) — it commands a
     bounded acceleration, exactly as it does when used as ``controller="rl"``.
  2. Project that acceleration forward by ``lookahead_s`` into a suggested
     target position/velocity — "where the learned policy is heading".
  3. Hand the suggestion to the reasoning layer as context; the planner may
     adopt it (optionally capped), override it, or reject it, and its
     rationale records which it did.

This is the hybrid research mode: the LLM keeps maneuver interpretability
(every decision carries a natural-language justification) while its planning
is informed by what the RL policy has learned. The suggestion is also echoed
on each ``llm_decision`` event, so the stream shows "RL suggested X, planner
chose Y".

The RL artifacts (model + VecNormalize stats) are the same ones used by
``controller="rl"``; if they're absent or the policy produces a non-finite
command, ``suggest`` returns ``None`` and the planner simply proceeds without
advisory context.
"""

from __future__ import annotations

import logging

import numpy as np

from app.config import get_settings
from app.schemas.events import LlmSubgoal, RlAdvisorSuggestion
from app.simulation.dynamics import RigidBodyState

logger = logging.getLogger("llm_docking.rl_advisor")


class RlAdvisor:
    """Runs the trained policy at replan time and produces a suggestion."""

    def __init__(
        self,
        mass_kg: float = 500.0,
        inertia: np.ndarray | None = None,
        lookahead_s: float = 4.0,
        model_path: str | None = None,
        normalize_path: str | None = None,
    ) -> None:
        from app.simulation.dynamics import DEFAULT_INERTIA

        self.mass_kg = float(mass_kg)
        self.inertia = np.asarray(inertia if inertia is not None else DEFAULT_INERTIA, dtype=float)
        self.lookahead_s = float(lookahead_s)
        settings = get_settings()
        self.model_path = model_path or settings.rl_model_path
        self.normalize_path = normalize_path or settings.rl_normalize_path
        self._controller = None  # lazy: RlController pulls in the RL extras
        self._load_error: str | None = None

    def suggest(
        self,
        state: RigidBodyState,
        subgoal: LlmSubgoal | None,
    ) -> RlAdvisorSuggestion | None:
        """Return the policy's advisory target, or None when unavailable.

        Never raises: a missing/broken policy degrades to no-advice, not a
        failed run.
        """
        controller = self._get_controller()
        if controller is None or subgoal is None:
            return None

        from app.simulation.controllers.base import ControlContext

        try:
            cmd = controller.compute(state, subgoal, dt=1.0, ctx=ControlContext())
        except Exception:  # noqa: BLE001 - advisory only; never crash the sim
            logger.warning(
                "rl_advisor_failed",
                extra={"error": str(self._load_error or "policy compute failed")},
            )
            return None

        accel = np.asarray(cmd.force_n, dtype=float) / self.mass_kg
        if not np.all(np.isfinite(accel)):
            logger.warning("rl_advisor_non_finite_command")
            return None

        tau = self.lookahead_s
        v_sugg = np.asarray(state.velocity, dtype=float) + accel * tau
        p_sugg = np.asarray(state.position, dtype=float) + state.velocity * tau + 0.5 * accel * tau**2

        p_norm = float(np.linalg.norm(p_sugg))
        closing = 0.0
        if p_norm > 1e-9:
            closing = max(0.0, -float(np.dot(v_sugg, p_sugg) / p_norm))

        return RlAdvisorSuggestion(
            suggested_position_m=[float(v) for v in p_sugg],
            suggested_velocity_mps=[float(v) for v in v_sugg],
            closing_speed_mps=closing,
            lookahead_s=tau,
        )

    # ------------------------------------------------------------------

    def _get_controller(self):
        if self._controller is not None:
            return self._controller
        if self._load_error is not None:
            return None
        if not self.model_path or not self.normalize_path:
            self._load_error = "RL artifacts not configured (LLM_DOCKING_RL_MODEL_PATH/NORMALIZE_PATH)"
            logger.warning("rl_advisor_disabled", extra={"reason": self._load_error})
            return None
        try:
            from app.simulation.controllers.rl import RlController

            self._controller = RlController(
                mass_kg=self.mass_kg,
                inertia=self.inertia,
                model_path=self.model_path,
                normalize_path=self.normalize_path,
            )
            return self._controller
        except Exception as exc:  # noqa: BLE001 - degrade to no-advice
            self._load_error = str(exc)
            logger.warning("rl_advisor_load_failed", extra={"error": self._load_error})
            return None
