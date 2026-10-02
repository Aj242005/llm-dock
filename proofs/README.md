# Measured docking experiments

These artifacts were produced in the user's live Kaggle runtime using two
Tesla T4 GPUs (14.56 GiB each). No benchmark numbers are illustrative data.

## Final experiment

`kaggle-final-seed-42/` and `kaggle-final-seed-137/` each contain an independent
expert-initialized PPO run with **200,704 actual environment steps**, 100 expert
episodes, 50 cloning epochs, eight environments, frozen observation
normalization, and a learning rate of 0.00001. Parameters include dependency
versions, GPU names, memory, reward description, and training source hashes.

Each checkpoint was evaluated through the actual backend on seeds
**70000–70049**, separate from the training and periodic evaluation seeds.
Starts have randomized directions at 5–80 m, random attitudes, small initial
velocity and rotation, and a 600-second time budget. The primary is the
cooperative local-frame target. Capture requires the common 1.25 m range,
relative speed ≤0.1 m/s, attitude error ≤2°, and rotation ≤0.05 rad/s.

| Method | Seed 42 checkpoint | Seed 137 checkpoint |
| --- | --- | --- |
| LQR with deterministic planner | 50/50 docked | 50/50 docked |
| PID with deterministic planner | 50/50 docked | 50/50 docked |
| PPO with deterministic planner | 50/50 docked | 50/50 docked |
| LQR with PPO advice and deterministic planner | 50/50 docked | 50/50 docked |

Each 50/50 result has a Wilson 95% interval of approximately **92.9–100%**.
The same scenario seeds were used for paired comparisons; duplicate LQR/PID
trials across the two reports are not 100 independent test scenarios. Periodic
training evaluation recorded 12/12 captures at each 20,000-step checkpoint.
That evaluation sample also does not establish universal performance.

These measurements do not evaluate paid-provider LLMs, real hardware,
contact mechanics, body collision, delayed communications, or realistic sensor
uncertainty. The current experiments support a research demonstration within
their stated conditions. They do not prove a learned method is superior to
LQR/PID; all methods succeeded in this held-out sample.

## Files in each run

- `parameters.json`: actual steps, hardware, configuration, dependency versions
  and training source hashes for the final runs.
- `behavior_cloning.json`: expert outcomes and cloning losses.
- `ppo_dock.zip` + `ppo_dock_vecnormalize.pkl`: matched final inference pair.
- `expert_initialized.zip`: policy before PPO fine-tuning.
- `checkpoints/`: intermediate models and their matching normalizers.
- `tensorboard/`: raw TensorBoard event files.
- `tensorboard_scalars.csv`: all recorded scalar readings and timestamps.
- `training_curves.png`: measured reward, value loss, policy loss and capture
  rate curves.
- `evaluation.json`: every held-out trial, terminal checks, failures, and
  confidence intervals.
- `manifest.json`: SHA-256 hashes of artifacts and evaluation source files.

`parameters.json.source_sha256` refers to the source at training start.
`manifest.json.source_sha256` refers to the source at evaluation. Later cleanup
and formatting can change source hashes without changing model artifacts.
The notebook packages the final readable source for rerunning the workflow.

`evaluation-source/` preserves the complete Python source whose hashes match
the final evaluation manifest. `training-source/` preserves the matching
training script, environment, safety limiter, and classical controllers used
for the final GPU training. These snapshots make the measured experiment
inspectable independently of subsequent application edits.

## Earlier results remain available

`kaggle-seed-42/` and `kaggle-seed-137/` are initial 100,352-step experiments.
`evaluation-before-fixes.json` retains the failures that exposed speed-limit,
attitude damping, and hybrid waypoint problems. Their corrected
`evaluation.json` uses the development validation seeds 50000–50029. The final
experiment uses fresh seeds and newly trained checkpoints. Do not substitute
the earlier validation sample for the final held-out experiment.

Hashes demonstrate integrity of these files; they are not independent
credentials or third-party certification. Verify locally with:

```powershell
python scripts/verify_proofs.py
tensorboard --logdir proofs
```

Open the dashboard's evidence link to view reports and plots. Export individual
sessions to retain configuration, decisions, tool readings, and applied
commands. Session data lives in memory until exported.

## Dashboard verification

`dashboard/` contains Chromium screenshots at 320, 390, 768, and 1440 pixels,
live and captured states, the latest complete hybrid session export, and
`dashboard-verification.json`. The browser workflow checks translated primary
coordinates, camera and overlay controls, manual capture, stop/restart, exports,
responsive chart labels, JavaScript errors, and horizontal overflow.

This run uses the deterministic planner with trained PPO advice, and reaches
capture at 0.510 m separation and 0.095 m/s relative speed. It does not measure
paid-provider LLM accuracy or physical spacecraft contact. The screenshots use
Chromium software WebGL; they do not establish mobile hardware performance.
Reproduce with `python scripts/verify_dashboard.py` after starting the backend
and building the frontend. Updated captures first appear in `.impeccable/review/`.

`dashboard-near-range/` records the later 5–10 m initial-separation configuration:
the 7.5 m default, rejection outside that band, bounded random placement, and
a complete hybrid docking run. Earlier dashboard and training evidence remains
unchanged for comparison.
