# Crypto Agent

Controlled, auditable, risk-aware crypto trading system built in bounded phases.

Phase 0 defines the architecture and operating model. The repository currently includes all ten bounded implementation phases, Validation Tracks 1-5, the paper replay harness, Harness Validation 1-4, the paper-run matrix, Matrix Validation 1-2, Matrix Report Pack, Matrix Report Validation, Matrix Trade Ledger Surface, Matrix Trade Ledger Validation, Trade Ledger Surface, Trade Ledger Validation, and a frozen record of the validated system state:

- Python packaging and quality gates
- configuration and shared contracts
- event and schema artifacts
- market-data models and replay skeleton
- deterministic features and regime rules
- deterministic signal proposal generation
- deterministic risk, policy, and kill-switch checks
- deterministic paper execution simulation
- deterministic monitoring and append-only journaling
- deterministic replay and evaluation workflows
- deterministic advisory-only LLM wrappers and prompts
- replay regression snapshots for scorecards, event counts, review packets, and operator summaries
- validated paper replay harness artifacts and snapshot coverage over summary, replay, event-stream, operator-report, and trade-ledger views
- validated paper-run matrix manifest, replay-aggregate, operator-report, and trade-ledger artifacts with snapshot coverage
- initial docs and tests

This repository is intentionally simulation-first. Live trading is out of scope until paper-mode validation, replayability, and guardrail coverage are in place.

## Principles

- Protect capital first.
- Keep deterministic policy and risk logic outside the LLM.
- Make every action explainable after the fact.
- Default to `research_only`, then `paper`.
- Prefer simple, testable building blocks over premature infrastructure.

## Current Scope

Implemented so far:

- repository scaffold and module boundaries
- `pyproject.toml`, `Makefile`, and `.env.example`
- architecture and operating model docs
- typed config, enums, IDs, and core event/order/proposal contracts
- checked-in JSON schema artifacts for core contracts
- market-data models, replay loading, and paper-feed adapter skeleton
- deterministic momentum, volatility, liquidity features, and rule-based regime classification
- deterministic breakout and mean-reversion proposal generation
- deterministic sizing, exposure checks, policy guardrails, and kill-switch evaluation
- deterministic order normalization, simulator fills, rejections, partial fills, and idempotent paper submission
- deterministic health snapshots, alerts, event serialization, and append-only journal helpers
- deterministic journal replay and scorecard generation over the existing event stream
- deterministic replay-derived paper PnL and ending-equity accounting over the existing journal plus final replay close
- advisory-only LLM prompt payloads and strict JSON parsing wrappers
- unit tests for config, contracts, replay loading, market-data quality checks, signals, risk policy, execution, journaling, evaluation, LLM parsing, incident drills, and replay snapshot regression coverage
- validation tracks for incident drills, mixed replay runs, multi-run replay suites, replay scorecard snapshots, and review/operator-summary snapshots
- validated paper replay harness with regression snapshots for summary outputs, replay-derived artifacts, adverse runs, and event-stream views
- validated single-run trade ledger with regression snapshots and replay/PnL reconciliation checks
- validated paper-run matrix with regression snapshots for manifest, replay-derived batch aggregates, operator-readable report artifacts, and batch trade-ledger artifacts

Explicitly not implemented yet:

- exchange integrations
- live trading
- production deployment or operator UI

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
make validate
```

## Paper Replay Harness

Run the validated paper-mode harness against a replay fixture:

```bash
crypto-agent-paper-run tests/fixtures/paper_candles_breakout_long.jsonl --config config/paper.yaml --run-id demo-paper-run
```

Artifacts are written to:

- `journals/<run-id>.jsonl`
- `runs/<run-id>/summary.json`
- `runs/<run-id>/report.md`
- `runs/<run-id>/trade_ledger.json`

The single-run summary, report, and ledger now include deterministic paper PnL and trade-ledger surfaces:

- `starting_equity_usd`
- `gross_realized_pnl_usd`
- `total_fee_usd`
- `net_realized_pnl_usd`
- `ending_unrealized_pnl_usd`
- `ending_equity_usd`
- `return_fraction`
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

The frozen harness baseline is documented in [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md).
The canonical operator-surface summary is documented in [docs/OPERATOR_SURFACES.md](/Users/muhammadaatif/cryp/docs/OPERATOR_SURFACES.md).

## Paper Run Matrix

Run the validated fixed batch matrix on top of the existing harness:

```bash
crypto-agent-paper-matrix-run --config config/paper.yaml --matrix-run-id demo-paper-matrix
```

Artifacts are written to:

- `journals/<run-id>.jsonl` for each generated run
- `runs/<run-id>/summary.json` for each generated run
- `runs/<matrix-run-id>/manifest.json` for the batch manifest
- `runs/<matrix-run-id>/matrix_trade_ledger.json` for the batch trade ledger
- `runs/<matrix-run-id>/report.md` for the batch operator report

The matrix replay aggregate, trade ledger, and report now also include deterministic aggregate PnL totals derived from the per-run journals plus the replay fixtures' final closes. The matrix trade ledger includes one synthetic `no_signal` row for no-event runs so the fixed five-case batch artifact stays operator-complete.

The frozen matrix baseline is documented in [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md).

## Repo Layout

The package layout follows the bounded module structure in [docs/ARCHITECTURE.md](/Users/muhammadaatif/cryp/docs/ARCHITECTURE.md). Empty directories are intentional placeholders for later phases.

## Execution Rules

Before making changes, read:

- [docs/ARCHITECTURE.md](/Users/muhammadaatif/cryp/docs/ARCHITECTURE.md)
- [docs/BASELINE.md](/Users/muhammadaatif/cryp/docs/BASELINE.md)
- [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md)
- [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md)
- [docs/OPERATOR_SURFACES.md](/Users/muhammadaatif/cryp/docs/OPERATOR_SURFACES.md)
- [docs/OPERATING_MODEL.md](/Users/muhammadaatif/cryp/docs/OPERATING_MODEL.md)
- [docs/RISK_POLICY.md](/Users/muhammadaatif/cryp/docs/RISK_POLICY.md)
- [docs/PHASE_PLAN.md](/Users/muhammadaatif/cryp/docs/PHASE_PLAN.md)
- [docs/CODEX_HANDOFF.md](/Users/muhammadaatif/cryp/docs/CODEX_HANDOFF.md)

Before any new bounded phase, run:

```bash
make phase-start
```

This preflight fails fast unless all of the following are true:

- you are in the correct repository
- HEAD is resolvable and shown
- git status is clean

If preflight fails because work was interrupted, stash or commit that work before starting a new bounded phase.

Work in one bounded phase at a time. Treat [docs/BASELINE.md](/Users/muhammadaatif/cryp/docs/BASELINE.md) as the system reference point and [docs/OPERATOR_SURFACES.md](/Users/muhammadaatif/cryp/docs/OPERATOR_SURFACES.md) as the canonical operator-path summary for single-run and batch work. Validate before advancing. Do not add live trading features until the paper-trading path is stable, replayable, and explicitly approved to widen scope.

Required bounded-phase workflow:

1. `make phase-start`
2. do the bounded phase only
3. `make phase-finish`
4. if `make phase-finish` reports a dirty tree, commit intended changes and autofixes or revert unrelated churn before considering the phase complete
5. `make phase-close-check`

Command roles:

- `make validate` remains the edited-tree-safe validation path and is run inside `make phase-finish`
- `make validate-check` remains the final verification path on an already-clean tree and is run inside `make phase-close-check`
