# Intermediate live reference

This run verified the initial stand-off guidance and impulse-based fuel changes.
It docked at 1.992 cm with 0.004 m/s relative speed, consuming 10.849 kg of
propellant. Both completed planner calls used Vertex and had PPO advisory
proposals. The first response was 217.8 simulated seconds old and was rejected;
the next response was applied. Physics and local control continued throughout.

The first explanation still described translation during the initial tumble.
That prompted a more explicit position-hold instruction above 0.1 rad/s and
current-state plan checks. This trace therefore predates the final prompt and
is retained as an intermediate reference. The final implementation, exact source
snapshot, test results and newer live demonstration are in
`../aligned-propellant-vertex-final/`.

The session export, numerical checks, telemetry CSV and plot preserve this run's
measurements. It is one simulation, not hardware validation or a success-rate
measurement.
