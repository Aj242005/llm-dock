# Coordinated centimetre docking

A live Vertex AI (`gemini-3.8-flash`) session using the included seed-42 PPO
checkpoint as advice and LQR for continuous actuation. The initial port vector
is [80, 48, 36] m (100 m separation), with approximately 45.3 degrees of attitude
error. Configured speed is 2 m/s on all axes, total thrust 50 N, acceleration
0.1 m/s?, near-port speed 0.3 m/s, and capture range 0.02 m.

The final run docked at **1.945 cm**, **0.004 m/s** relative speed, in **133.6
simulated seconds**. Playback was explicitly 5?; wall time was 75.4 seconds.
There were two applied Vertex decisions, two actual PPO proposals, no provider
fallbacks, and 449 telemetry steps with simultaneous force and torque.
The simulation continued during provider planning. All four capture checks passed.

The dashboard defaults to real-time playback. This is one live research
simulation, not a provider success-rate estimate or demonstrated hardware
accuracy. The trained checkpoint's original evaluation used a 1.25 m gate;
those results do not establish centimetre precision. The notebook packages the
new 2 cm environment for fresh training and evaluation.

- `session.json`: full final configuration, source-labelled decisions and telemetry.
- `checks.json`: measured limits and terminal checks, produced by `scripts/verify_vertex.py`.
- `telemetry.csv` and `approach-curves.png`: actual separation, speed, attitude and thrust.
- `decisions.json` and `planner-prompt.txt`: provider decisions and the actual system prompt.
- `reference-initial.json`: the first live run, before clarifying primary/secondary
  speed limits and preserving the model's selected closing-speed ceiling.
- `dashboard/`: browser evidence for actual SSE, manual/automatic capture, active
  nozzles, responsive viewports, and stop/restart. Its short scenario starts at
  7.5 m with deliberate attitude error and uses accelerated deterministic planning.
- `verification.json`: local checks and their limits.
- `source/` and `manifest.json`: readable source snapshot and SHA-256 checksums.

The NASA PMA-2 front-plane vertex bounds locate its docking-face centre at
[0.004878, -0.673222, 21.005283] m in asset coordinates. That centre is translated
to [0,0,0] and rotated about Y before rendering. The former bounding-box centre
misplaced the face vertically by approximately 0.573 m. The corrected docking
collar and the X/Y/Z grid now share the physical port origin.

Run `python scripts/verify_proofs.py` to verify the evidence hashes. Hashes
verify file integrity; they do not independently certify simulator accuracy.
