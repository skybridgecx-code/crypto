# Phase H2C — Operator Command Reference Audit

## Status

Phase H2C audits the operator-facing command references in the frozen docs against the shipped CLI entrypoints and current guard contract.

Conclusion: no command-reference mismatch was found for the shipped single-run, matrix, and sandbox-rehearsal paths.

The only clarity gap is documentation style:
- the forward-runtime preflight and canary examples are intentionally abbreviated with `...`
- they should not be treated as copy-paste-ready commands without the required market-source and supporting flags

This phase is docs-only.
It does not change runtime behavior, CLI behavior, tests, execution authority, or frozen boundaries.

## What was audited

Docs checked:

- `README.md`
- `docs/OPERATOR_SURFACES.md`
- `docs/LIVE_LAUNCH_RUNBOOK.md`
- `docs/PHASE_H1E_SANDBOX_REHEARSAL_OPERATOR_DOCS.md`
- `docs/PHASE_H2A_SHIPPED_VS_BLOCKED_SURFACE_AUDIT.md`
- `docs/PHASE_H2B_GUARD_FLAG_COVERAGE_AUDIT.md`

CLI sources checked:

- `src/crypto_agent/cli/main.py`
- `src/crypto_agent/cli/matrix.py`
- `src/crypto_agent/cli/forward_paper.py`

Guard references checked:

- `src/crypto_agent/runtime/loop.py`
- `src/crypto_agent/runtime/canary.py`

## Command-reference audit result

### 1. Single-run paper command

Documented command:

- `crypto-agent-paper-run tests/fixtures/paper_candles_breakout_long.jsonl --config config/paper.yaml --run-id demo-paper-run`

Audit result:

- aligned with the shipped single-run operator surface
- remains a concrete copy-paste-ready example

### 2. Matrix paper command

Documented command:

- `crypto-agent-paper-matrix-run --config config/paper.yaml --matrix-run-id demo-paper-matrix`

Audit result:

- aligned with the shipped matrix operator surface
- remains a concrete copy-paste-ready example

### 3. Forward-runtime preflight command reference

Documented command reference:

- `crypto-agent-forward-paper-run --preflight-only ...`

Audit result:

- aligned as a workflow reference
- not a complete copy-paste-ready command by itself

Required constraints for a real preflight command:

- `--market-source=binance_spot`
- `--live-symbol <symbol>`
- runtime id and normal forward-runtime context
- preflight remains live-input only
- preflight is not valid on replay input

H2C finding:

- no mismatch
- but this example is intentionally abbreviated and should be treated as a workflow placeholder, not a fully specified command

### 4. Forward-runtime canary command reference

Documented command reference:

- `crypto-agent-forward-paper-run --canary-only --execution-mode shadow ...`

Audit result:

- aligned as a workflow reference
- not a complete copy-paste-ready command by itself

Required constraints for a real canary command:

- `--canary-only`
- `--execution-mode shadow`
- `--market-source=binance_spot`
- `--live-symbol <symbol>`
- runtime id and normal forward-runtime context
- canary applies only to shadow mode with live `binance_spot` input

H2C finding:

- no mismatch
- but this example is intentionally abbreviated and should be treated as a workflow placeholder, not a fully specified command

### 5. Sandbox rehearsal command reference

Documented full command:

- `.venv/bin/crypto-agent-forward-paper-run --config config/paper.yaml --runtime-id <runtime-id> --market-source replay --execution-mode sandbox --allow-execution-mode sandbox --sandbox-fixture-rehearsal tests/fixtures/paper_candles_breakout_long.jsonl`

Audit result:

- aligned with the shipped bounded sandbox rehearsal path
- remains the canonical concrete copy-paste-ready sandbox rehearsal example

Required bounded contract:

- replay fixture input
- `--market-source replay`
- `--execution-mode sandbox`
- `--allow-execution-mode sandbox`
- `--sandbox-fixture-rehearsal`

This path remains sandbox-only evidence generation and does not enable live execution.

## Command-style classification

### Copy-paste-ready examples

- single-run paper example
- matrix paper example
- sandbox fixture rehearsal example

### Workflow placeholders, not complete commands

- preflight reference
- canary reference

These remain valid operator workflow references, but they rely on additional required flags and runtime context.

## Authority and safety posture

This audit does not change the frozen posture:

- `paper`, `shadow`, and `sandbox` remain the only executable modes
- production live execution is not shipped
- live order authority is not shipped
- `live_gate_decision.json` remains artifact-only
- `live_launch_verdict.json` remains artifact-only
- sandbox rehearsal remains separate from the live-market launch workflow

## Result

No command-reference mismatch was found in the frozen operator docs.

The main H2C clarification is that forward-runtime preflight and canary references are workflow shorthand, while the single-run, matrix, and sandbox rehearsal examples are the concrete copy-paste-ready command references.

## Closeout conclusion

Phase H2C confirms the current operator command references are accurate within the frozen contract.

No behavior change is needed.
