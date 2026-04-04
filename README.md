# Crypto Agent

Controlled, auditable, risk-aware crypto trading system built in bounded phases.

Phase 0 defines the architecture and operating model. The repository currently includes the first seven bounded implementation phases:

- Python packaging and quality gates
- configuration and shared contracts
- event and schema artifacts
- market-data models and replay skeleton
- deterministic features and regime rules
- deterministic signal proposal generation
- deterministic risk, policy, and kill-switch checks
- deterministic paper execution simulation
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
- unit tests for config, contracts, replay loading, market-data quality checks, signals, risk policy, and execution

Explicitly not implemented yet:

- exchange integrations
- trading strategies
- monitoring
- journaling
- live trading

## Quick Start

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
make validate
```

## Repo Layout

The package layout follows the bounded module structure in [docs/ARCHITECTURE.md](/Users/muhammadaatif/cryp/docs/ARCHITECTURE.md). Empty directories are intentional placeholders for later phases.

## Execution Rules

Before making changes, read:

- [docs/ARCHITECTURE.md](/Users/muhammadaatif/cryp/docs/ARCHITECTURE.md)
- [docs/OPERATING_MODEL.md](/Users/muhammadaatif/cryp/docs/OPERATING_MODEL.md)
- [docs/RISK_POLICY.md](/Users/muhammadaatif/cryp/docs/RISK_POLICY.md)
- [docs/PHASE_PLAN.md](/Users/muhammadaatif/cryp/docs/PHASE_PLAN.md)
- [docs/CODEX_HANDOFF.md](/Users/muhammadaatif/cryp/docs/CODEX_HANDOFF.md)

Work in one bounded phase at a time. Validate before advancing. Do not add live trading features until the paper-trading path is stable and replayable.
