# Matrix Baseline

## What Matters

The paper-run matrix is now the validated batch operator path on top of the frozen single-run harness. Future batch operator work should extend this path, not create a second batch runner.

The canonical operator-facing summary across single-run and batch paths is documented in [docs/OPERATOR_SURFACES.md](/Users/muhammadaatif/cryp/docs/OPERATOR_SURFACES.md).

## Operator Command Path

- console entrypoint: `crypto-agent-paper-matrix-run`
- module entrypoint: `crypto_agent.cli.matrix:main`
- core function: `crypto_agent.cli.matrix.run_paper_replay_matrix(...)`

Example:

```bash
crypto-agent-paper-matrix-run --config config/paper.yaml --matrix-run-id demo-paper-matrix
```

## Fixed Matrix Cases

- `paper_candles_breakout_long.jsonl`: positive breakout fill path
- `paper_candles_mean_reversion_short.jsonl`: positive mean-reversion fill path
- `paper_candles_high_volatility.jsonl`: no-signal / empty journal path
- `paper_candles_breakout_long.jsonl` with `equity_usd=1.0`: reject path
- `paper_candles_breakout_long.jsonl` with `max_drawdown_fraction=0.0`: halt path

## Manifest Inputs And Outputs

Inputs:

- paper-mode config path
- optional explicit `matrix_run_id`
- the existing fixed five-case fixture matrix

Outputs:

- normal per-run journals at `journals/<run-id>.jsonl`
- normal per-run summaries at `runs/<run-id>/summary.json`
- aggregate manifest at `runs/<matrix-run-id>/manifest.json`
- aggregate matrix comparison at `runs/<matrix-run-id>/matrix_comparison.json`
- aggregate matrix ledger at `runs/<matrix-run-id>/matrix_trade_ledger.json`
- operator-readable batch report at `runs/<matrix-run-id>/report.md`

The manifest records:

- fixture
- run id
- journal path
- summary path
- top-level outcome counts derived from existing summary surfaces

The report records:

- aggregate manifest counts
- aggregate replay-derived totals
- aggregate replay-derived PnL totals
- per-run manifest and replay sections for operator review
- per-run replay-derived PnL sections for operator review

The matrix comparison records:

- `run_id`
- `fixture`
- `proposal_count`
- `halt_count`
- `order_reject_count`
- `fill_event_count`
- `partial_fill_intent_count`
- `alert_count`
- `ledger_row_count`
- `starting_equity_usd`
- `net_realized_pnl_usd`
- `ending_unrealized_pnl_usd`
- `ending_equity_usd`
- `return_fraction`

Comparison reconciliation expectations:

- comparison rows must reconcile to the referenced manifest outcome counts
- comparison rows must reconcile to replay-derived per-run pnl values
- comparison `ledger_row_count` must reconcile to the referenced per-run single-run ledgers
- aggregate totals must reconcile to the summed per-run comparison rows
- ranking fields must reconcile to deterministic ordering over the recorded return and ending-equity fields

Aggregate and ranking fields are part of the operator-facing batch comparison view:

- aggregate proposal, halt, reject, fill, partial-fill, alert, ledger-row, and pnl totals
- best and worst return run ids
- highest and lowest ending-equity run ids

The matrix trade ledger records:

- `matrix_run_id`
- `run_id`
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

Ledger reconciliation expectations:

- non-empty matrix rows must reconcile back to the referenced per-run single-run ledgers
- per-run ledger fee totals must reconcile to replay-derived per-run `total_fee_usd`
- per-run ledger gross/net realized pnl totals must reconcile to replay-derived per-run PnL
- aggregate matrix ledger fee/gross/net totals must reconcile to the summed per-run replay PnL totals
- `no_signal` rows are synthetic at the matrix layer only, so a no-signal run still appears in the batch ledger even though its per-run single-run ledger has `row_count: 0`

## Artifact Locations

- per-run journals:
  - [journals](/Users/muhammadaatif/cryp/journals)
- per-run summaries:
  - [runs](/Users/muhammadaatif/cryp/runs)
- checked-in matrix snapshots:
  - [tests/fixtures/snapshots](/Users/muhammadaatif/cryp/tests/fixtures/snapshots)

## Validated Snapshot Surfaces

- matrix manifest snapshots:
  - [tests/unit/test_paper_run_matrix_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_snapshots.py)
- matrix replay-aggregate snapshots rebuilt from manifest-referenced journals:
  - [tests/unit/test_paper_run_matrix_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_replay_snapshots.py)
- matrix comparison snapshots for `runs/<matrix-run-id>/matrix_comparison.json`:
  - [tests/unit/test_paper_run_matrix_comparison_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_comparison_snapshots.py)
- matrix report snapshots for `runs/<matrix-run-id>/report.md`:
  - [tests/unit/test_paper_run_matrix_report_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_report_snapshots.py)
- matrix trade-ledger snapshots for `runs/<matrix-run-id>/matrix_trade_ledger.json`:
  - [tests/unit/test_paper_run_matrix_trade_ledger_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_trade_ledger_snapshots.py)

## Validation Command Path

- `make phase-start`
- `make phase-finish`
- `make phase-close-check`

Phase-start rule:

- run `make phase-start` before any edits in a new bounded phase
- if it fails on dirty status, stash or commit interrupted work before starting new work

Phase-end rule:

- run `make phase-finish` after the bounded matrix change is implemented
- if it reports a dirty tree, commit intended changes and autofixes or revert unrelated churn before treating the phase as complete
- run `make phase-close-check` on the final clean tree before closing the phase

## Known Limits

- fixed five-case matrix only
- sequential local execution only
- no live execution
- no second batch runner
- no second comparison path
- no second batch ledger path
- no second report path
- no separate accounting path beyond replayed journals plus final replay closes
- no funding-rate, borrow-cost, or intrabar mark accounting
- batch outputs remain deterministic control artifacts, not live execution evidence

## Non-Goals

- do not treat the matrix runner as a scheduler, orchestrator, or production job system
- do not bypass the existing single-run harness, journal path, or replay path
- do not fork a parallel batch report artifact path
- do not add API, UI, or live venue behavior under matrix work unless explicitly assigned
