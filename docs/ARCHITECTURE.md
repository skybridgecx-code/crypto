# Architecture

## What Matters

The system is designed as a controlled trading platform, not a black-box autonomous bot. Deterministic risk, policy, and execution boundaries remain outside any LLM component.

## Top-Level Flow

1. Market data is normalized into internal contracts.
2. Features are computed with no lookahead.
3. Regime is classified from deterministic inputs.
4. Strategies propose trade candidates.
5. Portfolio and risk logic resize or reject candidates.
6. Policy guardrails can veto any action.
7. Execution simulates or routes approved intents.
8. Monitoring and journaling preserve evidence and detect failures.
9. Replay and evaluation score behavior before trust increases.

## Module Boundaries

- `market_data`: venue adapters, normalization, data quality checks, replay inputs
- `features`: deterministic feature calculations for strategy and monitoring use
- `regime`: market-state classifiers with explicit supporting metrics
- `signals`: strategy plugins that emit proposals, not orders
- `portfolio`: positions and exposure views
- `risk`: sizing and invariant-based veto logic
- `policy`: operating-mode gates, kill switch, and safety rules
- `execution`: normalization, simulation, reconciliation, idempotency
- `monitoring`: health checks, alerts, anomaly detection
- `events`: shared event envelope, bus interfaces, journal writers
- `evaluation`: replay, backtest, and scorecard generation
- `llm`: strictly advisory analysis and review helpers
- `api`: local control and inspection endpoints
- `cli`: bounded local operator commands

## Technical Posture

- Python 3.11+
- typed contracts with Pydantic
- JSONL and local files first; databases only when justified
- simulation before any live venue interaction
- append-only evidence and replayability from day one

## Current State

The validated baseline now spans Phases 1-10, Validation Tracks 1-5, the paper replay harness, Harness Validation 1-4, the paper-run matrix, Matrix Validation 1-2, Matrix Report Pack, and Matrix Report Validation. The architecture surface above is implemented in simulation-first form, with snapshot-locked replay outputs over scorecards, event counts, review packets, replay-derived operator summaries, harness summaries, harness event-stream views, matrix manifests, replay-derived batch aggregates, and matrix operator reports.
