"""Evaluate controllers through the REAL SimulationRunner.

Rolls out N seeds × controller types and reports the outcomes that matter —
docked / diverged / fuel-out / timed-out (and diverged) counts, plus mean
Δv / ISE / LLM-call metrics — rather than training reward.

Why this exists: a rising training ``ep_rew_mean`` is necessary but NOT
sufficient evidence the policy learned the intended behavior. A policy that
learns to fail fast and cheap (fly away immediately) produces a clean-looking
improving reward curve while doing the opposite of the task. This script runs
the actual production pipeline (same runner, same dynamics, same sub-goal
planner) and reports the terminal outcomes — run it periodically against
checkpoints while training.

Example
-------
    # All classical controllers, no RL model needed:
    python -m app.simulation.rl.evaluate_policy --controllers pid,lqr --seeds 5

    # Include the trained RL policy:
    python -m app.simulation.rl.evaluate_policy --controllers pid,lqr,rl --seeds 5 \
        --rl-model models/rl/ppo_dock.zip --rl-normalize models/rl/ppo_dock_vecnormalize.pkl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.llm.reasoning_agent import HeuristicAgent
from app.schemas.docking import (
    OrbitalElements,
    SatelliteState,
    SimulateRequest,
    SimulationConfig,
)
from app.sessions.store import Session
from app.simulation.runner import SimulationRunner

LEO_SMA_M = 6_878_000.0


def make_request(controller: str, seed: int, range_m: float, max_steps: int, max_range_m: float) -> SimulateRequest:
    orbit = OrbitalElements(semi_major_axis_m=LEO_SMA_M)
    primary = SatelliteState(orbital_elements=orbit)
    secondary = SatelliteState(position_m=[range_m, 0.0, 0.0], orbital_elements=orbit)
    return SimulateRequest(
        primary=primary,
        secondary=secondary,
        config=SimulationConfig(
            controller=controller,
            max_steps=max_steps,
            max_range_m=max_range_m,
            llm_enabled=True,
            llm_cadence_steps=10,
            seed=seed,
        ),
    )


async def run_trial(controller: str, seed: int, args: argparse.Namespace) -> dict[str, Any]:
    request = make_request(controller, seed, args.range_m, args.max_steps, args.max_range_m)
    session = Session(session_id=f"{controller}-seed{seed}")
    runner = SimulationRunner(session=session, request=request, agent=HeuristicAgent())
    await runner.run()
    summary = session.summary
    assert summary is not None

    final = summary.final_secondary
    final_range = float(sum(summary.final_secondary.position_m[i] ** 2 for i in range(3)) ** 0.5) if final else -1.0
    m = summary.metrics
    return {
        "controller": controller,
        "seed": seed,
        "status": summary.status,
        "stop_reason": summary.stop_reason.value if summary.stop_reason else None,
        "failure_reason": summary.failure_reason.value if summary.failure_reason else None,
        "steps": summary.steps_completed,
        "final_range_m": round(final_range, 3),
        "delta_v_mps": round(m.delta_v_mps, 3),
        "ise": round(m.ise, 3),
        "llm_calls": m.total_llm_calls,
        "llm_fallbacks": m.llm_fallback_calls,
    }


def _parse_controllers(raw: str) -> list[str]:
    controllers = [c.strip() for c in raw.split(",") if c.strip()]
    allowed = {"pid", "lqr", "rl"}
    bad = set(controllers) - allowed
    if bad:
        sys.exit(f"Unknown controller(s): {sorted(bad)} (allowed: {sorted(allowed)})")
    return controllers


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Evaluate controllers through the real SimulationRunner.")
    p.add_argument("--controllers", type=str, default="pid,lqr",
                   help="Comma-separated: pid,lqr,rl")
    p.add_argument("--seeds", type=int, default=5, help="Number of random seeds per controller.")
    p.add_argument("--range-m", type=float, default=50.0, help="Initial chaser range [m].")
    p.add_argument("--max-steps", type=int, default=600)
    p.add_argument("--max-range-m", type=float, default=10_000.0,
                   help="Divergence guard bound (None disables).")
    p.add_argument("--rl-model", type=str, default=None, help="Trained policy zip (controller 'rl').")
    p.add_argument("--rl-normalize", type=str, default=None, help="VecNormalize stats pkl (controller 'rl').")
    p.add_argument("--out", type=str, default=None, help="Optional JSON report path.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    controllers = _parse_controllers(args.controllers)

    if "rl" in controllers:
        model = args.rl_model or os.environ.get("LLM_DOCKING_RL_MODEL_PATH")
        norm = args.rl_normalize or os.environ.get("LLM_DOCKING_RL_NORMALIZE_PATH")
        if not model or not norm:
            sys.exit(
                "controller 'rl' needs a trained policy: pass --rl-model/--rl-normalize "
                "(or set LLM_DOCKING_RL_MODEL_PATH / LLM_DOCKING_RL_NORMALIZE_PATH). "
                "Train one with: python -m app.simulation.rl.train_ppo"
            )
        for path in (model, norm):
            if not Path(path).is_file():
                sys.exit(f"RL artifact not found: {path}")
        # Must be set before the first Settings() is cached (SimulationRunner).
        os.environ["LLM_DOCKING_RL_MODEL_PATH"] = model
        os.environ["LLM_DOCKING_RL_NORMALIZE_PATH"] = norm

    async def _run_all() -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for controller in controllers:
            for seed in range(args.seeds):
                row = await run_trial(controller, seed, args)
                rows.append(row)
                print(
                    f"  {controller:<4} seed {seed}: {row['status']:<7} "
                    f"steps={row['steps']:<4} range={row['final_range_m']:>8.2f}m "
                    f"dv={row['delta_v_mps']:>7.2f} m/s ise={row['ise']:>10.2f}"
                )
        return rows

    rows = asyncio.run(_run_all())

    # ---- aggregate table ----
    print("\n=== Summary (docked / diverged / fuel-out / timed-out) ===")
    header = f"{'controller':<10} {'docked':>7} {'diverged':>8} {'fuel_out':>8} {'timed_out':>9} {'mean dv':>9} {'mean ise':>10}"
    print(header)
    print("-" * len(header))
    report: dict[str, Any] = {"trials": rows, "aggregate": {}}
    for controller in controllers:
        sub = [r for r in rows if r["controller"] == controller]
        n = len(sub) or 1
        counts = {
            "docked": sum(1 for r in sub if r["status"] == "docked"),
            "diverged": sum(1 for r in sub if r["failure_reason"] == "diverged"),
            "fuel_out": sum(1 for r in sub if r["failure_reason"] == "fuel_exhausted"),
            "timed_out": sum(
                1 for r in sub
                if r["failure_reason"] in ("max_steps_exceeded", "max_time_exceeded")
            ),
        }
        docked = [r for r in sub if r["status"] == "docked"] or sub
        agg = {
            **counts,
            "mean_delta_v_mps": round(sum(r["delta_v_mps"] for r in docked) / len(docked), 3),
            "mean_ise": round(sum(r["ise"] for r in docked) / len(docked), 3),
            "mean_llm_calls": round(sum(r["llm_calls"] for r in sub) / len(sub), 2),
        }
        report["aggregate"][controller] = agg
        print(
            f"{controller:<10} {agg['docked']:>7} {agg['diverged']:>8} {agg['fuel_out']:>8} "
            f"{agg['timed_out']:>9} {agg['mean_delta_v_mps']:>9} {agg['mean_ise']:>10}"
        )

    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2))
        print(f"\nReport written to {args.out}")


if __name__ == "__main__":
    main()
