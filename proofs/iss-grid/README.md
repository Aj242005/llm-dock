# ISS and XYZ grid verification

These are local browser and backend checks for the new presentation and placement
controls. The original Kaggle training evidence remains in its existing folders.

- `screenshots/`: actual desktop/mobile views, four camera views, a pointer-rotated
  grid, and a 1 cm grid at the target port.
- `verification.json`: recorded browser checks for rotation, spacing, visibility,
  exact distance boundaries, random placement, model loading, and overflow.
- `dashboard-verification.json`: live automatic docking, manual capture,
  stop/restart, exports, and responsive controls. The short capture scenario starts
  at 7.5 m, uses the trained PPO advisor and deterministic planner, and uses 200×
  playback to finish verification quickly. It is not a live Vertex benchmark.
- `hybrid-session.json`: complete actual request, 749 streamed events, and a
  docked result at 355.5 simulated seconds (711 steps). Recorded physical thrust
  reached 2.5 N; final relative speed was approximately 0.019 m/s.
- `checks.json`: test commands and results; 109 backend tests passed.
- `source/`: the source used for these checks and NASA asset provenance. The
  model itself is served from `frontend/public/models/iss.glb`; its SHA-256 is in
  the source metadata rather than duplicating the 5.6 MB asset here.
- `finish-review.json`: independent Impeccable review and fix verdict.
- `manifest.json`: SHA-256 of every file in this evidence folder.

Starting port separation may be 0.02–1000 m. This new configuration envelope
does not prove trained-policy reliability across that entire range. The visuals
retain metre scale, but the ISS mesh is not a hull-collision or contact model.

To verify hashes, run `python scripts/verify_proofs.py` from the project root.
NASA asset source: https://science.nasa.gov/resource/international-space-station-3d-model/
