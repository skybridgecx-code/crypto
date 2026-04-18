# Phase H1G — Sandbox Track Closeout

## Status

Phase H1G closes out the H1 sandbox track.

The sandbox track is now a bounded, shipped operator surface for deterministic sandbox-only evidence and rehearsal.

It does not authorize production live execution.

## What shipped in H1

### H1A
CLI sandbox adapter wiring.

### H1B
Documented why non-zero CLI sandbox executable-order rehearsal was blocked under the original boundaries.

### H1C
Defined the safe design for fixture-backed sandbox CLI rehearsal.

### H1D
Implemented fixture-backed sandbox CLI rehearsal with explicit opt-in and non-zero sandbox request/result/status proof.

### H1E
Documented the operator flow and kept sandbox rehearsal separate from the live-market launch workflow.

### H1F
Hardened negative-path guardrail tests for invalid flag combinations.

## What is now allowed

The repo now supports an explicit deterministic sandbox rehearsal path:

- `--market-source replay`
- `--execution-mode sandbox`
- `--allow-execution-mode sandbox`
- `--sandbox-fixture-rehearsal`
- checked-in replay fixture input

This path is for sandbox-only evidence generation.

## What remains blocked by default

The following remain blocked unless explicitly re-scoped in a future phase:

- replay + sandbox without `--sandbox-fixture-rehearsal`
- shadow + replay
- production live execution
- live order authority
- strategy rewrites
- risk rewrites
- trusted account-state widening
- second accounting system
- hidden launch authority

## Proof now available

The shipped fixture-backed sandbox CLI rehearsal can produce:

- non-zero execution requests
- non-zero execution results
- non-zero execution statuses

And the produced artifacts remain sandbox-scoped:

- `sandbox: true`
- testnet-scoped venue
- artifact-only launch verdict posture

## Separation from live-market workflow

The H1 sandbox track does not replace the frozen live-market workflow from G11.

The live-market workflow remains:

1. preflight
2. canary
3. longer bounded shadow evidence
4. gate review
5. launch verdict review

The sandbox fixture rehearsal is separate and non-authoritative.

## Current operator-safe posture

Safe operator surfaces now include:

- frozen live-market review workflow
- launch verdict artifact and reason-code map
- sandbox CLI rehearsal for deterministic fixture-backed sandbox evidence
- explicit operator docs for when sandbox rehearsal should and should not be used

## Future allowed work

Allowed future work:

- docs polish
- evidence collection
- sandbox-only examples
- bounded bug fixes inside current contract
- additional tests that preserve current boundaries

## Future disallowed work unless explicitly re-scoped

Do not add any of the following without a new explicit phase:

- production live trading
- live order transmission authority
- broader replay/shadow execution loosening
- strategy redesign
- risk/policy redesign
- account-state trust widening
- second accounting system
- silent autonomous execution

## Closeout conclusion

The H1 sandbox track is complete as a bounded operator rehearsal surface.

It is useful, deterministic, auditable, and still clearly separated from live execution authority.
