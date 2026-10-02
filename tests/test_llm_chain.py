"""Offline checks for the actual LangChain tool loop and provider fallback."""

import pytest
from langchain_core.messages import AIMessage

from app.llm.reasoning_agent import (
    HeuristicAgent,
    LangChainAgent,
    ReasoningAgent,
    ReasoningInput,
    with_retry_heuristic_fallback,
)
from app.llm.tools import docking_tools


def snapshot():
    return ReasoningInput(
        step=0,
        sim_time_s=0.0,
        phase="final_approach",
        range_m=20.0,
        position_m=[20.0, 0.0, 0.0],
        velocity_mps=[-0.1, 0.0, 0.0],
        orientation_quat=[1.0, 0.0, 0.0, 0.0],
        angular_velocity_radps=[0.0, 0.0, 0.0],
        fuel_remaining_pct=100.0,
        controller="lqr",
        capture={"eligible": False},
    )


class FakeChat:
    def __init__(self):
        self.calls = 0

    def bind_tools(self, tools):
        self.tools = tools
        return self

    async def ainvoke(self, messages):
        self.calls += 1
        if self.calls == 1:
            return AIMessage(
                content="", tool_calls=[{"name": "measure_distance", "args": {}, "id": "read"}]
            )
        assert messages[-1].tool_call_id == "read"
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "submit_maneuver",
                    "id": "plan",
                    "args": {
                        "target_position_m": [10.0, 0.0, 0.0],
                        "target_velocity_mps": [-0.1, 0.0, 0.0],
                        "closing_speed_mps": 0.1,
                        "rationale": "Close gently; the port is 20 metres away.",
                        "alternatives": ["Faster approach reduces braking margin."],
                    },
                }
            ],
        )


async def test_langchain_executes_tool_then_submits_maneuver():
    agent = object.__new__(LangChainAgent)
    agent.chat, agent.provider = FakeChat(), "test_provider"
    result, source = await agent.reason(snapshot())
    assert source == "test_provider"
    assert result.target_position_m == [10.0, 0.0, 0.0]
    assert any(
        tool["name"] == "measure_distance" and tool["result"]["distance_m"] == 20.0
        for tool in agent.last_tools
    )


async def test_outage_is_explicit_fallback():
    class Failing(ReasoningAgent):
        async def reason(self, input_data):
            raise RuntimeError("offline")

    result, source = await with_retry_heuristic_fallback(
        Failing(), snapshot(), HeuristicAgent(), max_retries=0
    )
    assert source == "heuristic_fallback"
    assert "fallback" in result.rationale


def test_geometry_tools_are_read_only_and_report_units():
    data = snapshot()
    tools = {t.name: t for t in docking_tools(data)}
    reading = tools["measure_distance"].invoke({})
    assert reading["distance_m"] == 20.0
    assert reading["closing_speed_mps"] == pytest.approx(0.1)
    assert not tools["inspect_rl_heuristic"].invoke({})["available"]
    assert data.position_m == [20.0, 0.0, 0.0]
    import json

    preview = tools["preview_maneuver"].invoke(
        {"target_position_m": [10.0, 0.0, 0.0], "target_velocity_mps": [-0.1, 0.0, 0.0]}
    )
    assert json.loads(json.dumps(preview))["reduces_range"] is True
