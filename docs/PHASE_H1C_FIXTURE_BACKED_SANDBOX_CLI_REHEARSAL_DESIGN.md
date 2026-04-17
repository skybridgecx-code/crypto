# Phase H1C — Fixture-Backed Sandbox CLI Rehearsal Design

## Status

Phase H1C is design-only.

It defines the safest possible shape for a future fixture-backed sandbox CLI rehearsal without weakening the existing live-market guardrails.

No code is added in this phase.

## Problem

H1A proved the CLI sandbox path can run through the normal runtime after wiring an explicit sandbox adapter.

H1B showed that a CLI-level non-zero sandbox executable-order rehearsal remains blocked because:

- sandbox and shadow runtime modes currently require `market_source == "binance_spot"`
- existing deterministic breakout fixtures can produce order intents
- those fixtures are replay inputs
- replay inputs cannot currently be used with CLI sandbox mode

## Design goal

Enable a future bounded rehearsal that proves:

- `execution_mode == "sandbox"`
- `execution_request_count > 0`
- `execution_results.result_count > 0`
- `execution_status.status_count > 0`
- sandbox acknowledgements and statuses are written
- no production live execution is possible
- no live order authority is granted

## Non-goals

This design does not authorize:

- production live trading
- live order transmission
- loosening live `binance_spot` launch workflow guardrails
- strategy rewrites
- risk rewrites
- trusted account-state widening
- second accounting system
- silent automatic actions

## Recommended design

Add a future explicit CLI flag for deterministic fixture-backed sandbox rehearsal.

Preferred shape:

- `crypto-agent-forward-paper-run`
- `--config config/paper.yaml`
- `--runtime-id <runtime-id>`
- `--market-source replay`
- `--execution-mode sandbox`
- `--allow-execution-mode sandbox`
- `--sandbox-fixture-rehearsal`
- `tests/fixtures/paper_candles_breakout_long.jsonl`

The new flag should be required. Replay plus sandbox should remain blocked unless this explicit rehearsal flag is present.

## Safety rule

The existing guard should not be generally removed.

Current behavior:

- shadow and sandbox require `market_source == "binance_spot"`

Future behavior should become:

- shadow and sandbox require `market_source == "binance_spot"`
- OR sandbox plus replay is allowed only when `--sandbox-fixture-rehearsal` is explicitly set

Shadow plus replay should remain blocked unless separately scoped.

## Runtime constraints

Fixture-backed sandbox rehearsal must:

- use only checked-in deterministic fixtures
- use the existing `ScriptedSandboxExecutionAdapter`
- write normal sandbox execution artifacts
- mark all artifacts as sandbox and test-fixture evidence
- refuse live symbols and base URLs when fixture rehearsal is active
- refuse `--preflight-only`
- refuse `--canary-only`
- refuse execution modes other than sandbox
- keep `execution_authority == "none"` in launch verdict
- keep final launch verdict non-authoritative

## Suggested artifact marker

Future implementation should add a clear marker to runtime output or status if fixture rehearsal is active, for example:

- `fixture_backed_sandbox_rehearsal: true`
- `execution_authority: none`

If adding this requires schema changes, that should be scoped explicitly in the implementation phase.

## Expected fixture

Use:

- `tests/fixtures/paper_candles_breakout_long.jsonl`

Existing tests show this fixture can produce a proposal and order intent through paper replay.

## Expected proof

The future implementation phase should prove:

- command exits successfully
- `session.execution_mode == "sandbox"`
- `session.execution_request_count > 0`
- `session.execution_terminal_count > 0`
- `session-0001.execution_requests.json.request_count > 0`
- `session-0001.execution_results.json.result_count > 0`
- `session-0001.execution_status.json.status_count > 0`
- all generated execution artifacts have `sandbox: true`
- no production venue is used
- no live order transmission path is invoked

## Testing requirements for future implementation

Add focused tests for:

1. Replay plus sandbox without `--sandbox-fixture-rehearsal` remains blocked.
2. Replay plus sandbox with `--sandbox-fixture-rehearsal` succeeds.
3. Shadow plus replay remains blocked.
4. Fixture-backed sandbox writes non-zero request, result, and status artifacts.
5. CLI output includes enough paths to inspect generated artifacts.
6. Launch verdict remains artifact-only and non-authoritative.

## Recommended future phase

Implementation should be a separate phase:

- H1D — Implement fixture-backed sandbox CLI rehearsal

H1D should remain bounded to CLI and runtime guard handling, deterministic fixture rehearsal, tests, and docs.

## Closeout conclusion

H1C does not add code.

The safe path is to preserve existing live-market guardrails and add only an explicit fixture-backed sandbox rehearsal escape hatch in a future implementation phase.
