# Operator Surfaces

## What Matters

This document is the canonical operator-facing reference for the validated local paths in this repository.

It covers:

- the validated single-run operator path
- the validated batch operator path
- the validated forward-runtime gate and readiness path
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
- trade ledger artifact: `runs/<run-id>/trade_ledger.json`

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
- trade ledger rows:
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
- batch comparison artifact: `runs/<matrix-run-id>/matrix_comparison.json`
- batch trade ledger: `runs/<matrix-run-id>/matrix_trade_ledger.json`
- batch operator report: `runs/<matrix-run-id>/report.md`

Matrix replay-derived surfaces:

- per-run replay scorecard summaries rebuilt from manifest-referenced journals
- aggregate replay totals across the fixed matrix
- per-run replay PnL summaries rebuilt from manifest-referenced journals
- aggregate replay PnL totals across the fixed matrix
- matrix comparison rows rebuilt from manifest-referenced summaries, replays, and ledgers:
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
- matrix comparison aggregate and ranking fields:
  - aggregate totals across the fixed matrix
  - best and worst return run ids
  - highest and lowest ending-equity run ids
- matrix trade-ledger rows rebuilt from manifest-referenced per-run ledgers:
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
- note:
  - `no_signal` rows are synthetic at the matrix layer so the fixed batch ledger stays complete even when a per-run single-run ledger has `row_count: 0`

## Forward Runtime Gate Path

Command path:

- console entrypoint: `crypto-agent-forward-paper-run`
- module entrypoint: `crypto_agent.cli.forward_paper:main`
- core function: `crypto_agent.runtime.loop.run_forward_paper_runtime(...)`

Current executable modes:

- `paper`
- `shadow`
- `sandbox`

Gate and readiness artifacts:

- runtime status: `runs/<runtime-id>/forward_paper_status.json`
- runtime history: `runs/<runtime-id>/forward_paper_history.jsonl`
- live-market preflight probe: `runs/<runtime-id>/live_market_preflight.json`
- shadow canary evaluation: `runs/<runtime-id>/shadow_canary_evaluation.json`
- account state: `runs/<runtime-id>/account_state.json`
- reconciliation report: `runs/<runtime-id>/reconciliation_report.json`
- live control status: `runs/<runtime-id>/live_control_status.json`
- readiness status: `runs/<runtime-id>/live_readiness_status.json`
- manual control state: `runs/<runtime-id>/manual_control_state.json`
- soak evaluation: `runs/<runtime-id>/soak_evaluation.json`
- shadow evaluation: `runs/<runtime-id>/shadow_evaluation.json`
- live-gate threshold summary: `runs/<runtime-id>/live_gate_threshold_summary.json`
- live-gate decision: `runs/<runtime-id>/live_gate_decision.json`
- live launch verdict: `runs/<runtime-id>/live_launch_verdict.json`
- live-gate report: `runs/<runtime-id>/live_gate_report.md`

Canonical first-launch runbook:

- [docs/LIVE_LAUNCH_RUNBOOK.md](/Users/muhammadaatif/cryp/docs/LIVE_LAUNCH_RUNBOOK.md)

The runbook freezes the future tiny-live review procedure only. It does not enable live execution today.

Forward-runtime operator workflow for a candidate live-market environment:

1. `crypto-agent-forward-paper-run --preflight-only ...`
2. stop if `live_market_preflight.json.batch_readiness != true`
3. `crypto-agent-forward-paper-run --canary-only --execution-mode shadow ...`
4. stop if `shadow_canary_evaluation.json.state != "pass"`
5. run the longer bounded shadow evidence session set
6. review the final `live_launch_verdict.json` only after preflight, canary, and gate artifacts exist

Operator note:

- if you want the verdict to reflect launch-review readiness rather than an intentional operator hold, the runtime readiness surface must already be `status == "ready"` and `limited_live_gate_status == "ready_for_review"`

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
- trade-ledger snapshots:
  - [tests/unit/test_paper_run_trade_ledger_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_trade_ledger_snapshots.py)

Matrix:

- manifest snapshots:
  - [tests/unit/test_paper_run_matrix_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_snapshots.py)
- replay-aggregate snapshots:
  - [tests/unit/test_paper_run_matrix_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_replay_snapshots.py)
- comparison snapshots:
  - [tests/unit/test_paper_run_matrix_comparison_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_comparison_snapshots.py)
- report snapshots:
  - [tests/unit/test_paper_run_matrix_report_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_report_snapshots.py)
- trade-ledger snapshots:
  - [tests/unit/test_paper_run_matrix_trade_ledger_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_trade_ledger_snapshots.py)

Forward runtime gate and readiness:

- runtime and recovery validation:
  - [tests/unit/test_forward_paper_runtime.py](/Users/muhammadaatif/cryp/tests/unit/test_forward_paper_runtime.py)
  - [tests/unit/test_runtime_recovery.py](/Users/muhammadaatif/cryp/tests/unit/test_runtime_recovery.py)
- shadow canary validation and snapshots:
  - [tests/unit/test_runtime_canary.py](/Users/muhammadaatif/cryp/tests/unit/test_runtime_canary.py)
- readiness and control validation:
  - [tests/unit/test_readiness_status.py](/Users/muhammadaatif/cryp/tests/unit/test_readiness_status.py)
- soak evaluation validation:
  - [tests/unit/test_soak_evaluation.py](/Users/muhammadaatif/cryp/tests/unit/test_soak_evaluation.py)
- shadow evaluation validation:
  - [tests/unit/test_shadow_evaluation.py](/Users/muhammadaatif/cryp/tests/unit/test_shadow_evaluation.py)
- live-gate validation:
  - [tests/unit/test_live_gate.py](/Users/muhammadaatif/cryp/tests/unit/test_live_gate.py)

Checked-in snapshot artifacts:

- [tests/fixtures/snapshots](/Users/muhammadaatif/cryp/tests/fixtures/snapshots)

## Required Workflow

For any future bounded phase or validation track that touches operator surfaces:

1. `make phase-start`
2. do the bounded phase only
3. `make phase-finish`
4. if `make phase-finish` reports a dirty tree, commit intended Ruff autofix changes or revert unrelated churn before treating the phase as complete
5. `make phase-close-check`

Additional rule:

- if `make phase-start` fails because the worktree is dirty, stash or commit interrupted work before starting new work
- if work is interrupted after `make phase-finish`, stash or commit it before starting the next bounded phase

## Known Limits

- trusted account state remains paper-derived
- `shadow` remains no-transmit evidence only
- `sandbox` remains sandbox-only evidence only
- no executable `limited_live` mode
- no unrestricted live execution
- no funding-rate or borrowing-cost accounting
- no intrabar mark model
- no API or UI operator surface
- no second single-run path
- no second batch path

## Non-Goals

- do not treat these paths as production trading infrastructure
- do not bypass the journal, replay, or snapshot surfaces for operator outputs
- do not fork alternative CLIs, manifests, or report artifacts without an explicit bounded assignment

## Launch verdict reason codes

The operator-facing reason-code map for `runs/<runtime-id>/live_launch_verdict.json` is documented in `docs/LAUNCH_VERDICT_REASON_CODES.md`.

This map explains each known reason code, the source artifact, the operator action, whether rerun is allowed, and whether the operator must stop.
