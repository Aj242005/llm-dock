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
simulation. Capture defaults to a 2 cm gate (maximum 3 cm), low speed, and alignment.
API clients can omit the narrower band, but must stay within 2 cm–1 km initially.
For longer approaches, increase the time and step budgets in Guidance & capture.

The secondary starts at `[80, 48, 36]` m (100 m separation), with a deliberately
misaligned attitude so simultaneous rotation and translation are visible. It defaults
to **2 m/s** total, horizontal and vertical speed, **50 N** total thrust, and
**0.1 m/s?** total local acceleration for a 500 kg concept chaser. All are configurable;
the speed inputs permit up to 20 m/s. These are simulator parameters, not a
calibrated engine specification. A stopping-distance envelope brakes before entering
the **0.3 m/s near-port zone**, then tightens to **0.004 m/s for capture**.
Playback defaults to **1?**: each 0.2 s physics step is paced over 0.2 s of wall time.
Fast rotation above 0.1 rad/s is damped while holding position first. Low-rate
attitude alignment runs alongside XYZ transfer to a **5 m stand-off** on the
primary port's positive X axis. Final approach requires stable alignment for
**1 second** and lateral entry into a **5 cm docking-axis corridor**; these
settings are editable. The provider's requested closing speed remains
an upper limit, and live telemetry displays the force, torque, attitude error and rate.
Accelerated playback is explicitly selectable for experiments and does not
increase the physical speed limit. Physics, both spacecraft states, and SSE
telemetry continue while Vertex plans in the background. The last accepted
maneuver stays active; before the first response, local detumbling can run and
translation remains subject to the motion and stopping-distance envelope. Abort and sensor-loss braking act
locally without waiting for a provider. One provider request runs at a time.
Returned plans are checked against current state and limits; responses older
than one planning interval plus the reserve, or with changed fault context, are
discarded and local braking requests fresh guidance. Decision events record
snapshot time, age, and whether the response was applied. Stop cancels the
outstanding task.

The primary spacecraft uses NASA's [International Space Station 3D model](https://science.nasa.gov/resource/international-space-station-3d-model/),
served locally with optimized textures and geometry compression. Its forward
PMA-2 docking-face centre, measured from front-plane vertices rather than the
adapter bounding-box centre, is placed at the simulation origin. The chaser is an authored futuristic
concept with faceted armour, illuminated rails, optics, and manoeuvring nozzles.
The Earth backdrop is illustrative. Four cameras provide **Track chaser**,
**ISS + chaser**, **Full ISS**, and **Target port** views.
Drag to orbit and scroll to zoom. A shared **X/Y/Z coordinate grid** rotates with
the same camera; select automatic spacing or 1 cm, 10 cm, 1 m, 10 m, and 100 m
divisions. Physics Z points up. Flight trails, relative
velocity vectors, and each port's capture envelope can be toggled independently.
Individual translation and attitude nozzles emit illustrative plumes in response
to applied force and torque. Positions and attitudes follow server telemetry; the capture announcement
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
   The model returns translation and attitude targets, a short justification, and
   rejected alternatives. The prompt explicitly coordinates both manoeuvres and
   distinguishes the chaser envelope from the primary envelope.
   The right panel displays the latest natural-language explanation, learned
   advice assessment, applied limits, and alternatives above the decision history.
   Tools inspect or preview; only the runner applies actuator commands.
4. PPO advice is enabled by default in the dashboard when a real load and
   inference probe succeeds. Switching it off is explicit. Every decision
   reports available, disabled, or unavailable, with the proposal and reason.
   It uses the same observation definition as training.
   The deterministic fallback adopts safe inward velocity advice while keeping
   a port-directed waypoint. The LLM receives the full learned proposal and
   can adopt, cap, or reject it. The log shows tool readings and actual sources.
   An expired provider response is discarded; fresh deterministic guidance
   from the current state sustains the approach while Vertex replans.
5. Commands pass through per-axis force/torque, total thrust, acceleration,
   configured velocity limits, and the stopping-distance envelope.
   Starting rotation rates are validated against the configured relative tumble
   limit (default 5 rad/s). The dashboard labels rad/s explicitly; 3 and 6 rad/s
   combine to 6.708 rad/s and exceed this limit. Runtime stops report the specific
   measured rate, range or budget condition in the right panel.
   When no bounded force can maintain a limit after a disturbance, the run
   fails explicitly rather than editing the physical velocity. Minimum speed
   is a transit preference; braking and docking permit zero speed.
6. Capture requires separation **at most min(3 cm, primary radius, secondary
   radius, configured range)**, with both radii and the range defaulting to **2 cm**.
   Relative speed must be at most the configured tolerance (**0.005 m/s** default,
   maximum 0.01 m/s), attitude error at most **1 degree** by default, and relative
   rotation at most **0.01 rad/s**. Manual and automatic capture share the same
   gate, including stable alignment and the docking-axis corridor. Abort and stale sensor readings inhibit capture.

Propellant consumption follows applied impulse: resultant engine thrust divided
by `specific_impulse_s * g0`, plus each torque-axis demand divided by the RCS
lever arm and `rcs_specific_impulse_s * g0`. Defaults are a **25 kg tank**, **220 s
engine Isp**, **60 s RCS Isp**, and **0.75 m torque lever arm**, all editable.
Coasting consumes no propellant; rotational thrusters do. Remaining kilograms,
used kilograms and current mass flow appear in the right panel. Mass and inertia
decrease with propellant use; commands are reduced if the tank empties during a
step. An explicitly supplied `fuel_consumption_rate_pct_per_s` is a legacy
load-proportional override; the dashboard omits it and uses the impulse model.


The Three.js spacecraft are schematic models with docking-port origins. Mesh
sizes and animations are visual aids; backend coordinates determine numerical
results. The physics is a local linearized model; fuel uses an equivalent-thruster
model with assumed engine efficiency and geometry. Contact
mechanics, body collision, sensor estimation, structural dynamics, actual
communications latency, and flight hardware are outside this simulator.
**This is research software, not flight-certified software.**

The live-session code audit, regression results, original reference run, and
verified Vertex-with-PPO trace are in [`proofs/code-audit/README.md`](proofs/code-audit/README.md).

The current tumbling-case verification, physical propellant accounting and
stable port-axis approach are in
[`proofs/aligned-propellant-vertex-final/README.md`](proofs/aligned-propellant-vertex-final/README.md).

The coordinated 2 cm live demonstration and its full telemetry are in
[`proofs/precision-vertex-docking/README.md`](proofs/precision-vertex-docking/README.md).
Older training success rates use their original 1.25 m gate; they do not establish
2 cm performance. The notebook packages the current gate for future training.

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
