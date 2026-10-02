# Physics during Vertex planning

This bundle records one actual Vertex call with trained PPO advice at **1×**
playback, starting 100 m apart. The primary starts at +0.01 m/s along X and the
secondary at −0.05 m/s. The request uses the server's configured default model;
it does not explicitly name a model or record provider model-version metadata.

Before the first decision returned, 90 telemetry events advanced simulation
time from 0.5 s to 45.0 s. Separation changed from 99.9701 m to 97.6774 m; the
primary position changed from 0.005 m to 0.45 m. The response was applied with
45.0 s snapshot age, inside this experiment's 255 s age budget. The session was
then stopped deliberately. This experiment verifies continued motion and a
real provider response; it is not a docking success-rate measurement.

- `vertex-session.json`: actual request, ordered SSE events, and terminal summary.
- `verification.json` and `checks.json`: measured values, commands, and scope.
- `screenshots/`: actual live/applied and stopped mobile states. The screenshots
  were taken after reconnecting to the same session; they do not depict a pending
  response. The pending-response evidence is in the timestamped telemetry log.
- `source/`: source used for these checks and meaningful delayed-provider tests.
- `verify-live.py`: browser verification harness. The first attempt timed out
  before creating a session; the next attempt created this session but failed to
  resolve a relative export URL. Reconnecting used a local mocked creation
  response pointing at the existing session, avoiding another paid call.
- `finish-review.json`: independent Impeccable review of the changed UI behavior.
- `manifest.json`: hashes of all files in this folder.

The automated tests cover both spacecraft moving before a response, continuing
the last accepted maneuver, one outstanding provider request, expired-response
rejection, current near-port limits, immediate abort braking, and cancellation
at Stop or the time budget. All 114 backend tests passed, with lint and frontend
build checks. Physics uses the existing simplified local-frame model.

For accelerated experiments, provider delay also advances accelerated simulated
time. Excessively fast playback can expire responses before application. The
full provider-docking script now uses 5× and writes to a new evidence folder,
preserving earlier recorded proofs.

Verify this bundle with `python scripts/verify_proofs.py` from the project root.
