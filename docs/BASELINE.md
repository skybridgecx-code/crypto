# Validated Baseline

## What Matters

This repository is frozen as a validated simulation-first baseline after Phases 1-10, Validation Tracks 1-5, the paper-run harness, Harness Validation 1-4, Single Run Report Pack, Single-Run Report Validation, Trade Ledger Surface, Trade Ledger Validation, the paper-run matrix, Matrix Validation 1-2, Matrix Report Pack, Matrix Report Validation, and Paper PnL Surface. It is the reference point for future bounded work.

## Current Architecture Surface

- market-data models, replay loading, and paper-feed skeleton
- deterministic features and regime classification
- deterministic breakout and mean-reversion proposals
- deterministic sizing, risk checks, policy guardrails, and kill-switch evaluation
- deterministic order normalization and paper execution simulation
- deterministic monitoring alerts, health snapshots, journaling, replay, and evaluation
- deterministic replay-derived paper PnL and ending-equity accounting
- deterministic replay-derived single-run trade ledger artifacts
- advisory-only LLM wrappers with strict JSON parsing
- validated paper replay harness and operator artifacts over the existing journal/replay path
- validated paper-run matrix and batch artifacts over the existing harness, journal, and replay path

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

## Completed Harness Work

- Paper Run Harness: validated end-to-end paper replay operator command
- Harness Validation 1: summary artifact regression snapshots
- Harness Validation 2: replay-derived artifact regression snapshots
- Harness Validation 3: adverse paper-run regression snapshots
- Harness Validation 4: harness event-stream regression snapshots
- Single Run Report Pack: operator-readable single-run report artifact (`report.md`)
- Single-Run Report Validation: report regression snapshot coverage
- Trade Ledger Surface: operator-readable single-run ledger artifact (`trade_ledger.json`)
- Trade Ledger Validation: ledger regression snapshot coverage

## Completed Matrix Work

- Paper Run Matrix: validated fixed-matrix batch replay runner
- Matrix Validation 1: manifest regression snapshots
- Matrix Validation 2: replay-derived batch aggregate snapshots
- Matrix Report Pack: operator-readable batch report artifact (`report.md`)
- Matrix Report Validation: report regression snapshot coverage

## Snapshot Surfaces

- replay scorecards and event-type counts:
  - [tests/unit/test_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_replay_snapshots.py)
- replay-derived review packets and operator summaries:
  - [tests/unit/test_review_packet_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_review_packet_snapshots.py)
- paper-run harness summary snapshots:
  - [tests/unit/test_paper_run_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_snapshots.py)
- paper-run harness replay-derived artifact snapshots:
  - [tests/unit/test_paper_run_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_replay_snapshots.py)
- paper-run harness event-stream snapshots:
  - [tests/unit/test_paper_run_event_stream_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_event_stream_snapshots.py)
- paper-run harness report snapshots:
  - [tests/unit/test_paper_run_report_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_report_snapshots.py)
- paper-run harness trade-ledger snapshots:
  - [tests/unit/test_paper_run_trade_ledger_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_trade_ledger_snapshots.py)
- deterministic paper PnL tests:
  - [tests/unit/test_paper_run_pnl.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_pnl.py)
- paper-run matrix manifest snapshots:
  - [tests/unit/test_paper_run_matrix_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_snapshots.py)
- paper-run matrix replay-aggregate snapshots:
  - [tests/unit/test_paper_run_matrix_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_replay_snapshots.py)
- paper-run matrix report snapshots:
  - [tests/unit/test_paper_run_matrix_report_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_report_snapshots.py)
- checked-in snapshot artifacts:
  - [tests/fixtures/snapshots](/Users/muhammadaatif/cryp/tests/fixtures/snapshots)

## Operator Path

The validated single-run operator command path is documented in [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md). The validated batch operator path is documented in [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md). The canonical operator-facing summary of both paths is documented in [docs/OPERATOR_SURFACES.md](/Users/muhammadaatif/cryp/docs/OPERATOR_SURFACES.md). Future operator-facing work should extend those paths instead of creating parallel CLIs or runtime entrypoints.

## Validation Command Path

- `make validate`
- `make validate-check`

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
