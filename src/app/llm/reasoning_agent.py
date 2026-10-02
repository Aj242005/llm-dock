"""A deterministic planner and a bounded LangChain tool-calling planner.

The LLM explains its chosen action and alternatives. Physics and capture checks
are enforced separately, and every failed provider call is reported as fallback.
"""

import asyncio
import json
import os
from abc import ABC, abstractmethod

import numpy as np
from pydantic import BaseModel, Field

from app.config import get_settings
from app.schemas.docking import DockingPhase
from app.schemas.events import AnomalyDetail, LlmSubgoal, RlAdvisorSuggestion

PROVIDER_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "groq": "https://api.groq.com/openai/v1",
}
PROVIDER_ENV_KEYS = {
    "vertex": ("VERTEX_API_KEY",),
    "openai": ("OPENAI_API_KEY",),
    "openrouter": ("OPENROUTER_API_KEY",),
    "groq": ("GROQ_API_KEY",),
    "anthropic": ("ANTHROPIC_API_KEY",),
}


class ReasoningInput(BaseModel):
    step: int
    sim_time_s: float
    phase: str
    range_m: float
    position_m: list[float]
    velocity_mps: list[float]
    orientation_quat: list[float]
    angular_velocity_radps: list[float]
    fuel_remaining_pct: float
    controller: str
    anomaly_context: list[AnomalyDetail] = Field(default_factory=list)
    priority_change: str | None = None
    rl_advisor: RlAdvisorSuggestion | None = None
    rl_advisor_status: str = "disabled"
    rl_advisor_reason: str | None = None
    capture: dict = Field(default_factory=dict)
    primary_limits: dict = Field(default_factory=dict)
    secondary_limits: dict = Field(default_factory=dict)
    max_thrust_n: float = 86.6025403784
    max_acceleration_mps2: float = 1.0
    mass_kg: float = 500.0
    primary_velocity_mps: list[float] = Field(default_factory=lambda: [0, 0, 0])


def build_prompt(snapshot):
    return (
        snapshot.model_dump_json()
        + "\nrl_advisor="
        + (snapshot.rl_advisor.model_dump_json() if snapshot.rl_advisor else "none")
    )


class ReasoningAgent(ABC):
    last_tools: list[dict] = []

    @abstractmethod
    async def reason(self, input_data) -> tuple[LlmSubgoal, str]:
        pass


class HeuristicAgent(ReasoningAgent):
    """Deterministic planner: proxy for a real LLM, and the fallback path.

    Strategy:
      * far rendezvous: coast toward a capture point ~60% of current range at a
        capped closing speed.
      * closing/final approach: fly straight toward the port with a closing speed
        proportional to sqrt(range), capped per phase.
      * proximity: approach the port axially with a very small closing speed.
      * abort (priority change): hold a safe offset and brake to zero velocity.
    """

    def __init__(self) -> None:
        self.phase_speed_caps = {
            DockingPhase.FAR_RENDEZVOUS.value: 1.5,  # m/s
            DockingPhase.CLOSING.value: 2.0,
            DockingPhase.FINAL_APPROACH.value: 0.5,
            # Below the dock velocity tolerance (0.1 m/s) so the final approach
            # never blows through the port faster than the docked condition.
            DockingPhase.PROXIMITY.value: 0.05,
            DockingPhase.DOCKED.value: 0.0,
        }

    def plan(self, input_data: ReasoningInput) -> LlmSubgoal:
        """Synchronous deterministic planner (also used by the RL env).

        In hybrid mode (``input_data.rl_advisor`` set) it *adopts* the RL
        policy's advisory suggestion — capped to the phase closing-speed and
        only when it is safe (reduces range, finite). Abort always overrides
        the advisor: the policy knows nothing about a priority change.
        """
        phase = input_data.phase
        r = np.asarray(input_data.position_m, dtype=float)
        current_vel = np.asarray(input_data.velocity_mps, dtype=float)

        if np.linalg.norm(r) < 1e-9:
            target_pos = np.zeros(3)
            target_vel = np.zeros(3)
            closing = 0.0
            rationale = "Already at the docking port."
        elif input_data.priority_change == "abort":
            # Safe hold: keep the *current* position fixed (a moving half-range
            # target would converge to the port) and brake nearly all relative
            # velocity. Never adopt the RL advisor on abort.
            target_pos = r.copy()
            target_vel = -current_vel * 0.9  # brake nearly all relative velocity
            closing = 0.0
            rationale = (
                "ABORT: mission priority changed; braking to a safe hold at current position."
            )
        else:
            if any(
                "restored" not in a.detail and a.type.value == "sensor_dropout"
                for a in input_data.anomaly_context
            ):
                return LlmSubgoal(
                    target_position_m=r.tolist(),
                    target_velocity_mps=[0.0, 0.0, 0.0],
                    closing_speed_mps=0.0,
                    rationale="Sensor reading stale: hold and brake until readings are restored.",
                )
            adopted = self._adopt_rl_advisor(input_data, phase)
            if adopted is not None:
                return adopted
            target_pos = r * (0.6 if phase == DockingPhase.FAR_RENDEZVOUS.value else 0.5)
            closing = min(
                self.phase_speed_caps.get(phase, 1.0),
                float(0.25 * np.sqrt(np.linalg.norm(r))),
            )
            target_vel = -target_pos / max(np.linalg.norm(target_pos), 1e-9) * closing
            rationale = (
                f"Phase {phase}: close toward port at {closing:.3f} m/s "
                f"(range {np.linalg.norm(r):.1f} m)."
            )

        return LlmSubgoal(
            target_position_m=[float(v) for v in target_pos],
            target_velocity_mps=[float(v) for v in target_vel],
            closing_speed_mps=float(closing),
            rationale=rationale,
        )

    def _adopt_rl_advisor(self, input_data: ReasoningInput, phase: str) -> LlmSubgoal | None:
        """Adopt the RL advisor's suggestion if it is safe; else None (fall back)."""
        sugg = input_data.rl_advisor
        if sugg is None:
            return None
        r = np.asarray(input_data.position_m, dtype=float)
        target_pos = np.asarray(sugg.suggested_position_m, dtype=float)
        target_vel = np.asarray(sugg.suggested_velocity_mps, dtype=float)
        current_range = float(np.linalg.norm(r))
        suggested_range = float(np.linalg.norm(target_pos))

        # Safety gate: the suggestion must reduce (or hold) range and be finite.
        if not (np.all(np.isfinite(target_pos)) and np.all(np.isfinite(target_vel))):
            return None
        if suggested_range >= current_range or np.dot(target_vel, r) >= 0:
            return None
        # Use learned velocity advice with a waypoint that still leads to the port.
        target_pos = r * 0.5

        cap = self.phase_speed_caps.get(phase, 1.0)
        v_norm = float(np.linalg.norm(target_vel))
        if v_norm > cap:
            target_vel = target_vel / v_norm * cap
        closing = min(float(np.linalg.norm(target_vel)), sugg.closing_speed_mps)
        rationale = (
            f"RL advisor adopted (lookahead {sugg.lookahead_s:.0f}s): follow policy "
            f"suggestion at {closing:.3f} m/s (range {current_range:.1f} -> {suggested_range:.1f} m)."
        )
        return LlmSubgoal(
            target_position_m=[float(v) for v in target_pos],
            target_velocity_mps=[float(v) for v in target_vel],
            closing_speed_mps=float(closing),
            rationale=rationale,
        )

    async def reason(self, input_data: ReasoningInput) -> tuple[LlmSubgoal, str]:
        return self.plan(input_data), "heuristic"


def provider_has_key(provider):
    if provider == "heuristic":
        return True
    from dotenv import dotenv_values

    dotenv = dotenv_values(".env")
    return any(
        os.environ.get(key) or dotenv.get(key) for key in PROVIDER_ENV_KEYS.get(provider, ())
    )


class LangChainAgent(ReasoningAgent):
    """A small tool loop: inspect, preview, and submit one structured maneuver."""

    def __init__(self, provider, model=None):
        from dotenv import dotenv_values
        from langchain_openai import ChatOpenAI

        settings = get_settings()
        dotenv = dotenv_values(".env")
        key = next(
            (
                os.environ.get(k) or dotenv.get(k)
                for k in PROVIDER_ENV_KEYS[provider]
                if os.environ.get(k) or dotenv.get(k)
            ),
            None,
        )
        if not key:
            raise ValueError(f"No server-side API key configured for {provider}")
        self.provider = provider
        self.last_tools = []
        defaults = {
            "vertex": settings.llm_model_vertex,
            "openai": settings.llm_model,
            "groq": settings.llm_model_groq,
            "openrouter": settings.llm_model_openrouter,
            "anthropic": "claude-sonnet-4-5",
        }
        self.model = model or defaults[provider]
        if provider == "vertex":
            from langchain_google_genai import ChatGoogleGenerativeAI

            self.chat = ChatGoogleGenerativeAI(
                model=self.model,
                api_key=key,
                vertexai=True,
                temperature=0,
                timeout=settings.llm_timeout_s,
                max_retries=0,
                max_output_tokens=3000,
                thinking_level="low",
                include_thoughts=False,
            )
        elif provider == "anthropic":
            from langchain_anthropic import ChatAnthropic

            self.chat = ChatAnthropic(
                model=self.model,
                api_key=key,
                timeout=settings.llm_timeout_s,
                max_retries=0,
            )
        else:
            self.chat = ChatOpenAI(
                model=self.model,
                api_key=key,
                base_url=settings.llm_base_url or PROVIDER_BASE_URLS[provider],
                timeout=settings.llm_timeout_s,
                max_retries=0,
            )

    async def reason(self, input_data):
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
        from langchain_core.tools import StructuredTool

        from app.llm.tools import docking_tools

        def submit_maneuver(
            target_position_m,
            target_velocity_mps,
            closing_speed_mps,
            rationale,
            alternatives=None,
            rl_assessment="",
        ):
            return LlmSubgoal(
                target_position_m=target_position_m,
                target_velocity_mps=target_velocity_mps,
                closing_speed_mps=closing_speed_mps,
                rationale=rationale,
                alternatives=alternatives or [],
                rl_assessment=rl_assessment,
            )

        submit = StructuredTool.from_function(
            submit_maneuver,
            name="submit_maneuver",
            args_schema=LlmSubgoal,
            description="Submit the next bounded maneuver and a concise explanation with rejected alternatives.",
        )
        tools = docking_tools(input_data)
        lookup = {t.name: t for t in tools}
        self.last_tools = [{"name": t.name, "result": t.invoke({})} for t in tools[:4]]
        chat = self.chat.bind_tools(tools + [submit])
        messages = [
            SystemMessage(
                content=(
                    "Plan a satellite docking subgoal in a local frame: X/Y horizontal, Z vertical. "
                    "Use the read-only tools to inspect separation, capture, motion limits and learned PPO advice. "
                    "Submit one maneuver. Reduce separation, brake before capture, and respect both envelopes. "
                    "For an approach choose a port-directed waypoint around half the current separation. "
                    "The controller brakes at that waypoint: do not copy an RL lookahead point only centimetres "
                    "ahead, which would stall the approach before the next replan. Learned velocity is advisory. "
                    "A positive minimum speed is only a transit preference; allow zero for braking and docking. "
                    "For abort hold current position and brake. For sensor loss brake conservatively. "
                    "Compare learned advice against limits and explain adoption or rejection. "
                    "RL availability is given by inspect_rl_heuristic; never claim advice is missing "
                    "when its proposal is present. Its status distinguishes disabled from inference failure. "
                    "Physics continues while you plan; readings are timestamped snapshots. "
                    "Your response is rechecked against the latest state. Preserve large braking margins. "
                    "Provide rationale in plain natural-language sentences for an operator: explain measured "
                    "separation and velocity, the chosen direction and safe speed, and why it fits the readings. "
                    "Provide rl_assessment explaining adoption, limitation or rejection of the learned advice. "
                    "Explain rejected alternatives in ordinary language. These are decision explanations, "
                    "not private deliberation. "
                    "Capture is independently gated at at most 1.25 m. Do not claim capture yourself."
                )
            ),
            HumanMessage(
                content=build_prompt(input_data) + "\nTool readings=" + json.dumps(self.last_tools)
            ),
        ]
        for _ in range(4):
            if self.provider == "vertex":
                response = await chat.ainvoke(messages, tool_choice="any")
            else:
                response = await chat.ainvoke(messages)
            messages.append(response)
            if not response.tool_calls:
                raise ValueError("Provider did not return a tool call")
            result = None
            for call in response.tool_calls:
                if call["name"] == submit.name:
                    result = LlmSubgoal.model_validate(call["args"])
                    output = {"accepted": True}
                elif call["name"] in lookup:
                    output = lookup[call["name"]].invoke(call["args"])
                    self.last_tools.append(
                        {"name": call["name"], "arguments": call["args"], "result": output}
                    )
                else:
                    output = {"error": "Unknown tool"}
                messages.append(ToolMessage(content=json.dumps(output), tool_call_id=call["id"]))
            if result is not None:
                return result, self.provider
        raise ValueError("Provider exhausted the four-round tool budget")


class ReasoningAgentFactory:
    @staticmethod
    def build(provider=None, fallback_provider=None, model=None):
        provider = provider or get_settings().mode
        if provider == "heuristic":
            return HeuristicAgent()
        if provider not in PROVIDER_ENV_KEYS:
            raise ValueError(f"Unknown provider: {provider}")
        return LangChainAgent(provider, model)

    @staticmethod
    def heuristic():
        return HeuristicAgent()


async def with_retry_heuristic_fallback(
    agent, input_data, heuristic, max_retries=2, backoff_s=0.25
):
    for attempt in range(max_retries + 1):
        try:
            return await asyncio.wait_for(agent.reason(input_data), get_settings().llm_timeout_s)
        except Exception:
            if attempt < max_retries:
                await asyncio.sleep(backoff_s * (attempt + 1))
    subgoal = heuristic.plan(input_data)
    subgoal.rationale = (
        "Provider unavailable or invalid response; deterministic fallback. " + subgoal.rationale
    )
    return subgoal, "heuristic_fallback"
