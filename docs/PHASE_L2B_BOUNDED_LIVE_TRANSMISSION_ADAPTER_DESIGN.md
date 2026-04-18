# Phase L2B — Bounded Live Transmission Adapter Design

## Status

Phase L2B defines the exact live adapter boundary for the first bounded real live transmission attempt.

This phase is docs-only.

It does not:
- enable live order transmission
- change runtime behavior
- change CLI behavior
- change tests
- widen strategy, risk, or accounting boundaries

## Purpose

L2A locked the first real live transmission envelope.

L2B freezes the exact adapter boundary and artifact contract that any future live transmission implementation must follow.

## Design goal

The first live transmission implementation must add one explicit adapter boundary only.

That boundary must:

- transmit at most one bounded live request at a time
- stay inside the L2A envelope
- remain deny-by-default
- produce operator-readable request/result/state artifacts
- fail closed on uncertainty
- avoid hidden fallback behavior

## First live transmission adapter boundary

The first live transmission phase must introduce one bounded adapter surface with three responsibilities only:

1. submit one approved live order request
2. fetch the resulting live order state
3. cancel the live order if required by the bounded failure path

No other responsibilities are allowed in the first live adapter phase.

## Required adapter contract

The future live adapter must accept only a fully materialized bounded live request.

That request must already have passed:

- authority enabled
- launch window active
- approval active
- readiness ready
- limited-live gate ready for review
- manual halt inactive
- reconciliation clean
- live control decision action go
- approved symbol match
- tiny notional within cap
- max open positions not exceeded

The adapter must not make these policy decisions itself.
The adapter only executes the already-authorized bounded request.

## Required request artifact

Before any real transmit call, the runtime must write one operator-readable live request artifact containing at minimum:

- runtime id
- session id
- request id
- client order id
- venue identifier
- symbol
- side
- order type
- quantity
- reference price
- estimated notional
- approval artifact reference
- authority artifact reference
- launch-window artifact reference
- transmission-decision artifact reference
- generated timestamp

The live request artifact must be written before transmission is attempted.

## Required result artifact

Immediately after transmit attempt, the runtime must write one live result artifact containing at minimum:

- runtime id
- session id
- request id
- client order id
- venue identifier
- attempt timestamp
- adapter action attempted
- accepted / rejected result
- venue order id if present
- reject reason if present
- raw adapter status summary suitable for operators

## Required state artifact

After the result artifact, the runtime must write one live order-state artifact containing at minimum:

- runtime id
- session id
- request id
- client order id
- venue order id if present
- current order state
- terminal status boolean
- filled quantity
- average fill price if known
- fee if known
- updated timestamp

## First live request shape

The first real transmitted order must remain constrained to:

- one symbol only
- one market order only
- one request only
- one open position maximum
- tiny notional only
- one venue only

No batching.
No parallel submission.
No limit-order logic in the first phase.
No retry loop that can widen exposure.

## Failure handling contract

The first live transmission implementation must fail closed.

Required failure behavior:

- adapter error => no silent retry
- unknown venue response => no silent retry
- missing venue order id => no silent retry
- unknown order state => no silent retry
- mismatch between request/result/state => halt
- duplicate request detection => halt
- unexpected rejection => halt
- any uncertainty about exposure => halt

## Cancel boundary

The first live transmission phase may include one bounded cancel path only if required by the adapter/state contract.

If included:

- cancel must be explicit
- cancel must write its own state update artifact
- cancel must not be automatic beyond the bounded documented failure path
- cancel must not broaden into generalized order management

## Explicitly out of scope

The first live adapter phase must not add:

- multiple venues
- multiple symbols
- batching
- autonomous retries
- autonomous recovery
- unattended operation
- overnight operation
- limit-order strategy expansion
- portfolio-level routing
- second accounting system
- hidden fallback execution paths

## Required future implementation files

A future implementation phase is expected to touch only bounded execution/runtime surfaces such as:

- live adapter boundary file
- runtime loop execution seam
- execution artifact models
- focused live transmission tests
- bounded operator docs

Any additional file touches must be justified by the bounded live adapter contract.

## Required future tests

A later implementation phase must prove:

- no transmit occurs when bounded prerequisites fail
- one bounded request artifact is written before transmit
- one bounded result artifact is written after transmit attempt
- one bounded state artifact is written after result handling
- shadow behavior remains unchanged
- sandbox behavior remains unchanged
- no retry widens exposure
- no second request is emitted implicitly
- halt occurs on ambiguous live execution state

## Exit criteria

Phase L2B is complete when:

- the live adapter boundary is frozen in writing
- required request/result/state artifacts are frozen in writing
- bounded failure behavior is explicit
- out-of-scope behavior is explicit
- no runtime or CLI behavior changed
- the repo remains in a clean validated state

## Closeout conclusion

L2B defines the exact adapter boundary for the first bounded real live transmission phase without implementing it.

Any future live transmission code must stay inside this contract unless explicitly respecified.
