"""Export real training curves, randomized controller evaluations, and SHA-256 hashes."""

import argparse
import asyncio
import csv
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

from app.config import get_settings
from app.llm.reasoning_agent import HeuristicAgent
from app.schemas.docking import OrbitalElements, SatelliteState, SimulateRequest, SimulationConfig
from app.sessions.store import Session
from app.simulation.runner import SimulationRunner


async def evaluate(directory, episodes, start_seed, checkpoint):
    import os

    os.environ["LLM_DOCKING_RL_MODEL_PATH"] = str(directory / f"{checkpoint}.zip")
    os.environ["LLM_DOCKING_RL_NORMALIZE_PATH"] = str(directory / "ppo_dock_vecnormalize.pkl")
    get_settings.cache_clear()
    rows = []
    for controller, advisor in [("lqr", False), ("pid", False), ("rl", False), ("lqr", True)]:
        for seed in range(start_seed, start_seed + episodes):
            rng = np.random.default_rng(seed)
            direction = rng.normal(size=3)
            position = direction / np.linalg.norm(direction) * rng.uniform(5, 80)
            quat = rng.normal(size=4)
            quat /= np.linalg.norm(quat)
            request = SimulateRequest(
                primary=SatelliteState(orbital_elements=OrbitalElements(semi_major_axis_m=6878000)),
                secondary=SatelliteState(
                    position_m=position.tolist(),
                    velocity_mps=rng.normal(0, 0.15, 3).tolist(),
                    orientation_quat=quat.tolist(),
                    angular_velocity_radps=rng.normal(0, 0.01, 3).tolist(),
                ),
                config=SimulationConfig(
                    controller=controller, rl_advisor_enabled=advisor, max_steps=600, seed=seed
                ),
            )
            session = Session(f"{controller}-{'hybrid' if advisor else 'baseline'}-{seed}")
            await SimulationRunner(session, request, agent=HeuristicAgent()).run()
            summary = session.summary
            final = summary.final_secondary
            rows.append(
                {
                    "controller": controller,
                    "rl_advisor": advisor,
                    "seed": seed,
                    "status": summary.status,
                    "failure_reason": summary.failure_reason,
                    "initial_position_m": position.tolist(),
                    "steps": summary.steps_completed,
                    "final_range_m": float(np.linalg.norm(final.position_m)) if final else None,
                    "final_speed_mps": float(np.linalg.norm(final.velocity_mps)) if final else None,
                    "delta_v_mps": summary.metrics.delta_v_mps,
                    "capture": session.capture,
                }
            )
            print(f"{controller} advisor={advisor} seed={seed}: {summary.status}", flush=True)
    return rows


def export_curves(directory):
    rows = []
    for file in sorted((directory / "tensorboard").rglob("events.out.tfevents.*")):
        accumulator = EventAccumulator(str(file), size_guidance={"scalars": 0})
        accumulator.Reload()
        for tag in accumulator.Tags()["scalars"]:
            rows += [
                {"tag": tag, "step": x.step, "value": x.value, "wall_time": x.wall_time}
                for x in accumulator.Scalars(tag)
            ]
    with (directory / "tensorboard_scalars.csv").open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["tag", "step", "value", "wall_time"])
        writer.writeheader()
        writer.writerows(rows)
    tags = [
        tag
        for tag in [
            "rollout/ep_rew_mean",
            "train/value_loss",
            "train/policy_gradient_loss",
            "eval/success_rate",
        ]
        if any(row["tag"] == tag for row in rows)
    ]
    if tags:
        fig, axes = plt.subplots(len(tags), 1, figsize=(9, 3 * len(tags)), squeeze=False)
        for axis, tag in zip(axes.flat, tags, strict=True):
            data = sorted([r for r in rows if r["tag"] == tag], key=lambda r: r["step"])
            axis.plot([r["step"] for r in data], [r["value"] for r in data])
            axis.set(title=tag, xlabel="Environment timesteps")
            axis.grid(alpha=0.2)
        fig.tight_layout()
        fig.savefig(directory / "training_curves.png", dpi=160)
        plt.close(fig)
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--episodes", type=int, default=30)
    parser.add_argument("--start-seed", type=int, default=50000)
    parser.add_argument("--checkpoint", default="ppo_dock")
    args = parser.parse_args()
    if args.episodes < 1:
        parser.error("At least one held-out episode is required")
    directory = args.run_dir
    rows = asyncio.run(evaluate(directory, args.episodes, args.start_seed, args.checkpoint))
    aggregates = []
    for controller, advisor in [("lqr", False), ("pid", False), ("rl", False), ("lqr", True)]:
        trials = [r for r in rows if r["controller"] == controller and r["rl_advisor"] == advisor]
        count = sum(r["status"] == "docked" for r in trials)
        n = len(trials)
        p = count / n
        # Wilson interval: small samples must carry uncertainty.
        center = (p + 1.96**2 / (2 * n)) / (1 + 1.96**2 / n)
        margin = 1.96 * np.sqrt(p * (1 - p) / n + 1.96**2 / (4 * n**2)) / (1 + 1.96**2 / n)
        aggregates.append(
            {
                "controller": controller,
                "rl_advisor": advisor,
                "docked": count,
                "trials": n,
                "success_rate": p,
                "wilson_95_percent": [max(0.0, center - margin), min(1.0, center + margin)],
            }
        )
    report = {
        "scope": "Research simulation; randomized 5-80 m starts, random attitude, 600 s budget; heuristic planner, no provider calls",
        "checkpoint": args.checkpoint,
        "aggregate": aggregates,
        "trials": rows,
    }
    (directory / "evaluation.json").write_text(json.dumps(report, indent=2))
    scalars = export_curves(directory)
    files = [p for p in directory.rglob("*") if p.is_file() and p.name != "manifest.json"]
    manifest = {
        "files": {
            str(p.relative_to(directory)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files
        },
        "tensorboard_scalar_count": scalars,
        "source_sha256": {
            str(p.relative_to(Path("src"))): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path("src").rglob("*.py")
        },
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps(aggregates, indent=2))


if __name__ == "__main__":
    main()
