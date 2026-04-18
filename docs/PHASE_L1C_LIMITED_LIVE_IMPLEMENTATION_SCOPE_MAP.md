# Phase L1C — Limited-Live Implementation Scope Map

## Status

Phase L1C maps the exact code touchpoints for the first bounded live-authority implementation.

This phase is docs-only.

It does not:
- enable live order transmission
- change runtime behavior
- change CLI behavior
- change tests
- widen trusted state
- widen strategy, risk, or accounting boundaries

## Purpose

L1A locked the tiny first live-authority envelope.
L1B locked the limited-live authority design.

L1C identifies the minimum implementation surface required for a future code phase so the repo can add bounded live authority without speculative rewrites.

## Implementation objective

The first live-authority code phase must do one thing only:

- allow tiny, manually approved, deny-by-default live transmission inside the frozen L1A/L1B envelope

It must not redesign the runtime.

## Exact implementation areas

### 1. Forward runtime entry and gating

Primary touchpoints:

- `src/crypto_agent/cli/forward_paper.py`
- `src/crypto_agent/runtime/loop.py`

Expected responsibilities in a future implementation phase:

- accept explicit live-authority configuration inputs
- persist live-authority runtime state
- reject live transmission unless the full bounded prerequisite set passes
- keep all non-live modes unchanged unless explicitly needed for shared control evaluation

### 2. Control and policy evaluation surfaces

Primary touchpoints:

- `src/crypto_agent/policy/live_controls.py`
- `src/crypto_agent/policy/readiness.py`
- `src/crypto_agent/policy/live_gate.py`

Expected responsibilities:

- evaluate deny-by-default live transmission conditions
- surface clear no-go reasons
- preserve existing artifact-only review posture for gate and readiness surfaces
- avoid allowing gate/readiness artifacts to independently grant authority

### 3. Runtime state and artifact models

Primary touchpoints:

- `src/crypto_agent/runtime/models.py`
- existing runtime artifact writers/readers inside `src/crypto_agent/runtime/loop.py`

Expected responsibilities:

- add typed models for:
  - runtime live-authority state
  - launch-window state
  - per-request live approval
  - per-request live transmission decision
  - halt event or halt-state artifact extension
- keep artifacts operator-readable and written under the normal runtime directory

### 4. Execution adapter boundary

Primary touchpoints:

- `src/crypto_agent/execution/live_adapter.py`
- any execution-routing boundary currently used by forward runtime
- `src/crypto_agent/execution/models.py`

Expected responsibilities:

- isolate real transmission behind one explicit boundary
- deny transmission unless approval and all runtime controls pass
- keep shadow and sandbox behavior unchanged
- avoid hidden fallback routing

### 5. Reconciliation and state-trust blocking

Primary touchpoints:

- `src/crypto_agent/runtime/reconciliation.py`
- reconciliation checks invoked from `src/crypto_agent/runtime/loop.py`

Expected responsibilities:

- block live transmission when reconciliation is not clean
- block on mismatch detection
- block on missing required runtime evidence
- preserve current paper-derived trust posture

### 6. Market-input and venue-health blocking

Primary touchpoints:

- `src/crypto_agent/market_data/live_adapter.py`
- live feed health/state handling in `src/crypto_agent/runtime/loop.py`
- `src/crypto_agent/market_data/venue_constraints.py`

Expected responsibilities:

- block live transmission on stale, degraded, or unavailable feed
- block on missing or unknown venue constraints
- block on unknown execution status conditions

## Required new artifacts

Future implementation must add explicit artifacts for:

- `live_authority_state.json`
- `live_launch_window.json`
- per-request live approval artifact
- per-request live transmission decision artifact
- explicit deny-reason evidence
- explicit halt event or halt-state evidence

These names can be adjusted in implementation, but the artifact set must exist and remain operator-readable.

## Required enforcement points

The future code phase must enforce all of the following before transmission:

- live authority enabled
- launch window active
- readiness `ready`
- limited-live gate status `ready_for_review`
- manual halt inactive
- reconciliation clean
- live control state explicitly go
- allowed symbol match
- tiny notional within cap
- max open positions not exceeded
- explicit per-order approval present
- feed health acceptable
- prerequisite artifacts present

## Exact deny-by-default checks to implement

Future implementation must have explicit checks for:

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

## Tests required before or with implementation

Primary expected test files:

- `tests/unit/test_forward_paper_live_execution.py`
- `tests/unit/test_live_controls.py`
- `tests/unit/test_readiness_status.py`
- `tests/unit/test_live_gate.py`
- new focused tests for approval/authority/window artifacts if needed

Required coverage:

- live transmission disabled by default
- live authority cannot be inferred from artifact-only surfaces
- missing approval blocks transmission
- symbol mismatch blocks transmission
- oversize request blocks transmission
- manual halt blocks transmission
- readiness downgrade blocks transmission
- reconciliation mismatch blocks transmission
- stale/degraded/unavailable feed blocks transmission
- expired launch window blocks transmission
- deny reasons are surfaced clearly in artifacts

## Out-of-scope files unless implementation proves they are necessary

Avoid speculative edits to:

- signal generation
- regime classification
- portfolio logic unrelated to bounded transmission checks
- replay-only single-run logic
- replay matrix logic
- sandbox rehearsal behavior
- shadow evidence behavior
- baseline evaluation/reporting surfaces unrelated to limited-live control

## Implementation sequencing for the future code phase

Recommended later code order:

1. add authority/approval/window artifact models
2. add deny-by-default control evaluation
3. add runtime enforcement in forward loop
4. add transmission-boundary check
5. add focused negative-path tests
6. add one minimal positive-path test for explicitly approved tiny live transmission
7. validate that non-live modes still behave as before

## Exit criteria

Phase L1C is complete when:

- exact files and responsibility boundaries are frozen in writing
- required artifacts are named
- required tests are named
- out-of-scope areas are explicitly protected
- no runtime or CLI behavior changed

## Closeout conclusion

L1C defines the minimum implementation surface for a future bounded limited-live code phase.

Any future live-authority implementation must stay inside this map unless explicitly respecified.
