# Phase L2C — Bounded Live Transmission Implementation Scope Map

## Purpose

This phase maps the exact repository touchpoints for a future bounded live-transmission implementation.

L2C is docs-only.

It does not add executable live trading behavior.

## Relationship to prior phases

- L2A locked the smallest acceptable first real live transmission envelope.
- L2B defined the future bounded transmission design.
- L2C maps the exact code and artifact touchpoints that a future implementation phase would be allowed to modify.

## Implementation posture

Any future implementation must remain:
- deny-by-default
- single-runtime scoped
- single-symbol scoped
- tiny-notional scoped
- operator-mediated
- artifact-first
- fail-closed

L2C does not authorize widening beyond that posture.

## Expected touchpoint groups

A future bounded implementation phase is expected to touch only the following groups.

### 1. Authority and control artifacts

Expected touchpoints:
- limited-live authority artifact surface
- live approval artifact surface
- launch-window artifact surface
- transmission decision artifact surface
- manual halt / readiness control artifacts

Expected purpose:
- load and validate bounded live authority prerequisites
- preserve deny-by-default behavior
- write operator-readable decision evidence

### 2. Forward runtime execution seam

Expected touchpoints:
- the existing limited-live execution seam
- the runtime path that currently evaluates bounded transmission prerequisites
- the artifact-writing path around transmission decisions

Expected purpose:
- keep one single bounded transmission path
- prevent shadow or sandbox path widening
- prevent hidden alternate transmission routes

### 3. Venue adapter boundary

Expected touchpoints:
- one explicit bounded venue transmission boundary only
- no multi-venue routing
- no failover logic
- no hidden retry path

Expected purpose:
- isolate the first real transmission attempt to one explicit adapter seam
- keep all behavior fail-closed on missing prerequisites or unexpected responses

### 4. Approval and request identity flow

Expected touchpoints:
- request identity fields
- approval artifact lookup or validation
- expiry / mutation invalidation checks
- symbol and notional enforcement path

Expected purpose:
- ensure exact request-level approval
- ensure approval cannot silently carry to mutated or later requests

### 5. Post-attempt evidence path

Expected touchpoints:
- per-request decision artifact
- per-request result artifact
- deny reason fields or deny artifact
- preserved runtime evidence directory

Expected purpose:
- keep operator review artifact-first
- make any attempted bounded live action auditable

## Expected no-touch areas

A future bounded implementation phase should avoid touching:
- paper replay harness behavior
- matrix behavior
- sandbox rehearsal behavior
- shadow execution behavior
- strategy generation logic
- risk model logic except where already enforced by bounded live prerequisites
- unrelated operator docs
- deployment or infrastructure surfaces

## Expected concrete file categories

A future bounded implementation phase will likely need to inspect and possibly touch files in these categories:

- runtime control-state modules
- limited-live authority / approval / launch-window modules
- execution-boundary or transmission-decision modules
- venue adapter boundary modules
- CLI/runtime orchestration files that already persist bounded control artifacts
- focused tests covering deny-by-default and bounded positive-path eligibility

L2C does not authorize touching anything outside those categories without a separately scoped phase.

## Required artifact continuity

Any future implementation must preserve continuity for:
- live authority state
- launch-window state
- approval state
- transmission decision state
- transmission result state
- halt event state
- runtime evidence directory layout

No second artifact tree or alternate authority surface should be introduced.

## Required tests for future implementation

A future bounded implementation phase must include focused tests for:
- deny-by-default transmission
- positive-path bounded eligibility
- missing approval deny
- expired approval deny
- symbol mismatch deny
- notional breach deny
- launch-window inactive deny
- readiness downgrade deny
- manual halt deny
- reconciliation not-clean deny
- stale/degraded feed deny
- post-attempt artifact persistence
- proof that sandbox and shadow paths remain unchanged

## Explicit out of scope for L2C

L2C does not permit:
- executable live transmission
- runtime code changes
- new services, queues, or workers
- UI control surfaces
- broader live-trading workflow expansion
- multi-symbol or multi-venue widening
- autonomous retry or recovery logic

## Exit criteria

L2C is complete when:
- the future implementation touchpoints are explicitly mapped
- no-touch areas are explicitly recorded
- required artifact continuity is named
- required future tests are named
- no code or live authority is added

## Result

L2C records the smallest acceptable implementation touchpoint map for a future bounded live-transmission phase without adding executable live trading behavior.
