# Phase L1G — Launch Window Foundation

## Status

Phase L1G upgrades the limited-live launch-window artifact from a static placeholder to runtime-controlled state.

## What changed

- added runtime materialization for launch-window state
- launch-window artifact now reflects:
  - not configured
  - scheduled
  - active
  - expired
- added focused tests proving the runtime can materialize an active window and that transmission still stays denied when the window is not active

## Boundary confirmation

L1G does not add:

- live order transmission
- live execution authority
- approval granting workflows
- runtime CLI launch-window controls
- symbol/notional live transmission logic
- autonomous behavior
- strategy or risk rewrites

## Closeout conclusion

L1G establishes runtime-controlled launch-window state while keeping limited-live transmission denied by default.
