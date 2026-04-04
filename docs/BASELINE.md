# Validated Baseline

## What Matters

This repository is frozen as a validated simulation-first baseline after Phases 1-10 and Validation Tracks 1-5. It is the reference point for future bounded work.

## Current Architecture Surface

- market-data models, replay loading, and paper-feed skeleton
- deterministic features and regime classification
- deterministic breakout and mean-reversion proposals
- deterministic sizing, risk checks, policy guardrails, and kill-switch evaluation
- deterministic order normalization and paper execution simulation
- deterministic monitoring alerts, health snapshots, journaling, replay, and evaluation
- advisory-only LLM wrappers with strict JSON parsing

## Completed Phases

- Phase 1: repository foundation
- Phase 2: core contracts and config
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

## Snapshot Surfaces

- replay scorecards and event-type counts:
  - [tests/unit/test_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_replay_snapshots.py)
- replay-derived review packets and operator summaries:
  - [tests/unit/test_review_packet_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_review_packet_snapshots.py)
- checked-in snapshot artifacts:
  - [tests/fixtures/snapshots](/Users/muhammadaatif/cryp/tests/fixtures/snapshots)

## Validation Command Path

- `make format`
- `make lint`
- `make typecheck`
- `make test`
- `make validate`

## Known Limits

- no live trading
- no exchange integration
- no operator UI or dashboard
- no production deployment path
- simulator behavior is deterministic and useful for control validation, not live-fill realism
- limited-live remains a documented future control mode, not a baseline-trusted operating mode

## Non-Goals

- do not treat this baseline as production-ready
- do not expand runtime authority without an explicit bounded assignment
- do not bypass replay, journal, or snapshot validation when changing accounting behavior
