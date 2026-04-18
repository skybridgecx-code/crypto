# Phase L2A — Bounded Live Transmission Scope Lock

## Status

Phase L2A defines the smallest acceptable first real live transmission envelope for this repository.

This phase is docs-only.

It does not:
- enable live order transmission
- change runtime behavior
- change CLI behavior
- change tests
- widen strategy, risk, or accounting boundaries

## Purpose

The L1 track closed the limited-live preparation stack:

- authority state
- launch-window state
- approval state
- transmission boundary
- positive-path test coverage
- operator dry-run checklist

The repository still does not implement executable live transmission.

Before any real live transmission code is added, the exact first live transmission envelope must be frozen in writing.

## Scope lock

The first live transmission phase must remain narrower than the current bounded preparation track.

Locked envelope:

- one runtime only
- one venue path only
- one approved symbol only
- one order request at a time
- one open position maximum
- tiny per-order notional only
- tiny per-symbol notional cap only
- one short launch window only
- full manual supervision only
- explicit per-request approval only
- immediate halt on first unexpected condition

## First live transmission constraints

### Venue and symbol

- one venue path only
- one approved symbol only
- recommended first symbol: `BTCUSDT`
- any request outside the approved symbol must hard-fail
- no multi-venue routing
- no venue failover behavior

### Order shape

- market order only for first live attempt
- no batching
- no parallel requests
- one request at a time
- no pyramiding
- no averaging down
- no portfolio-style allocation logic

### Size limits

- `max_open_positions = 1`
- tiny per-order notional only
- tiny per-symbol notional only
- no automatic size clipping
- oversize requests must be denied, not modified

### Approval and supervision

- every live request requires explicit manual approval
- approval must be per request
- operator must remain present for the full launch window
- second reviewer must confirm go/no-go before launch window start
- no unattended operation
- no overnight operation
- no same-window retry unless explicitly re-approved

## Required preconditions before any transmission attempt

All of the following must remain required at the live transmission boundary:

- limited-live authority enabled
- launch window active
- active approval present
- readiness `ready`
- limited-live gate status `ready_for_review`
- manual halt inactive
- reconciliation `clean`
- latest live control decision action `go`
- approved symbol match
- tiny notional within cap
- max open positions not exceeded
- feed health healthy
- venue constraints present and trusted
- required upstream review artifacts present and passing

If any single precondition fails, live transmission must be denied.

## Explicitly out of scope

Do not add any of the following in the first live transmission phase:

- multiple symbols
- multiple venues
- unattended trading
- overnight trading
- automatic approval bands
- autonomous retry or resume behavior
- strategy redesign
- risk model redesign
- second accounting system
- trust widening beyond current reconciliation posture
- hidden fallback execution paths

## Required next implementation design topics

A future implementation phase must explicitly define:

- exact live adapter boundary
- exact live request artifact set
- exact live result/state artifact set
- exact approval-consumption behavior
- exact failure and rollback behavior
- exact deny reasons at the transmission seam
- exact operator stop procedure on first live anomaly
- exact tiny first-order notional value
- exact first venue identifier and execution path

## Exit criteria

Phase L2A is complete when:

- the first real live transmission envelope is frozen in writing
- the envelope is narrower than a general live trading system
- no runtime or CLI behavior changed
- the repo remains in a clean validated state

## Closeout conclusion

L2A locks the smallest acceptable first real live transmission scope without implementing it.

Any future live transmission code must stay inside this bounded envelope unless explicitly respecified.
