# Phase H1E — Sandbox Rehearsal Operator Docs

## Status

Phase H1E is docs-only.

It documents the shipped fixture-backed sandbox CLI rehearsal added in H1D and keeps it clearly separated from the real live-market operator workflow.

## What this path is

The fixture-backed sandbox CLI rehearsal is a deterministic operator rehearsal path for sandbox-only evidence generation.

It exists to prove sandbox request, result, and status artifact generation from a checked-in replay fixture.

## What this path is not

This path is not:

- production live execution
- a live-market preflight
- a shadow canary
- a launch verdict approval flow
- a way to bypass live-market guardrails
- a way to authorize live orders

## Required command

`.venv/bin/crypto-agent-forward-paper-run --config config/paper.yaml --runtime-id <runtime-id> --market-source replay --execution-mode sandbox --allow-execution-mode sandbox --sandbox-fixture-rehearsal tests/fixtures/paper_candles_breakout_long.jsonl`

## Required boundaries

The fixture-backed sandbox rehearsal remains bounded by all of the following:

- replay + sandbox is blocked unless `--sandbox-fixture-rehearsal` is explicitly set
- shadow + replay remains blocked
- the rehearsal uses deterministic checked-in fixtures only
- the execution path remains sandbox-only
- generated execution artifacts must remain `sandbox: true`
- generated venue must remain testnet-scoped
- launch verdict remains artifact-only and non-authoritative

## Expected proof artifacts

A successful rehearsal should produce non-zero sandbox execution artifacts under:

- `runs/<runtime-id>/sessions/session-0001.execution_requests.json`
- `runs/<runtime-id>/sessions/session-0001.execution_results.json`
- `runs/<runtime-id>/sessions/session-0001.execution_status.json`

Expected proof shape:

- `request_count > 0`
- `result_count > 0`
- `status_count > 0`

## Separation from live-market workflow

The normal live-market operator workflow remains:

1. `make phase-start`
2. preflight
3. canary
4. longer bounded shadow evidence
5. gate artifact review
6. launch verdict review
7. `make phase-finish`
8. commit
9. `make phase-close-check`

The fixture-backed sandbox rehearsal does not replace any of those steps.

It is a separate deterministic sandbox evidence path.

## Recommended operator wording

When describing this path, use:

- fixture-backed sandbox rehearsal
- sandbox-only evidence
- deterministic replay rehearsal

Do not describe it as:

- live-ready
- launch-ready
- approved for trading
- live validation

## Closeout conclusion

H1E keeps the sandbox rehearsal path understandable and constrained.

Operators now have clear written guidance for when to use the fixture-backed sandbox rehearsal and when not to use it.
