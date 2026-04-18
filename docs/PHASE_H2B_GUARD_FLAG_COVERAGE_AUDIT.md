# Phase H2B — Guard and Flag Coverage Audit

## Status

Phase H2B audits the shipped forward-runtime guardrails and operator-facing flag contract against the current docs and tests.

Conclusion: no doc/code mismatch was found in the current bounded contract.

This phase is docs-only.
It does not change runtime behavior, CLI behavior, tests, execution authority, trusted-state boundaries, or live-launch scope.

## What was audited

This audit checked:

- operator-facing docs
- forward-runtime CLI guard behavior
- runtime combination enforcement
- shadow canary applicability rules
- negative-path tests for invalid combinations
- positive-path tests for the bounded sandbox rehearsal carveout

Canonical references:

- `docs/OPERATOR_SURFACES.md`
- `docs/LIVE_LAUNCH_RUNBOOK.md`
- `docs/PHASE_H1B_SANDBOX_EXECUTABLE_ORDER_REHEARSAL_BLOCKER.md`
- `docs/PHASE_H1D_IMPLEMENT_FIXTURE_BACKED_SANDBOX_REHEARSAL.md`
- `docs/PHASE_H1G_SANDBOX_TRACK_CLOSEOUT.md`

Code and test references audited:

- `src/crypto_agent/cli/forward_paper.py`
- `src/crypto_agent/runtime/loop.py`
- `src/crypto_agent/runtime/canary.py`
- `tests/unit/test_runtime_canary.py`
- `tests/unit/test_forward_paper_live_execution.py`

## Shipped forward-runtime contract

Shipped market sources:

- `replay`
- `binance_spot`

Shipped execution modes:

- `paper`
- `shadow`
- `sandbox`

This remains aligned with the operator docs and launch runbook.

## Combination matrix

### Allowed by default

- `replay + paper`
- `binance_spot + paper`
- `binance_spot + shadow`
- `binance_spot + sandbox`

### Allowed only through explicit bounded opt-in

- `replay + sandbox` only when all of the following are true:
  - `--execution-mode sandbox`
  - `--market-source replay`
  - `--allow-execution-mode sandbox`
  - `--sandbox-fixture-rehearsal`
  - checked-in replay fixture input

This path is a deterministic sandbox-only rehearsal surface.
It does not enable live execution.

### Blocked

- `replay + shadow`
- `replay + sandbox` without the explicit sandbox rehearsal carveout
- `--preflight-only` with any market source other than `binance_spot`
- `--canary-only` with any market source other than `binance_spot`
- `--canary-only` with any execution mode other than `shadow`
- `--sandbox-fixture-rehearsal` with any execution mode other than `sandbox`
- `--sandbox-fixture-rehearsal` with any market source other than `replay`
- `--sandbox-fixture-rehearsal` without replay fixture input
- `--sandbox-fixture-rehearsal` combined with `--preflight-only`
- `--sandbox-fixture-rehearsal` combined with `--canary-only`

## Exact CLI guard coverage

The CLI currently enforces all of the following:

- replay source requires replay fixture input
- `binance_spot` source requires `--live-symbol`
- `--preflight-only` requires `--market-source=binance_spot`
- `--preflight-only` and `--canary-only` are mutually exclusive
- `--canary-only` requires `--market-source=binance_spot`
- `--canary-only` requires `--execution-mode=shadow`
- `--sandbox-fixture-rehearsal` requires `--execution-mode=sandbox`
- `--sandbox-fixture-rehearsal` requires `--market-source=replay`
- `--sandbox-fixture-rehearsal` requires replay fixture input
- `--sandbox-fixture-rehearsal` cannot be combined with `--preflight-only`
- `--sandbox-fixture-rehearsal` cannot be combined with `--canary-only`

## Runtime enforcement coverage

The runtime currently enforces that:

- live `binance_spot` input requires symbol, interval, lookback, and stale-feed threshold inputs
- `shadow` and `sandbox` require `market_source == "binance_spot"` by default
- the only shipped carveout is:
  - `execution_mode == "sandbox"`
  - `market_source == "replay"`
  - `sandbox_fixture_rehearsal == true`

There is no shipped carveout for `replay + shadow`.

## Shadow canary applicability

Shadow canary remains narrowly scoped.

It is applicable only when:

- `execution_mode == "shadow"`
- `market_source == "binance_spot"`

For all other combinations, shadow canary is not applicable.

This remains aligned with the launch runbook and operator workflow.

## Sandbox rehearsal coverage

The bounded sandbox rehearsal path is positively covered.

The current shipped path supports:

- deterministic replay fixture input
- replay-source sandbox execution only through explicit opt-in
- non-zero sandbox request/result/status evidence
- sandbox-scoped artifacts
- testnet-scoped venue evidence
- no live execution authority

This remains separate from the live-market launch workflow.

## Artifact authority posture

The current authority posture remains unchanged:

- `live_gate_decision.json` is artifact-only
- `live_launch_verdict.json` is artifact-only
- shadow remains no-transmit evidence only
- sandbox remains sandbox-only evidence only
- production live execution is not shipped
- live order authority is not shipped

## Test coverage checked

Negative-path tests confirm:

- replay+sandbox remains blocked without the fixture rehearsal flag
- replay+shadow remains blocked even when sandbox rehearsal is set
- invalid CLI sandbox rehearsal combinations exit nonzero

Positive-path tests confirm:

- CLI passes the sandbox rehearsal flag through to the runtime
- replay+sandbox with explicit rehearsal opt-in can write non-zero adapter evidence

## Result

No doc/code mismatch was found in the current bounded forward-runtime guard and flag contract.

The shipped operator-facing docs, runtime guards, and current tests all align on the following frozen posture:

- live-market review workflow remains separate from sandbox rehearsal
- replay+sandbox is a narrow explicit rehearsal carveout only
- shadow+replay remains blocked
- launch verdict and gate artifacts remain non-authoritative
- production live trading is not shipped

## Closeout conclusion

Phase H2B confirms the current docs accurately describe the shipped forward-runtime guardrails and opt-in flag behavior.

No behavior change is needed.
