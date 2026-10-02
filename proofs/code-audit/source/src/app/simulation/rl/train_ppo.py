"""Train an expert-initialized PPO policy; save the data needed to reproduce it.

Use --device cuda:0 in Kaggle. Two independent processes can use cuda:0 and
cuda:1 with different seeds. A small MLP does not pool the GPUs' memory.
"""

import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from pathlib import Path

import numpy as np
import torch
from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.vec_env import DummyVecEnv, VecNormalize
from torch.utils.data import DataLoader, TensorDataset

from app.schemas.docking import MotionLimits
from app.simulation.controllers import ControlContext, build_controller
from app.simulation.rl.docking_env import DockingEnv


def environment(seed, max_steps=600):
    return DockingEnv(
        seed=seed,
        max_steps=max_steps,
        initial_range_m=(5.0, 80.0),
        motion_limits=MotionLimits(),
        diverged_penalty=200.0,
        shaping_scale=3.0,
    )


def expert_trajectories(episodes, seed, max_steps):
    env = environment(seed, max_steps)
    controller = build_controller("lqr", env.mass_kg, env.inertia, env.n)
    observations, actions, outcomes = [], [], []
    for episode in range(episodes):
        obs, _ = env.reset(seed=seed + episode)
        ctx = ControlContext()
        for step in range(max_steps):
            if step % env.subgoal_cadence_steps == 0:
                controller.reset(ctx)
            command = controller.compute(env.current_state, env.current_subgoal, env.dt, ctx)
            action = env.command_to_action(command)
            observations.append(obs)
            actions.append(action)
            obs, _, terminated, truncated, info = env.step(action)
            if terminated or truncated:
                outcomes.append(info["termination"] or "timeout")
                break
    env.close()
    return (
        np.asarray(observations, dtype=np.float32),
        np.asarray(actions, dtype=np.float32),
        outcomes,
    )


def warm_start(model, normalizer, observations, actions, epochs, device):
    # Fit observation statistics BEFORE cloning; PPO sees these exact normalized inputs.
    normalizer.obs_rms.update(observations)
    normalizer.training = False
    normalized = normalizer.normalize_obs(observations)
    loader = DataLoader(
        TensorDataset(torch.from_numpy(normalized), torch.from_numpy(actions)),
        batch_size=512,
        shuffle=True,
    )
    optimizer = torch.optim.Adam(model.policy.parameters(), lr=0.001)
    losses = []
    for _ in range(epochs):
        total = 0.0
        for obs, action in loader:
            prediction = model.policy.get_distribution(obs.to(device)).distribution.mean
            loss = torch.nn.functional.mse_loss(prediction, action.to(device))
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            total += loss.item() * len(obs)
        losses.append(total / len(observations))
    with torch.no_grad():
        model.policy.log_std.fill_(-3.0)
    return losses


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timesteps", type=int, default=200000)
    parser.add_argument("--out-dir", type=Path, default=Path("models/rl"))
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-seeds", type=int, default=8)
    parser.add_argument("--n-steps", type=int, default=256)
    parser.add_argument("--batch-size", type=int, default=512)
    parser.add_argument("--lr", type=float, default=0.00001)
    parser.add_argument("--bc-episodes", type=int, default=80)
    parser.add_argument("--bc-epochs", type=int, default=30)
    parser.add_argument("--max-steps", type=int, default=600)
    parser.add_argument("--eval-freq", type=int, default=20000)
    parser.add_argument("--eval-episodes", type=int, default=12)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--resume-normalize", type=Path)
    args = parser.parse_args()
    if args.timesteps < 1 or args.n_seeds < 1 or args.bc_episodes < 1:
        parser.error("Timesteps, environment count, and expert episodes must be positive")
    if args.device.startswith("cuda") and not torch.cuda.is_available():
        parser.error("CUDA requested but no CUDA runtime is available")
    if args.resume and not args.resume_normalize:
        parser.error("Resume requires the matching --resume-normalize checkpoint")
    torch.set_num_threads(2)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    metadata = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items()}
    metadata.update(
        python=platform.python_version(),
        torch=torch.__version__,
        capture_range_m=1.25,
        initial_range_m=[5, 80],
        dt_s=1.0,
        observation="14 values: subgoal position/velocity error, quaternion, rotation rate, fuel",
        reward="bounded position cost, velocity and attitude cost, action cost, range progress, capture bonus 100",
        gpu=[
            {
                "name": torch.cuda.get_device_properties(i).name,
                "memory_bytes": torch.cuda.get_device_properties(i).total_memory,
            }
            for i in range(torch.cuda.device_count())
        ],
    )
    metadata["dependencies"] = {
        name: importlib.metadata.version(name)
        for name in ["stable-baselines3", "gymnasium", "torch", "numpy", "tensorboard", "pydantic"]
    }
    metadata["source_sha256"] = {
        str(path.relative_to(Path("src"))): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in Path("src").rglob("*.py")
    }
    metadata["motion_limits"] = MotionLimits().model_dump()
    (args.out_dir / "parameters.json").write_text(json.dumps(metadata, indent=2))
    env = DummyVecEnv(
        [
            lambda i=i: Monitor(environment(args.seed + i, args.max_steps))
            for i in range(args.n_seeds)
        ]
    )
    normalizer = VecNormalize(env, norm_obs=True, norm_reward=False)
    if args.resume:
        normalizer = VecNormalize.load(str(args.resume_normalize), env)
        normalizer.training = False
        normalizer.norm_reward = False
        model = PPO.load(str(args.resume), env=normalizer, device=args.device)
        model.tensorboard_log = str(args.out_dir / "tensorboard")
    else:
        model = PPO(
            "MlpPolicy",
            normalizer,
            device=args.device,
            seed=args.seed,
            policy_kwargs={"net_arch": [128, 128]},
            n_steps=args.n_steps,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            gamma=0.995,
            ent_coef=0.0,
            clip_range=0.1,
            n_epochs=4,
            verbose=0,
            tensorboard_log=str(args.out_dir / "tensorboard"),
        )
        observations, actions, outcomes = expert_trajectories(
            args.bc_episodes, args.seed, args.max_steps
        )
        losses = warm_start(model, normalizer, observations, actions, args.bc_epochs, args.device)
        (args.out_dir / "behavior_cloning.json").write_text(
            json.dumps(
                {"losses": losses, "outcomes": outcomes, "samples": len(observations)}, indent=2
            )
        )
        model.save(args.out_dir / "expert_initialized")
        normalizer.save(str(args.out_dir / "expert_initialized_vecnormalize.pkl"))
    eval_env = VecNormalize(
        DummyVecEnv([lambda: Monitor(environment(args.seed + 10000, args.max_steps))]),
        training=False,
        norm_reward=False,
    )
    eval_env.obs_rms = normalizer.obs_rms
    evaluation = EvalCallback(
        eval_env,
        best_model_save_path=str(args.out_dir),
        log_path=str(args.out_dir),
        n_eval_episodes=args.eval_episodes,
        eval_freq=max(1, args.eval_freq // args.n_seeds),
        deterministic=True,
        verbose=0,
    )
    checkpoint = CheckpointCallback(
        save_freq=max(1, args.eval_freq // args.n_seeds),
        save_path=str(args.out_dir / "checkpoints"),
        name_prefix="ppo_dock",
        save_vecnormalize=True,
    )
    start = time.perf_counter()
    model.learn(
        total_timesteps=args.timesteps,
        callback=[evaluation, checkpoint],
        reset_num_timesteps=not bool(args.resume),
    )
    model.save(args.out_dir / "ppo_dock")
    normalizer.save(str(args.out_dir / "ppo_dock_vecnormalize.pkl"))
    metadata.update(
        actual_timesteps=model.num_timesteps, elapsed_seconds=time.perf_counter() - start
    )
    (args.out_dir / "parameters.json").write_text(json.dumps(metadata, indent=2))
    eval_env.close()
    normalizer.close()
    print(json.dumps({"completed": model.num_timesteps, "out_dir": str(args.out_dir)}))


if __name__ == "__main__":
    main()
