# Live-session code audit — 2 October 2026

The reported null advice was traced to the real session `23148b702b92460da5c8f7690cfe6665`.
Its exported request explicitly set `rl_advisor_enabled: false`: all 14 planning
decisions therefore received no learned proposal. The UI advertised an available
checkpoint but left the advice checkbox unchecked. Of those 14 responses, only
two were applied; the others expired against the 35-second snapshot budget.
The user cancelled this run after 1645 simulated seconds.

## Fixed findings

| Priority | Finding and correction | Main location |
| --- | --- | --- |
| P1 | Available PPO advice was silently off by default. A successful inference probe now enables it; Reset restores that verified default. | `frontend/src/main.js` |
| P1 | Capability and request checks accepted corrupt policy files. Both now load the policy, validate observation/action dimensions and normalization, and run a finite prediction before reporting readiness. Invalid artifacts receive HTTP 400 before session creation. | `api/routes.py`, `controllers/rl.py`, `llm/rl_advisor.py` |
| P1 | A single inference failure permanently disabled advice for the session. Transient prediction failures now report a reason and retry at the next cadence. Persistent load failures stay cached per advisor. | `llm/rl_advisor.py`, `simulation/runner.py` |
| P1 | Expired provider responses repeatedly installed braking holds. They remain discarded, but current-state deterministic guidance now sustains progress while a fresh provider request runs. The event includes the actual recovery maneuver. | `simulation/runner.py`, `schemas/events.py` |
| P1 | Fault braking could use PPO or corrupted sensor readings; the capture UI could still claim eligibility during abort/dropout. An independent LQR safety channel uses simulator truth, and API/telemetry capture eligibility is explicitly blocked. | `simulation/runner.py` |
| P1 | A moving primary's velocity offset weakened the relative stopping-speed bound. Applied forces now satisfy both absolute spacecraft envelopes and the port-relative braking cap. | `simulation/safety.py`, `simulation/runner.py` |
| P2 | Slow provider client setup ran on the event loop and could hold existing sessions. Session preparation now runs in a worker thread; a regression checks event-loop responsiveness. | `api/routes.py` |
| P2 | Disabling LLM planning still required a provider key and initialized its client. Static homing now runs without either. | `api/routes.py`, `simulation/runner.py` |
| P2 | Importing classical controllers eagerly imported optional Gymnasium dependencies. RL imports are deferred until selected. | `controllers/__init__.py` |
| P2 | Final states reverted to default spacecraft names, capture radii and motion limits. Summaries retain the configured metadata and explicitly use relative coordinates. | `simulation/runner.py` |
| P2 | Exports recorded a null model when the provider's default was used. They now record the resolved provider model. | `llm/reasoning_agent.py`, `simulation/runner.py` |
| P2 | RL baseline timestamps could read moving runner globals from a worker thread. They now use the captured request timestamp. | `simulation/runner.py` |
| P2 | The evaluation CLI defaulted to 10 km although requests allow at most 1 km. Its default now validates. | `rl/evaluate_policy.py` |
| P2 | Proof evaluation always selected the final normalizer for any checkpoint. Non-default checkpoints now require their matching `--normalize` file and fail before evaluation when absent. | `rl/proofs.py` |
| P2 | Minimum transit-speed planning used a hard-coded acceleration unrelated to configured thrust. It now uses the configured acceleration and thrust/mass. | `simulation/runner.py` |

The audit covered all 30 application Python modules, the frontend's five JS
modules and HTML/CSS, tests, notebook source bundle, training/evaluation and
verification entry points, configuration and container setup. Findings were
checked against actual execution; this does not assert that every possible bug
or physical scenario has been ruled out.

## Verification and evidence

- `reference-session.json`: original real run, including its disabled-advice request, discarded responses and cancellation.
- `vertex-session.json`: a new real Vertex/Gemini 3.8 Flash call at 100 m, with a non-null trained PPO proposal. Vertex explicitly rejected the short lookahead waypoint and capped learned speed at 0.10 m/s. The response arrived after 25 simulated seconds while physics continued; it was applied. The trace reaches approximately 91.7 m and was deliberately cancelled at 122.5 s. **This is an advisory-path check, not a completed Vertex docking trial.**
- `browser-validation.json`: real SSE runs with the trained policy, automatic and manual capture, Stop/restart, all four camera modes and overlays, distance validation, and 320/390/768/1440 px viewport checks. Both capture modes passed; no JavaScript errors or page overflow were recorded.
- `rl-browser-check.json`, `desktop.png`, `mobile.png`: default/reset behavior and display of the saved real Vertex decision through the dashboard's SSE handlers. The displayed trace is a replay; the underlying provider run is real.
- `verification.json`: regression, build, dependency, notebook and proof verification results. Historical training manifests remain unchanged.
- `source/`: reviewed application, regression and notebook sources; `manifest.json` supplies SHA-256 hashes for this evidence set.

The Impeccable static detector reported `flat-type-hierarchy`. Browser-computed
sizes were h1 43.2 px, h2 15 px and h3 12 px; its assumption that every heading
was 16 px is a verified false positive. The existing flight-operations design
was preserved.

## Remaining practical limits

The archived policy was trained/evaluated primarily on 5–80 m starts and older
motion envelopes. A successful 100 m advisory call does not establish policy
accuracy across every permitted 2 cm–1 km start, attitude, fault or slow-thrust
setting. Current actuator bounds and deterministic safety controls remain
independent of learned advice.

Physics uses a local linearized orbital model, prescribed primary motion,
simplified fuel and discrete integration. The ISS mesh and chaser concept
visualize docking-port states; body collision, contact mechanics and hardware
interfaces are outside scope. The safety channel's use of simulator truth is
not a flight-ready sensor estimator.

Sessions are process-local and unauthenticated, bounded to four active and
32 retained completed sessions. Use the local server as documented; durable
storage, authentication and multi-worker coordination need implementation for
a shared deployment. The Three.js chunk remains 536 kB minified; the build
passes with Vite's size advisory. An earlier provider SDK coroutine warning was
seen in the reference server log; it did not reproduce during this corrected
live call and was not patched inside third-party libraries.
