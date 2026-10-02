"""Record a live Vertex session without exposing server credentials.

Requires the local server with Vertex and a trained policy configured.
This is one accelerated demonstration, not a statistical evaluation.
"""

import json
import time
from pathlib import Path

import httpx
import numpy as np


def main():
    output = Path("proofs/conservative-vertex")
    output.mkdir(parents=True, exist_ok=True)
    request = {
        "primary": {"orbital_elements": {"semi_major_axis_m": 6878000}},
        "secondary": {
            "position_m": [100, 0, 0],
            "motion_limits": {
                "max_speed_mps": 0.1,
                "max_horizontal_speed_mps": 0.1,
                "max_vertical_speed_mps": 0.05,
            },
        },
        "config": {
            "provider": "vertex",
            "model": "gemini-3.8-flash",
            "controller": "lqr",
            "rl_advisor_enabled": True,
            "step_interval_s": 0.5,
            "max_steps": 6000,
            "llm_cadence_steps": 500,
            "playback_speed": 1000,
            "max_thrust_n": 2.5,
            "max_acceleration_mps2": 0.005,
            "near_port_speed_mps": 0.02,
            "dock_velocity_tol_mps": 0.02,
            "fuel_consumption_rate_pct_per_s": 0.001,
            "initial_separation_range_m": [80, 120],
        },
    }
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=30) as client:
        response = client.post("/api/v1/docking/simulate", json=request)
        response.raise_for_status()
        urls = response.json()
        started = time.monotonic()
        previous_calls = -1
        while True:
            summary = client.get(urls["summary_url"]).json()
            calls = summary["metrics"]["total_llm_calls"]
            if calls != previous_calls:
                print(
                    f"Plans: {calls}; step: {summary['steps_completed']}; status: {summary['status']}",
                    flush=True,
                )
                previous_calls = calls
            if summary["status"] != "running":
                break
            if time.monotonic() - started > 900:
                client.post(urls["summary_url"] + "/cancel")
                raise RuntimeError("Live verification exceeded 15 minutes; stopped its session")
            time.sleep(1)
        export = client.get(urls["summary_url"] + "/export").json()
    (output / "session.json").write_text(json.dumps(export, indent=2), encoding="utf-8")
    telemetry = [e for e in export["events"] if e["type"] == "telemetry"]
    velocity = np.asarray([e["secondary_velocity_mps"] for e in telemetry])
    speeds = np.linalg.norm(velocity, axis=1)
    decisions = [e for e in export["events"] if e["type"] == "llm_decision"]
    checks = {
        "status": summary["status"],
        "wall_time_s": time.monotonic() - started,
        "sim_time_s": telemetry[-1]["sim_time_s"],
        "playback_speed": 1000,
        "replan_every_steps": 500,
        "max_speed_mps": float(max(speeds)),
        "max_acceleration_mps2": float(
            max(np.linalg.norm(np.diff(velocity, axis=0) / 0.5, axis=1))
        ),
        "max_thrust_n": summary["metrics"]["max_commanded_thrust_n"],
        "final_range_m": telemetry[-1]["range_m"],
        "provider_sources": [e["source"] for e in decisions],
        "learned_proposals": sum(e["rl_advisor"] is not None for e in decisions),
        "near_port_speed_ok": all(
            speed <= 0.020001
            for e, speed in zip(telemetry, speeds, strict=True)
            if e["range_m"] <= 5
        ),
        "scope": "Single accelerated live demonstration; not a measured provider success rate.",
    }
    (output / "checks.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks, indent=2))
    assert summary["status"] == "docked", summary["failure_reason"]
    assert checks["max_speed_mps"] <= 0.100001
    assert checks["max_acceleration_mps2"] <= 0.005001
    assert checks["max_thrust_n"] <= 2.500001
    assert checks["near_port_speed_ok"]
    assert all(e["source"] == "vertex" for e in decisions)
    assert checks["learned_proposals"] == len(decisions)


if __name__ == "__main__":
    main()
