# Crypto Agent

Controlled, auditable, risk-aware crypto trading system built in bounded phases.

Phase 0 defines the architecture and operating model. The repository currently includes all ten bounded implementation phases, Validation Tracks 1-5, the paper replay harness, Harness Validation 1-4, the paper-run matrix, Matrix Validation 1-2, and a frozen record of the validated system state:

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
- validated paper replay harness artifacts and snapshot coverage over summary, replay, and event-stream views
- validated paper-run matrix manifest and replay-aggregate artifacts with snapshot coverage
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
- advisory-only LLM prompt payloads and strict JSON parsing wrappers
- unit tests for config, contracts, replay loading, market-data quality checks, signals, risk policy, execution, journaling, evaluation, LLM parsing, incident drills, and replay snapshot regression coverage
- validation tracks for incident drills, mixed replay runs, multi-run replay suites, replay scorecard snapshots, and review/operator-summary snapshots
- validated paper replay harness with regression snapshots for summary outputs, replay-derived artifacts, adverse runs, and event-stream views
- validated paper-run matrix with regression snapshots for manifest and replay-derived batch aggregates

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

The frozen harness baseline is documented in [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md).

## Paper Run Matrix

Run the validated fixed batch matrix on top of the existing harness:

```bash
crypto-agent-paper-matrix-run --config config/paper.yaml --matrix-run-id demo-paper-matrix
```

Artifacts are written to:

- `journals/<run-id>.jsonl` for each generated run
- `runs/<run-id>/summary.json` for each generated run
- `runs/<matrix-run-id>/manifest.json` for the batch manifest

The frozen matrix baseline is documented in [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md).

## Repo Layout

The package layout follows the bounded module structure in [docs/ARCHITECTURE.md](/Users/muhammadaatif/cryp/docs/ARCHITECTURE.md). Empty directories are intentional placeholders for later phases.

## Execution Rules

Before making changes, read:

- [docs/ARCHITECTURE.md](/Users/muhammadaatif/cryp/docs/ARCHITECTURE.md)
- [docs/BASELINE.md](/Users/muhammadaatif/cryp/docs/BASELINE.md)
- [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md)
- [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md)
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

Work in one bounded phase at a time. Treat [docs/BASELINE.md](/Users/muhammadaatif/cryp/docs/BASELINE.md) as the system reference point, [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md) as the single-run operator-path reference point, and [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md) as the batch operator-path reference point for future work. Validate before advancing. Do not add live trading features until the paper-trading path is stable, replayable, and explicitly approved to widen scope.

After edits, run `make validate` so Ruff autofix runs before format, lint, typecheck, and test. Use `make validate-check` only when you specifically want a non-mutating pass on an already-clean tree.
