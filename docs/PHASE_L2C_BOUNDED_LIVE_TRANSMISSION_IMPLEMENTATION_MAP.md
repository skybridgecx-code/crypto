# Phase L2C — Bounded Live Transmission Implementation Map

## Status

Phase L2C maps the exact code touchpoints for the first bounded live transmission implementation.

This phase is docs-only.

It does not:
- enable live order transmission
- change runtime behavior
- change CLI behavior
- change tests
- widen strategy, risk, or accounting boundaries

## Purpose

L2A locked the first live transmission envelope.
L2B locked the live adapter boundary and artifact contract.

L2C freezes the minimum implementation surface for the first code phase so the repo can add bounded live transmission without speculative rewrites.

## Implementation objective

The first live transmission code phase must do one thing only:

- execute one bounded live request through one explicit adapter boundary after the full bounded prerequisite set has already authorized transmission

It must not redesign the runtime.

## Exact implementation areas

### 1. Runtime execution seam

Primary touchpoint:

- `src/crypto_agent/runtime/loop.py`

Responsibilities for a future implementation phase:

- refresh the bounded transmission decision at the execution seam
- write the live request artifact before any transmit attempt
- call the bounded live adapter only when transmission is authorized
- write the live result artifact immediately after the transmit attempt
- write the live state artifact immediately after result/state handling
- fail closed on ambiguity

### 2. Live adapter boundary

Primary touchpoint:

- `src/crypto_agent/execution/live_adapter.py`

Responsibilities:

- submit one bounded live order
- fetch live order state
- cancel one live order only if the bounded failure path requires it
- expose no hidden fallback path
- avoid policy decisions already handled upstream

### 3. Execution artifact models

Primary touchpoint:

- `src/crypto_agent/execution/models.py`

Responsibilities:

- add bounded live request/result/state artifacts if missing
- keep artifact schema operator-readable
- preserve clear separation from shadow and sandbox artifacts

### 4. Request artifact builder

Primary touchpoint:

- `src/crypto_agent/execution/shadow.py`

Responsibilities:

- either extend the existing request-builder pattern carefully or add a clearly separated bounded live builder
- avoid widening shadow/sandbox semantics
- keep one-request-at-a-time behavior explicit

### 5. Transmission boundary evaluation support

Primary touchpoints:

- `src/crypto_agent/policy/live_controls.py`
- `src/crypto_agent/runtime/models.py`

Responsibilities:

- preserve the bounded authorization decision as the only prerequisite input to the adapter call
- keep authority/window/approval/control/reconciliation conditions explicit and operator-readable

## Required artifact write order

A future implementation phase must preserve this order:

1. bounded live request artifact
2. bounded live result artifact
3. bounded live order-state artifact

No transmit call is allowed before the request artifact exists.

## Required future tests

A later implementation phase must prove:

- no transmit occurs when any bounded prerequisite fails
- exactly one bounded live request artifact is written before transmit
- exactly one bounded live result artifact is written after transmit attempt
- exactly one bounded live state artifact is written after result handling
- shadow behavior remains unchanged
- sandbox behavior remains unchanged
- no retry widens exposure
- no second request is emitted implicitly
- halt occurs on ambiguous live execution state

## Out of scope files unless strictly required

Avoid speculative edits to:

- strategy logic
- signal generation
- replay-only paths
- matrix/replay surfaces
- sandbox rehearsal behavior
- shadow-only evidence behavior
- accounting or reconciliation logic beyond bounded enforcement already frozen

## Expected future code-phase order

1. add bounded live request/result/state artifact models
2. add bounded live request artifact write step
3. add one explicit live adapter call at the runtime seam
4. add bounded live result/state artifact write steps
5. add focused negative-path and one bounded positive-path test
6. validate that shadow and sandbox behavior remain unchanged

## Exit criteria

Phase L2C is complete when:

- exact files and responsibility boundaries are frozen in writing
- required artifact write points are frozen in writing
- required tests are named
- out-of-scope areas are explicit
- no runtime or CLI behavior changed

## Closeout conclusion

L2C defines the minimum implementation surface for the first bounded live transmission code phase.

Any future live transmission code must stay inside this map unless explicitly respecified.
