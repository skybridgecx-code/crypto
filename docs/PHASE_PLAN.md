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

## Baseline Freeze

The current repository state is frozen as the validated baseline documented in [docs/BASELINE.md](/Users/muhammadaatif/cryp/docs/BASELINE.md). Future work should treat that document as the reference point and propose new bounded tracks relative to it.

## Harness Freeze

The paper replay harness is frozen as the validated operator path documented in [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md). Future operator-facing work should extend that path rather than introducing a second CLI or parallel harness.

## Current Validation Path

- `make format`
- `make lint`
- `make typecheck`
- `make test`
- `make validate`

## Stop Conditions

Stop and report if:

- a dependency or environment issue blocks validation
- the requested phase would require out-of-scope infrastructure
- existing repo state conflicts with the bounded phase
