# Harness Baseline

## What Matters

The paper replay harness is now the validated single-run operator path on top of the frozen simulation-first baseline. Future single-run operator work should extend this path, not fork a second one.

The canonical operator-facing summary across single-run and batch paths is documented in [docs/OPERATOR_SURFACES.md](/Users/muhammadaatif/cryp/docs/OPERATOR_SURFACES.md).

## Operator Command Path

- console entrypoint: `crypto-agent-paper-run`
- module entrypoint: `crypto_agent.cli.main:main`
- core function: `crypto_agent.cli.main.run_paper_replay(...)`

Example:

```bash
crypto-agent-paper-run tests/fixtures/paper_candles_breakout_long.jsonl --config config/paper.yaml --run-id demo-paper-run
```

## Inputs

- replay candle fixture JSONL path
- paper-mode config path
- explicit or generated `run_id`
- optional starting `equity_usd`

The harness is validated only for `paper` mode and existing replay candle fixtures.

## Outputs

- append-only journal at `journals/<run-id>.jsonl`
- run summary at `runs/<run-id>/summary.json`
- operator report at `runs/<run-id>/report.md`
- trade ledger at `runs/<run-id>/trade_ledger.json`
- replay-derived scorecard
- replay-derived PnL summary:
  - `starting_equity_usd`
  - `gross_realized_pnl_usd`
  - `total_fee_usd`
  - `net_realized_pnl_usd`
  - `ending_unrealized_pnl_usd`
  - `ending_equity_usd`
  - `return_fraction`
- replay-derived trade ledger rows:
  - `proposal_id`
  - `symbol`
  - `side`
  - `strategy_id`
  - `intent_id`
  - `filled_size`
  - `average_fill_price`
  - `total_fee_usd`
  - `gross_realized_pnl_usd`
  - `net_realized_pnl_usd`
  - `ending_status`
- replay-derived review packet
- replay-derived operator summary

## Artifact Locations

- operator journal artifacts:
  - [journals](/Users/muhammadaatif/cryp/journals)
- operator run summaries:
  - [runs](/Users/muhammadaatif/cryp/runs)
- harness snapshot artifacts:
  - [tests/fixtures/snapshots](/Users/muhammadaatif/cryp/tests/fixtures/snapshots)

## Operator-Readable Artifact Path

- single-run operator report:
  - `runs/<run-id>/report.md`
- single-run trade ledger:
  - `runs/<run-id>/trade_ledger.json`

## Validated Fixture Matrix

Positive paths:

- `paper_candles_breakout_long.jsonl`
- `paper_candles_mean_reversion_short.jsonl`

Adverse paths:

- `paper_candles_high_volatility.jsonl`: no-signal / empty journal path
- `paper_candles_breakout_long.jsonl` with low equity: reject path
- `paper_candles_breakout_long.jsonl` with zero drawdown threshold: halt path

## Snapshot Surfaces

- summary artifact snapshots:
  - [tests/unit/test_paper_run_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_snapshots.py)
- replay-derived scorecard, review packet, and operator-summary snapshots:
  - [tests/unit/test_paper_run_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_replay_snapshots.py)
- deterministic paper PnL tests:
  - [tests/unit/test_paper_run_pnl.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_pnl.py)
- replay-derived event-count and event-sequence snapshots:
  - [tests/unit/test_paper_run_event_stream_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_event_stream_snapshots.py)
- single-run operator report snapshots:
  - [tests/unit/test_paper_run_report_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_report_snapshots.py)
- single-run trade-ledger snapshots:
  - [tests/unit/test_paper_run_trade_ledger_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_trade_ledger_snapshots.py)

## Ledger Reconciliation Rules

- trade-ledger rows must be derived from the existing journal, replay, and replay-derived PnL path only
- ledger fee totals must reconcile to replay PnL `total_fee_usd`
- ledger gross realized PnL totals must reconcile to replay PnL `gross_realized_pnl_usd`
- ledger net realized PnL totals must reconcile to replay PnL `net_realized_pnl_usd`
- fill and partial rows must reconcile to `order.filled` events for the linked `intent_id`
- reject rows must reconcile to `order.rejected` without linked fill events
- halt rows must remain pre-execution rows with no linked intent or fill activity
- no-signal runs must write an empty ledger with `row_count: 0`

## Validation Command Path

- `make phase-start`
- `make phase-finish`
- `make phase-close-check`

Phase-start rule:

- run `make phase-start` before any edits in a new bounded phase
- if it fails on dirty status, stash or commit interrupted work before starting new work

Phase-end rule:

- run `make phase-finish` after the bounded harness change is implemented
- if it reports a dirty tree, commit intended changes and autofixes or revert unrelated churn before treating the phase as complete
- run `make phase-close-check` on the final clean tree before closing the phase

## Batch Extension

The validated batch operator path that builds on this harness is documented in [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md). Batch work should extend that matrix runner instead of adding a second batch path.

## Known Limits

- no live execution
- no exchange connectivity or reconciliation
- no second operator path
- harness outputs are deterministic control artifacts, not live-fill realism
- ending marks use the replay fixture's final available close for each symbol
- no funding-rate, borrow-cost, or intrabar mark accounting
- replay fixtures remain narrow and synthetic relative to real market conditions

## Non-Goals

- do not treat the harness as production trading infrastructure
- do not bypass the journal or replay path for operator outputs
- do not add UI, API, or live venue behavior under harness work unless explicitly assigned
