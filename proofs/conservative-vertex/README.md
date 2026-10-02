# Conservative docking and live Vertex checks

`session.json` is a complete live Vertex AI + PPO advisory demonstration,
starting 100 m apart. All eight decisions came from `gemini-3.8-flash` and
received a learned proposal. No deterministic fallback was needed. The run
used 1000× playback and replanned every 500 half-second steps; those settings
differ from the dashboard's 1× / 60-step defaults. This is one demonstration,
not a statistical success rate or flight qualification.

`checks.json` records the measured maximum speed (0.100000001 m/s), total thrust
(2.5 N), local acceleration (0.004996 m/s²), and successful final port separation
(0.9885 m). Every near-port sample was at most 0.02 m/s. Simulated time was
1802.5 seconds and wall time approximately 433 seconds, including planning waits.

`source/` preserves the source used for that completed run. After this run,
the final approach was tightened to aim directly at the measured port vector
and retain a 5% margin under the capture speed tolerance. That later change
is tested separately; it is not retroactively attributed to the live run.

`real-time-session.json` and `real-time-check.json` record a separate browser
session using Vertex and 1× playback without learned advice. The craft moved
0.04 m over the observed interval; the clock advanced 3.5 simulation seconds,
and Stop completed. `vertex-real-time.png` shows the model's natural-language
explanation and actual telemetry. Explanations describe chosen actions,
measurements and alternatives; private deliberation is not exposed.

Training evidence remains in the Kaggle run directories. This folder contains
no API credentials. SHA-256 hashes verify file integrity, not independent endorsement.

`hybrid-current-100m.json` is a separate successful 100 m run using the current
final-approach controls, the deterministic planner, and PPO advice. Its source
is in `current-source/`. It used 200× playback and the dashboard's 60-step cadence;
the export records all parameters. Responsive captures and the completed capture
screen are included. The automated browser script encountered timing limits on
this machine; those timeouts are not reported as passes. Backend capture, live
Vertex connectivity, planning/reset, 1× pacing and Stop were verified separately.
After fixing the immediate-Stop session URL race, a focused browser check passed
both manual capture and starting/stopping the next session. See
`browser-interactions.json`; this used an explicit 7.5 m interaction scenario.
