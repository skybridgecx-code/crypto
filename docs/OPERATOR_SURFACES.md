# Operator Surfaces

## What Matters

This document is the canonical operator-facing reference for the validated local paths in this repository.

It covers:

- the validated single-run operator path
- the validated batch operator path
- the file artifacts each path writes
- the snapshot-locked validation surfaces that protect those artifacts
- the required bounded-work workflow before future changes

## Single-Run Operator Path

Command path:

- console entrypoint: `crypto-agent-paper-run`
- module entrypoint: `crypto_agent.cli.main:main`
- core function: `crypto_agent.cli.main.run_paper_replay(...)`

Example:

```bash
crypto-agent-paper-run tests/fixtures/paper_candles_breakout_long.jsonl --config config/paper.yaml --run-id demo-paper-run
```

Single-run artifacts:

- append-only journal: `journals/<run-id>.jsonl`
- summary artifact: `runs/<run-id>/summary.json`
- operator-readable report: `runs/<run-id>/report.md`

Single-run replay-derived surfaces:

- replay scorecard
- replay PnL summary:
  - `starting_equity_usd`
  - `gross_realized_pnl_usd`
  - `total_fee_usd`
  - `net_realized_pnl_usd`
  - `ending_unrealized_pnl_usd`
  - `ending_equity_usd`
  - `return_fraction`
- review packet
- operator summary

Validated single-run fixture coverage:

- positive breakout path
- positive mean-reversion path
- no-signal path
- reject path
- halt path

## Matrix Operator Path

Command path:

- console entrypoint: `crypto-agent-paper-matrix-run`
- module entrypoint: `crypto_agent.cli.matrix:main`
- core function: `crypto_agent.cli.matrix.run_paper_replay_matrix(...)`

Example:

```bash
crypto-agent-paper-matrix-run --config config/paper.yaml --matrix-run-id demo-paper-matrix
```

Fixed matrix cases:

- `paper_candles_breakout_long.jsonl`: positive breakout fill path
- `paper_candles_mean_reversion_short.jsonl`: positive mean-reversion fill path
- `paper_candles_high_volatility.jsonl`: no-signal / empty journal path
- `paper_candles_breakout_long.jsonl` with `equity_usd=1.0`: reject path
- `paper_candles_breakout_long.jsonl` with `max_drawdown_fraction=0.0`: halt path

Matrix artifacts:

- per-run journals: `journals/<run-id>.jsonl`
- per-run summaries: `runs/<run-id>/summary.json`
- batch manifest: `runs/<matrix-run-id>/manifest.json`
- batch operator report: `runs/<matrix-run-id>/report.md`

Matrix replay-derived surfaces:

- per-run replay scorecard summaries rebuilt from manifest-referenced journals
- aggregate replay totals across the fixed matrix
- per-run replay PnL summaries rebuilt from manifest-referenced journals
- aggregate replay PnL totals across the fixed matrix

## Snapshot-Locked Validation Surfaces

Single-run:

- summary snapshots:
  - [tests/unit/test_paper_run_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_snapshots.py)
- replay-derived artifact snapshots:
  - [tests/unit/test_paper_run_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_replay_snapshots.py)
- event-stream snapshots:
  - [tests/unit/test_paper_run_event_stream_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_event_stream_snapshots.py)
- report snapshots:
  - [tests/unit/test_paper_run_report_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_report_snapshots.py)

Matrix:

- manifest snapshots:
  - [tests/unit/test_paper_run_matrix_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_snapshots.py)
- replay-aggregate snapshots:
  - [tests/unit/test_paper_run_matrix_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_replay_snapshots.py)
- report snapshots:
  - [tests/unit/test_paper_run_matrix_report_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_report_snapshots.py)

Checked-in snapshot artifacts:

- [tests/fixtures/snapshots](/Users/muhammadaatif/cryp/tests/fixtures/snapshots)

## Required Workflow

For any future bounded phase or validation track that touches operator surfaces:

1. `make phase-start`
2. do the bounded phase only
3. `make validate`
4. commit Ruff autofix changes if they are part of the intended scoped change; otherwise revert unrelated autofix churn before commit
5. optionally run `make validate-check` when a non-mutating verification pass is specifically needed on the final clean tree

Additional rule:

- if `make phase-start` fails because the worktree is dirty, stash or commit interrupted work before starting new work

## Known Limits

- paper mode only
- local replay fixtures only
- deterministic simulator outputs only
- no live execution
- no exchange integration
- no funding-rate or borrowing-cost accounting
- no intrabar mark model
- no API or UI operator surface
- no second single-run path
- no second batch path

## Non-Goals

- do not treat these paths as production trading infrastructure
- do not bypass the journal, replay, or snapshot surfaces for operator outputs
- do not fork alternative CLIs, manifests, or report artifacts without an explicit bounded assignment
