"""RL/PPO docking: Gymnasium env, training and evaluation CLIs.

  * ``docking_env.DockingEnv`` — the env (same physics as the service runner)
  * ``train_ppo.py`` — BC warm-start + PPO training (``python -m ...train_ppo``)
  * ``evaluate_policy.py`` — honest outcome-based eval through SimulationRunner
"""

from app.simulation.rl.docking_env import DockingEnv, build_rl_observation

__all__ = ["DockingEnv", "build_rl_observation"]
