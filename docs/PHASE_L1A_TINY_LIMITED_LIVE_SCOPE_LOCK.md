# Phase L1A — Tiny Limited-Live Scope Lock

## Status

Phase L1A locks the smallest acceptable first live-authority envelope for this repository.

This phase is docs-only.

It does not:
- enable live order transmission
- change runtime behavior
- change CLI behavior
- change tests
- widen trusted state
- widen strategy, risk, or accounting boundaries

## Why this phase exists

The repo is frozen through H2C with:

- validated paper paths
- frozen live-review workflow
- artifact-only launch verdicts
- bounded sandbox rehearsal
- no production live execution authority

If the repo is going to be used to pursue real money, the next correct move is not direct implementation.

The next correct move is to freeze the exact first live-authority envelope before any code path is widened.

## Scope of the first limited-live envelope

The first limited-live envelope must be narrower than the current review workflow suggests, not broader.

Locked scope:

- one runtime only
- one venue path only
- one approved symbol only
- one open position maximum
- tiny notional only
- full manual supervision only
- one short launch window only
- no unattended operation
- no overnight operation
- immediate halt on first unexpected condition

## Locked first-launch parameters

These values define the intended first real-money envelope for the next design phase.

### Runtime and venue

- runtime count: `1`
- venue count: `1`
- venue must be explicitly named in the future implementation phase
- no multi-venue routing
- no venue failover logic

### Symbol scope

- approved symbol count: `1`
- initial recommended symbol: `BTCUSDT`
- no symbol expansion in the first live phase
- any request outside the approved symbol must hard-fail

### Position and notional scope

- `max_open_positions = 1`
- per-order notional must remain tiny
- per-symbol notional cap must remain tiny
- no pyramiding
- no averaging down
- no multi-position portfolio behavior

### Approval scope

- every live order must require manual approval
- there is no auto-approved notional band in the first live phase
- operator approval must be explicit per request
- missing approval must hard-block transmission

### Session scope

- one bounded launch window only
- operator present for the full session
- second reviewer required before the session begins
- no background execution
- no cron-style scheduling
- no unattended retries

## Required deny-by-default posture

The first live-authority implementation phase must remain deny-by-default.

Required posture:

- live authority disabled unless explicitly enabled
- symbol deny by default
- venue deny by default
- order transmission deny by default
- approval deny by default
- launch window deny by default
- halt on any missing prerequisite artifact
- halt on any stale or degraded live input
- halt on reconciliation mismatch
- halt on unknown execution status
- halt on size breach
- halt on duplicate or unexplained request behavior

## Non-negotiable operator controls

The first live-authority phase must include all of the following:

- manual halt
- manual readiness downgrade
- explicit per-order approval
- full artifact preservation
- reconciliation visibility
- operator-readable request/result/status trail
- clear no-go state when prerequisites are missing

## Explicitly disallowed in the first live phase

Do not add any of the following in the first live-authority implementation phase:

- unattended trading
- overnight trading
- multiple symbols
- multiple venues
- automatic approval bands
- autonomous recovery logic that resumes live transmission without operator action
- strategy redesign
- risk model redesign
- second accounting system
- trust widening beyond paper-derived reconciliation
- hidden fallback execution paths
- silent retries that can widen exposure

## Required prerequisites before implementation

Before any live-authority code is added, the next design phase must define:

- exact live authority toggle location
- exact venue adapter boundary
- exact approval artifact and approval state model
- exact halt behavior
- exact reconciliation block conditions
- exact launch window controls
- exact request-size enforcement rules
- exact symbol allowlist enforcement rules
- exact test plan for deny-by-default coverage

## Relationship to existing frozen workflow

This scope lock does not replace the frozen live-review workflow.

The frozen workflow remains:

1. preflight
2. canary
3. bounded shadow evidence
4. gate review
5. launch verdict review

L1A only defines the maximum allowed first live-authority envelope for a future bounded implementation track.

## Exit criteria

Phase L1A is complete when:

- the first limited-live envelope is frozen in writing
- the envelope is smaller than the current review workflow, not larger
- no runtime or CLI behavior changed
- no execution authority changed
- the repo remains in a clean validated state

## Closeout conclusion

L1A locks a tiny first live-authority envelope without enabling it.

Any future live-authority phase must implement only this bounded envelope unless explicitly respecified in a later scope-lock phase.
