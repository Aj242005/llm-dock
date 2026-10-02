# Tumble-limit validation

The reported dashboard state uses angular rates [3,6,0] rad/s. Its combined
relative rate is sqrt(45) = 6.708 rad/s, exceeding the default 5 rad/s tumble
guard. The former runner accepted this request and immediately terminated as
`diverged` before returning a planner decision, without a specific explanation.

Requests now reject that starting state with HTTP 422 and the measured rate,
limit and units. The dashboard validates the same relative-rate vector before
launch, exposes the limit, and explains radians per second beside the inputs.
Runtime divergence reports its specific range, rotation or non-finite condition.
Failure events replace stale planning text in the right panel.

132 offline tests passed, lint/format and the production build passed. Browser
checks at 1440px and 390px verified invalid-rate rejection, acceptance after
resetting rates to zero, responsive layout and termination messages with no
JavaScript errors. The terminal browser event is injected deterministically;
the request rejection was also verified against the actual running API.
The notebook's 32 packaged files are synchronized. Existing proof bundles
remain unchanged and retain their original source snapshots and parameters.
