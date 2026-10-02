# Docking Lab

Satellite docking research simulator with a 3D flight dashboard, FastAPI event
streams, LangChain tools, and an expert-initialized PPO advisor.

## Run locally

Python 3.11+ and Node 20+ are required. From the project root:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev,rl]"
Copy-Item .env.example .env
cd frontend
npm ci
npm run build
cd ..
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. API reference: `/docs`. Evidence: `/proofs/`.
Vertex AI is the default provider. Set `VERTEX_API_KEY` in `.env`; use
`LLM_DOCKING_MODE=heuristic` for offline experiments. For frontend development, run `npm run dev`
in `frontend`; Vite forwards API calls to port 8000. Or run `docker compose up --build`.
Docker has not been built in this session.

Your existing `.env` is preserved. Copy the example or update the two RL paths
to select the included Kaggle policy and its matching normalization file.
Select **Use learned PPO advice** for the hybrid flow. Start, stop, capture,
and export from the dashboard.

Dashboard sessions start **100 m** apart. Any initial separation from
**2 cm to 1 km** is permitted, with optional narrower bounds. Random placement
stays inside the configured band, and invalid
manual positions cannot start a session. The request sends `initial_separation_range_m`, which
the backend validates using both three-dimensional port positions. The 2 cm
minimum applies to initial placement; the 1 km maximum also guards the running
simulation. Capture still requires at most 1.25 m, low speed, and alignment.
API clients can omit the narrower band, but must stay within 2 cm–1 km initially.
For longer approaches, increase the time and step budgets in Guidance & capture.

The secondary defaults to **0.10 m/s** total and horizontal speed, **0.05 m/s**
vertical speed, **2.5 N** total thrust, and **0.005 m/s²** total local acceleration.
Applied thrust is limited before integration. A stopping-distance envelope
brakes toward **0.02 m/s within 5 m**. These are conservative simulation settings,
not a calibrated specification of a particular spacecraft engine.
Playback defaults to **1×**: each 0.5 s physics step is paced over 0.5 s of wall
time. A 100 m approach takes at least 16 minutes, plus planning waits.
Accelerated playback is explicitly selectable for experiments and does not
increase the physical speed limit. The clock and spacecraft state are held
while the planner responds; Stop cancels that wait.

The primary spacecraft uses NASA's [International Space Station 3D model](https://science.nasa.gov/resource/international-space-station-3d-model/),
served locally with optimized textures and geometry compression. Its forward
PMA-2 port is placed at the simulation origin. The chaser is an authored futuristic
concept with faceted armour, illuminated rails, optics, and manoeuvring nozzles.
The Earth backdrop is illustrative. Four cameras provide **Track chaser**,
**ISS + chaser**, **Full ISS**, and **Target port** views.
Drag to orbit and scroll to zoom. A shared **X/Y/Z coordinate grid** rotates with
the same camera; select automatic spacing or 1 cm, 10 cm, 1 m, 10 m, and 100 m
divisions. Physics Z points up. Flight trails, relative
velocity vectors, and each port's capture envelope can be toggled independently.
Positions and attitudes follow server telemetry; the capture announcement
appears only after the server confirms docking. Reduced motion removes spatial
transitions, and offscreen rendering pauses. Fonts are served locally.
See `frontend/public/models/README.md` for NASA attribution, asset hashes, and
the display alignment. Visual geometry does not add a hull-collision physics model.

To reproduce the browser checks with the backend running and frontend built:

```powershell
python -m pip install playwright
python -m playwright install chromium
python scripts/verify_dashboard.py
```

This checks hybrid guidance, manual capture, stop/restart, exports, camera and
overlay controls, and responsive layouts. Chromium screenshots and the complete
session export are saved in `.impeccable/review/`.

## Execution flow

1. Configure both docking-port states, mass, fuel, orientation, rotation,
   capture radii, and speed envelopes. Seeded random placement is repeatable.
   X/Y are horizontal; Z is vertical. Units are metres, seconds, m/s, kg,
   Newtons, and radians/s.
2. FastAPI creates a session and advances relative Clohessy-Wiltshire dynamics
   and rigid-body attitude. The primary supplies the orbit and prescribed
   local position/velocity. It is a cooperative reference target; the secondary
   is controlled. The primary is not optimized by a second control agent.
3. At each cadence, a fresh snapshot goes to the planner. LangChain provides
   `measure_distance`, `inspect_capture_gate`, `inspect_actuators`,
   `inspect_rl_heuristic`, `preview_maneuver`, and `submit_maneuver` tools.
   The model returns a target, short justification, and rejected alternatives.
   The right panel displays the latest natural-language explanation, learned
   advice assessment, applied limits, and alternatives above the decision history.
   Tools inspect or preview; only the runner applies actuator commands.
4. Optional PPO advice uses the same observation definition as training.
   The deterministic fallback adopts safe inward velocity advice while keeping
   a port-directed waypoint. The LLM receives the full learned proposal and
   can adopt, cap, or reject it. The log shows tool readings and actual sources.
5. Commands pass through per-axis force/torque, total thrust, acceleration,
   configured velocity limits, and the stopping-distance envelope.
   When no bounded force can maintain a limit after a disturbance, the run
   fails explicitly rather than editing the physical velocity. Minimum speed
   is a transit preference; braking and docking permit zero speed.
6. Capture requires separation **at most min(1.25 m, primary radius, secondary
   radius, configured range)**, relative speed at most the configured tolerance
   (dashboard default 0.02 m/s; API default 0.1 m/s), attitude error at most the configured tolerance (default
   2 degrees), and relative rotation at most 0.05 rad/s. Manual and automatic
   capture share the same gate. Abort and stale sensor readings inhibit capture.

The Three.js spacecraft are schematic models with docking-port origins. Mesh
sizes and animations are visual aids; backend coordinates determine numerical
results. The physics is a local linearized model; fuel is simplified. Contact
mechanics, body collision, sensor estimation, structural dynamics, actual
communications latency, and flight hardware are outside this simulator.
**This is research software, not flight-certified software.**

## Providers

Set the matching server-side key in `.env`, restart, and select the provider:

| Provider | Key |
| --- | --- |
| Vertex AI (default) | `VERTEX_API_KEY` |
| OpenAI | `OPENAI_API_KEY` |
| Groq | `GROQ_API_KEY` |
| OpenRouter | `OPENROUTER_API_KEY` |
| Anthropic | `ANTHROPIC_API_KEY` |

The optional model field overrides the server default. Set
`LLM_DOCKING_LLM_MODEL_VERTEX` to change Vertex's model. The supplied credential
successfully invoked **`gemini-3.8-flash`** through the Vertex express-mode
endpoint and the LangChain tool loop in this session. The server uses Google
Cloud API-key authentication; the credential remains in ignored `.env`.
Set
`LLM_DOCKING_LLM_BASE_URL` only for the OpenAI-compatible endpoint you intend
to use. Credentials never enter the frontend, notebook, exports, or proofs.
Provider failures and invalid output use labelled deterministic fallback.
The dashboard shows short explanations, not private chain-of-thought.
The included benchmark uses the deterministic planner, so it does not establish
real-provider performance. Separate live Vertex checks validate connectivity,
tool calling and explanations; they do not establish a mission success rate.
The complete live Vertex + PPO demonstration is in `proofs/conservative-vertex/`.

## Kaggle notebook

`notebook.ipynb` packages the Python source, dependency installation, two-T4
checks, training controls, TensorBoard, fresh-seed evaluation, manifest checks,
checkpoint resume, and evidence ZIP export. Enable Internet and GPU T4 x2.
The notebook bundles the current source. Its retained outputs describe the
earlier training runs, whose exact source snapshots remain in `/proofs`.
Rerun evaluation when changing dynamics or control limits.
Run in order; monitoring cells are nonblocking and can be rerun.
Two GPUs train independent seeds, with separate memory. A small PPO MLP can
run faster on CPU; no GPU speed advantage is claimed.

Training: LQR expert trajectories -> behavior cloning on normalized inputs ->
PPO with frozen observation statistics. Every checkpoint must be paired with
its matching VecNormalize file. Never mix files between seeds/checkpoints.
`best_model.zip` uses the frozen final normalizer. Intermediate pairs live in
`checkpoints/`.

```powershell
python -m app.simulation.rl.train_ppo --device cpu --seed 42 --timesteps 200000 --out-dir proofs/my-run
python -m app.simulation.rl.proofs --run-dir proofs/my-run --episodes 50 --start-seed 70000
tensorboard --logdir proofs
```

`scripts/kaggle_runtime.py` can execute a Python file in an existing Jupyter
kernel using `requests` and `websocket-client`. Its credential-bearing runtime
URL is stored outside the project at `~/.codex/kaggle-docking-runtime.txt`.
The helper never restarts the kernel. Runtime credentials are not packaged.

## Evidence and checks

See `proofs/README.md`. Each run contains `evaluation.json`, raw TensorBoard
events, `tensorboard_scalars.csv`, `training_curves.png`, `parameters.json`,
and `manifest.json`. Keep failed trials and scenario limits when presenting.
Hashes establish file integrity, not independent endorsement. Confidence
intervals accompany the success rates. LQR with PPO advice is the recommended
presentation mode; direct PPO is an experimental controller.

```powershell
python -m pytest
python -m ruff check src tests scripts
python scripts/verify_proofs.py
```

One process allows four active sessions and retains the latest 32 completed
sessions in memory. Export before restarting. For public multi-process use,
add persistent storage, authentication, rate limits, and a worker queue.

## Main files

| File | Responsibility |
| --- | --- |
| `frontend/src/main.js` | Configuration, SSE, log, telemetry |
| `frontend/src/scene.js` | Spacecraft geometry and animation |
| `src/app/simulation/runner.py` | One simulation loop |
| `src/app/simulation/safety.py` | Motion limits and capture gate |
| `src/app/llm/reasoning_agent.py` | Deterministic and LangChain planners |
| `src/app/llm/tools.py` | Geometry, actuator, RL and preview tools |
| `src/app/simulation/rl/train_ppo.py` | Expert initialization and PPO |
| `src/app/simulation/rl/proofs.py` | Evaluation, curves, hashes |

## API

`POST /api/v1/docking/simulate` returns stream/summary URLs. Session routes
also provide `/events`, `/export`, `/cancel`, and `/dock`. SSE uses monotonic
IDs and independent viewer cursors. Reconnect with `Last-Event-ID` or `?after=N`.
`/api/v1/capabilities` reports configured providers/artifacts without keys.
