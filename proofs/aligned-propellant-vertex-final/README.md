# Stable alignment and propellant verification

The reported scenario began 100 m from the ISS docking port, with roll/pitch/yaw
15/40/35 degrees and relative angular rates `[1, 3, 0]` rad/s. This live run used
Vertex `gemini-3.8-flash`, a trained PPO advisory proposal, and LQR tracking.

The final controller damps rotation above 0.1 rad/s while holding position. It
then aligns attitude while transferring in XYZ toward a 5 m stand-off on the
primary port axis. Final axial closure requires one second of stable alignment
and entry into a 5 cm lateral corridor. Manual and automatic capture also check
range, speed, alignment, relative rotation, stability, and corridor entry.

| Measurement | Result |
| --- | --- |
| Final port separation | 0.019211 m / 1.921 cm |
| Final relative speed | 0.004 m/s |
| Simulation time | 374.6 s |
| Playback | 5x; approximately 100.84 s measured wall time |
| Maximum speed | 1.92 m/s |
| Maximum thrust | 49.106 N, configured maximum 50 N |
| Propellant consumed | 10.712557 kg |
| Propellant remaining | 14.287443 kg of the initial 25 kg |
| Final mass | 489.287443 kg |
| Live Vertex decisions | 4; all applied and supplied PPO advice |
| Detumbling control steps | 599 |
| Simultaneous force and torque steps | 965 |
| Minimum range before stable alignment | 100 m |
| Final capture checks | All six passed |
| Automated tests | 139 passed, zero failures/errors |

The first Vertex decision explicitly requested a position hold because the
measured 3.162 rad/s spin exceeded the detumbling threshold. Physics continued
while Vertex planned. The run reached stable alignment before final closure.
The fuel calculation includes rotational thrusters; the substantial detumbling
cost explains why remaining fuel no longer appears almost unchanged.

Fuel follows equivalent engine thrust divided by `Isp * g0`, plus summed
torque-axis demand divided by the RCS lever arm and RCS `Isp * g0`. This run used
220 s engine Isp, 60 s RCS Isp, and a 0.75 m lever arm. Coasting costs no
propellant. Mass and assumed fixed-geometry inertia decrease with consumption.
These are editable simulator assumptions, not calibrated ISS/chaser engines.

`session.json` contains the request, complete event history and summary.
`telemetry.csv` and `approach-and-fuel.png` show the motion and fuel trajectory.
`checks.json` records numerical checks. `tests.xml` records the complete test
suite. `planner-prompt.txt` and `source/` preserve the final implementation.
`dashboard/` includes browser evidence for six capture checks, manual capture,
stop/restart, nine active jets, responsive layouts, and zero JavaScript errors.
The focused capture screenshot verifies that both spacecraft remain visible.

The prior run in `../aligned-propellant-vertex/` is an intermediate reference
that motivated the explicit detumbling prompt. Its first delayed Vertex
response was rejected. It is not a trace of the final prompt.

These are individual simulated demonstrations. They do not establish statistical
mission reliability, flight certification, hardware accuracy, or validation of
the archived PPO policy against this changed fuel model. Existing Kaggle results
retain their original source and capture limits. The notebook packages the new
source for fresh training and held-out evaluation; no new training is claimed.

Run `python scripts/verify_proofs.py` to verify artifact hashes. To repeat the
live scenario, start the backend with Vertex credentials and matched PPO
artifacts, then run `python scripts/verify_vertex.py --out-dir proofs/new-run`.
