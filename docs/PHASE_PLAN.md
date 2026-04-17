# Phase Plan

## Execution Rule

Complete one bounded phase at a time. Validate that phase before starting the next. Do not backfill future-phase functionality opportunistically.

## Completed Implementation Phases

- Phase 1: repository foundation
- Phase 2: core contracts and config expansion
- Phase 3: market data and replay skeleton
- Phase 4: features and regime rules
- Phase 5: signal engine
- Phase 6: risk and policy layer
- Phase 7: paper execution simulator
- Phase 8: monitoring and journaling
- Phase 9: evaluation and replay
- Phase 10: LLM advisory layer

## Completed Validation Tracks

- Validation Track 1: incident drills and replay fixture expansion
- Validation Track 2: mixed replay runs and recovery drills
- Validation Track 3: multi-run replay suites
- Validation Track 4: replay regression snapshots
- Validation Track 5: review packet and operator-summary regression snapshots

## Completed Harness Work

- Paper Run Harness: end-to-end replay runner
- Harness Validation 1: paper-run summary regression snapshots
- Harness Validation 2: replay artifact regression snapshots
- Harness Validation 3: adverse paper-run snapshots
- Harness Validation 4: event-stream regression snapshots
- Single Run Report Pack: operator-readable single-run report artifact
- Single-Run Report Validation: report regression snapshot coverage
- Trade Ledger Surface: operator-readable single-run trade ledger artifact
- Trade Ledger Validation: trade-ledger regression snapshot coverage

## Completed Matrix Work

- Paper Run Matrix: fixed five-case batch replay runner
- Matrix Validation 1: manifest regression snapshots
- Matrix Validation 2: replay aggregate regression snapshots
- Matrix Report Pack: operator-readable batch report artifact
- Matrix Report Validation: report regression snapshot coverage
- Matrix Comparison Surface: operator-readable batch comparison artifact
- Matrix Comparison Validation: batch comparison regression snapshot coverage
- Matrix Trade Ledger Surface: operator-readable batch trade ledger artifact
- Matrix Trade Ledger Validation: batch trade-ledger regression snapshot coverage
- Paper PnL Surface: deterministic replay-derived PnL and ending-equity accounting

## Baseline Freeze

The current repository state is frozen as the validated baseline documented in [docs/BASELINE.md](/Users/muhammadaatif/cryp/docs/BASELINE.md). Future work should treat that document as the reference point and propose new bounded tracks relative to it.

## Completed Forward Runtime Work

- Phase A: forward paper runtime
- Phase B: live market data and venue constraints
- Phase C: account state, reconciliation, and recovery
- Phase D: shadow and sandbox execution adapter
- Phase E: live risk controls and ops guardrails
- Phase F: soak evaluation, shadow evaluation, and live gate
- Phase G3: venue preflight probe and operator fail-fast diagnostics
- Phase G4: preflight-to-batch consistency diagnostics
- Phase G5: preflight launch-truth hardening
- Phase G6: shadow canary launchability evidence
- Phase G7: freeze shadow canary operator path
- Phase G8: operator live-launch verdict artifact
- Phase G9: launch verdict operator rehearsal
- Live Launch Runbook Freeze: canonical first tiny-live review procedure without executable live mode

## Harness Freeze

The paper replay harness is frozen as the validated operator path documented in [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md). Future operator-facing work should extend that path rather than introducing a second CLI or parallel harness.

## Matrix Freeze

The paper-run matrix is frozen as the validated batch operator path documented in [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md). Future batch operator work should extend that path rather than introducing a second matrix runner or parallel batch flow.

## Current Validation Path

- `make validate`
- `make validate-check`

## Stop Conditions

Stop and report if:

- a dependency or environment issue blocks validation
- the requested phase would require out-of-scope infrastructure
- existing repo state conflicts with the bounded phase
