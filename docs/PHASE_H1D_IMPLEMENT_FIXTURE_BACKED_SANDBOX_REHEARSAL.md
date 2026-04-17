# Phase H1D — Implement Fixture-Backed Sandbox Rehearsal

## Status

Phase H1D implemented the bounded fixture-backed sandbox CLI rehearsal designed in H1C.

This phase adds an explicit replay+sandbox escape hatch only for deterministic fixture-backed sandbox rehearsal.

## What changed

- Added explicit CLI flag: `--sandbox-fixture-rehearsal`
- Replay + sandbox remains blocked by default
- Replay + sandbox is allowed only when:
  - `--execution-mode sandbox`
  - `--market-source replay`
  - `--sandbox-fixture-rehearsal`
- Shadow + replay remains blocked
- CLI now passes `sandbox_fixture_rehearsal=True` into the runtime
- Runtime synthesizes minimal replay-backed market-state and constraint artifacts only for this explicit sandbox fixture rehearsal path

## Proof command

`.venv/bin/crypto-agent-forward-paper-run --config config/paper.yaml --runtime-id phase-h1d-fixture-sandbox-cli-01 --market-source replay --execution-mode sandbox --allow-execution-mode sandbox --sandbox-fixture-rehearsal tests/fixtures/paper_candles_breakout_long.jsonl`

## Proof result

The CLI command succeeded and wrote non-zero sandbox execution artifacts:

- `session-0001.execution_requests.json.request_count == 1`
- `session-0001.execution_results.json.result_count == 1`
- `session-0001.execution_status.json.status_count == 1`

Observed sandbox evidence:

- `execution_mode: sandbox`
- `sandbox: true` on request/result/status artifacts
- venue: `binance_spot_testnet`
- accepted result written
- filled terminal status written

## Boundary confirmation

H1D does not add:

- production live execution
- live order authority
- new unsafe execution modes
- strategy rewrite
- risk rewrite
- trusted account-state widening
- second accounting system

The launch-verdict workflow remains artifact-only and non-authoritative.
