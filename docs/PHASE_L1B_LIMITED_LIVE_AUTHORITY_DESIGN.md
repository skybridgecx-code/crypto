# Phase L1B — Limited-Live Authority Design

## Status

Phase L1B defines the bounded control surface required before any live-order transmission code is added.

This phase is docs-only.

It does not:
- enable live order transmission
- change runtime behavior
- change CLI behavior
- change tests
- widen trusted state
- widen strategy, risk, or accounting boundaries

## Purpose

L1A locked the first live-authority envelope.

L1B freezes the exact authority model that any future implementation must follow so live transmission remains:

- deny-by-default
- explicitly bounded
- manually supervised
- fully auditable
- easy to halt
- impossible to silently widen

## Design goals

Any future limited-live implementation must satisfy all of the following:

- no live transmission unless explicitly enabled
- no order transmission without explicit per-order approval
- no transmission outside the active launch window
- no transmission outside the single allowed symbol
- no transmission above the tiny configured notional cap
- no transmission when readiness is downgraded
- no transmission when manual halt is active
- no transmission when reconciliation is not clean
- no transmission on stale, degraded, or unavailable live input
- no hidden fallback path that can bypass the control surface

## Authority model

Future live authority must require all of the following to be true at the same time:

1. live authority explicitly enabled for the runtime
2. launch window currently active
3. operator readiness set to `ready`
4. limited-live gate status set to `ready_for_review`
5. manual halt inactive
6. reconciliation status clean
7. live control status in explicit go state
8. symbol on the single approved allowlist
9. request size within the tiny allowed cap
10. explicit per-order approval granted
11. all required upstream review artifacts present and passing

If any one of these conditions is false, transmission must be denied.

## Single enable point

Future implementation must have one explicit enable point for live order authority.

Requirements:

- one runtime-scoped live-authority toggle only
- default value disabled
- persisted in an operator-readable artifact
- changing the toggle must be auditable
- no implicit enablement from other flags
- no inferred enablement from launch verdicts, readiness, or gate status alone

Live-review artifacts may inform operator decisions but may not independently grant live order authority.

## Manual approval model

The first live phase must require approval for every order.

Required approval behavior:

- each candidate live request must create an operator-reviewable approval record
- approval must be explicit per request
- approval must be tied to:
  - runtime id
  - session id
  - request id
  - symbol
  - side
  - estimated notional
  - approval timestamp
  - approving operator identity field
- approval must expire outside the active launch window
- approval must not survive request mutation
- approval must not auto-carry to later requests
- missing approval must hard-block transmission

## Halt model

Future live implementation must support immediate operator halt.

Required halt behavior:

- manual halt must block all new live transmission immediately
- readiness downgrade to `not_ready` must block all new live transmission immediately
- halt state must be persisted and auditable
- live transmission must not auto-resume after halt
- resume must require explicit operator action
- halting must preserve all evidence artifacts

## Launch-window model

Live authority must be valid only inside one bounded launch window.

Requirements:

- one explicit start boundary
- one explicit end boundary
- no live transmission outside the window
- expired window must block transmission even if approval exists
- a new window must require new operator action
- same-day retry after halt is blocked by default unless explicitly re-approved by operators

## Symbol and notional enforcement model

The first live phase must enforce one symbol and tiny size only.

Requirements:

- one approved symbol only
- request symbol mismatch must hard-fail before transmission
- one tiny per-order notional cap
- one tiny per-symbol cap
- max open positions remains `1`
- exceeding any cap must block transmission and emit clear control evidence
- there is no automatic size clipping in the first live phase
- oversize requests must be denied, not silently modified

## Reconciliation and state trust model

The first live phase must not widen trust beyond the current paper-derived reconciliation posture.

Requirements:

- transmission blocked unless reconciliation status is `clean`
- transmission blocked on mismatch detection
- transmission blocked on unknown position state
- transmission blocked on unknown balance state
- transmission blocked if required runtime artifacts are missing
- no second accounting system
- no independent live-state trust path that bypasses reconciliation

## Feed and venue health model

The first live phase must block transmission on data-quality uncertainty.

Requirements:

- stale feed blocks transmission
- degraded feed blocks transmission
- unavailable feed blocks transmission
- unknown venue constraints block transmission
- unknown execution status blocks transmission
- repeated unexplained rejection behavior blocks transmission
- duplicate or conflicting request evidence blocks transmission

## Required artifacts

Any future live-authority implementation must add explicit artifacts for authority and approval decisions.

Minimum required artifacts:

- runtime live-authority state artifact
- per-request approval artifact
- per-request transmission decision artifact
- deny reason artifact or deny fields in the decision artifact
- halt event artifact
- launch-window state artifact

These artifacts must be operator-readable and written into the normal runtime evidence directory.

## Required deny reasons

At minimum, the future implementation must emit clear deny reasons for:

- live authority disabled
- outside launch window
- readiness not ready
- limited-live gate not ready for review
- manual halt active
- reconciliation not clean
- missing manual approval
- symbol not allowed
- request exceeds notional cap
- max open positions reached
- stale feed
- degraded feed
- unavailable feed
- missing prerequisite artifact
- unknown execution state
- duplicate or conflicting request evidence

## Explicit non-authority surfaces

The following surfaces must remain non-authoritative:

- `live_gate_decision.json`
- `live_launch_verdict.json`
- shadow evidence artifacts
- sandbox evidence artifacts

These surfaces may support human review but may not independently authorize live transmission.

## Required tests for future implementation

A later implementation phase must include tests that prove:

- live transmission is disabled by default
- every missing prerequisite blocks transmission
- every deny reason is surfaced clearly
- symbol mismatch blocks transmission
- oversize notional blocks transmission
- manual halt blocks transmission
- readiness downgrade blocks transmission
- launch-window expiry blocks transmission
- missing approval blocks transmission
- stale/degraded/unavailable feed blocks transmission
- reconciliation mismatch blocks transmission
- no artifact-only surface can accidentally grant authority

## Implementation boundaries

The first implementation phase must not add:

- unattended operation
- overnight operation
- multiple symbols
- multiple venues
- automatic approval bands
- hidden retries that widen exposure
- strategy redesign
- risk model redesign
- second accounting system
- broader trust in live balances or positions than current reconciliation allows

## Exit criteria

Phase L1B is complete when:

- the live-authority control surface is frozen in writing
- deny-by-default posture is explicit
- per-order approval requirements are explicit
- halt and launch-window behavior are explicit
- artifact and test expectations are explicit
- no runtime or CLI behavior changed

## Closeout conclusion

L1B defines the exact limited-live authority model required before any implementation work.

Any future live-authority code must implement this bounded design and no more.
