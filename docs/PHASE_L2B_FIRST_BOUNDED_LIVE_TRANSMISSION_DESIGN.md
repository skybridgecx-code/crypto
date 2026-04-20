# Phase L2B — First Bounded Live Transmission Design

## Purpose

This phase defines the exact future implementation shape for the first bounded real live transmission path.

L2B is design-only.

It does not add executable live trading behavior.

## Relationship to L2A

L2A locked:
- the smallest acceptable first real live transmission envelope
- deny-by-default requirements
- authoritative controls and artifacts
- explicit out-of-scope items

L2B translates that locked envelope into an implementation-ready design without widening authority.

## Design goal

The first live transmission implementation must remain:
- deny-by-default
- single-runtime scoped
- single-symbol scoped
- tiny-notional scoped
- operator-mediated
- artifact-first
- fail-closed on every missing prerequisite

## Proposed future entrypoint

The future implementation must use one explicit bounded live transmission entrypoint only.

Requirements:
- no second live path
- no hidden fallback path
- no bypass around the existing limited-live execution seam
- no alternate transmission path through shadow or sandbox flows

## Proposed future authority chain

A future live transmission attempt must be allowed only when all of the following are true:

1. limited-live authority is explicitly enabled
2. launch window is active
3. readiness is `ready`
4. limited-live gate status is `ready_for_review`
5. manual halt is inactive
6. reconciliation status is `clean`
7. latest live control decision action is `go`
8. runtime is the explicitly approved runtime
9. symbol matches the one approved symbol
10. request size is within the tiny approved cap
11. max-open-position constraint is satisfied
12. explicit per-request manual approval is present and unexpired
13. all required upstream review artifacts are present and authoritative

If any condition is false, transmission must be denied.

## Proposed future request flow

The first bounded future transmission flow should be:

1. load runtime-scoped authority state
2. load launch-window state
3. load approval state for the exact request
4. verify symbol and notional constraints
5. verify reconciliation and control-state prerequisites
6. evaluate transmission allow/deny decision
7. if denied, write operator-readable deny artifact and stop
8. if allowed, invoke the single bounded venue transmission seam
9. write post-attempt result artifact
10. preserve the full evidence chain for operator review

## Proposed required artifacts

A future implementation should emit, at minimum:

- runtime live-authority state artifact
- launch-window state artifact
- per-request approval artifact
- per-request transmission decision artifact
- per-request transmission result artifact
- halt event artifact when triggered
- operator-readable deny reason fields when blocked

These artifacts must remain in the runtime evidence directory and stay operator-readable.

## Proposed deny conditions

A future implementation must explicitly deny on:
- authority disabled
- inactive or expired launch window
- readiness not ready
- limited-live gate not ready for review
- manual halt active
- reconciliation not clean
- missing or stale approval
- symbol mismatch
- notional breach
- max-open-position breach
- stale, degraded, or unavailable feed state
- missing prerequisite artifact
- unknown execution state
- duplicate or conflicting request evidence

## Proposed post-attempt requirements

After any live transmission attempt, future implementation must:
- preserve the request and decision trail
- persist the venue response or bounded failure outcome
- avoid silent retries
- avoid hidden recovery behavior
- require operator review before any subsequent attempt

## Explicit design constraints

L2B does not permit:
- executable live transmission in this phase
- autonomous retry logic
- unattended operation
- multi-symbol expansion
- multi-venue expansion
- UI launch control surfaces
- new queues, workers, schedulers, or services
- strategy or risk rewrites
- a second accounting truth

## Validation expectations for a future implementation phase

Any future implementation phase must include:
- deny-by-default tests
- positive-path bounded transmission eligibility tests
- symbol and notional guard tests
- approval-expiry tests
- launch-window guard tests
- manual-halt tests
- reconciliation-block tests
- post-attempt artifact tests
- proof that shadow and sandbox paths remain unchanged

## Exit criteria

L2B is complete when:
- the future bounded live transmission path is explicitly designed
- authority checks are enumerated
- artifact requirements are enumerated
- deny conditions are enumerated
- no code or live authority is added

## Result

L2B defines the exact future implementation shape for the first bounded live transmission path while keeping live transmission out of scope in this phase.
