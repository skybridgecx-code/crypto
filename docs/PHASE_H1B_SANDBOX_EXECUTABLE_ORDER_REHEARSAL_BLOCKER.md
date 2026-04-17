# Phase H1B — Sandbox Executable-Order Rehearsal Blocker

## Status

Phase H1B investigated whether the CLI sandbox path can produce non-zero sandbox execution requests, results, and statuses.

Conclusion: blocked for CLI-level executable-order rehearsal under current safety boundaries.

## Target proof

The intended proof was:

- `execution_mode == "sandbox"`
- `execution_request_count > 0`
- `execution_results.result_count > 0`
- `execution_status.status_count > 0`
- no production live execution
- no live order authority
- no new execution mode
- no strategy/risk rewrite

## H1A evidence

Phase H1A proved the CLI sandbox path can run through the normal runtime and write sandbox execution artifacts.

However, the rehearsal produced zero executable order evidence:

- `proposal_count: 0`
- `order_intent_count: 0`
- `execution_request_count: 0`
- `request_count: 0`

This happened because the live BTCUSDT session produced no executable proposal/order intent.

## Existing non-zero sandbox coverage

The repo already has unit-level sandbox execution coverage using:

- `tests/fixtures/paper_candles_breakout_long.jsonl`
- `run_paper_replay(...)`
- `execute_sandbox_requests(...)`
- `ScriptedSandboxExecutionAdapter`

That path proves sandbox requests, results, and statuses can be generated when an order intent exists.

## CLI blocker

The runtime currently enforces that shadow and sandbox execution modes require `market_source == "binance_spot"`.

That means the existing breakout replay fixture cannot be used directly with CLI sandbox mode.

## Why this remains blocked

Forcing a non-zero CLI sandbox order would require at least one explicitly scoped change:

- loosen replay + sandbox restrictions
- add a fixture-backed sandbox CLI mode
- add live adapter injection through CLI
- add deterministic signal forcing
- change strategy behavior to produce a trade

Those are not safe as an unscoped continuation after G11/H1A.

## Correct future phase

Allowed future phase:

- H1C — Fixture-backed sandbox CLI rehearsal design

H1C must preserve:

- no production live execution
- no live order authority
- no unsafe new execution mode
- no strategy/risk rewrite
- no trusted account-state widening
- deterministic test-fixture inputs only

## Closeout conclusion

H1B does not add code.

The current repo is safe to keep as-is:

- H1A wires CLI sandbox adapter
- unit tests prove non-zero sandbox adapter behavior
- CLI non-zero executable-order rehearsal remains intentionally blocked until explicitly scoped
