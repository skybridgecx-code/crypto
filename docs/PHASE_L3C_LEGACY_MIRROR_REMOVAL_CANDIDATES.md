# Phase L3C — Legacy Mirror Removal Candidate Map

## Purpose

Map the safest removal order for the loose per-request mirror fields:
- `per_request_request_id`
- `per_request_decision_path`
- `per_request_result_path`

This phase is docs-only.

## Current posture

Repo truth after L3B:
- typed `per_request_artifact_summary` is the preferred asserted surface
- loose mirror coverage is isolated into dedicated compatibility-focused tests
- model validators still enforce typed-summary/mirror consistency
- runtime/model code still carries loose mirror fields for compatibility

## Candidate removal order

### Candidate 1
`per_request_request_id`

Why it may be easiest:
- duplicated by `per_request_artifact_summary.request_id`
- simpler scalar mirror than path mirrors

Risks:
- session/runtime compatibility checks still use it
- dedicated compatibility tests still pin it

### Candidate 2
`per_request_decision_path`

Why next:
- duplicated by `per_request_artifact_summary.decision_path`

Risks:
- runtime result compatibility surface still exposes it
- compatibility tests still pin it

### Candidate 3
`per_request_result_path`

Why last:
- duplicated by `per_request_artifact_summary.result_path`

Risks:
- runtime result compatibility surface still exposes it
- compatibility tests still pin it

## Required prep before any removal

1. decide whether removal is session-only, runtime-only, or both
2. preserve typed summary as the only source of truth
3. update validators so they no longer require the removed mirror
4. narrow compatibility coverage or replace it with removal-phase assertions
5. confirm no docs still describe the removed mirror as active API surface

## Recommended first removal phase

Recommend a bounded first removal phase targeting only:
- `per_request_request_id`

Reason:
- smallest surface
- least structurally important
- cleanest replacement path through `per_request_artifact_summary.request_id`

## Out of scope

This phase does not:
- remove any field
- change runtime behavior
- widen live authority
- alter typed summary behavior
- change artifact emission order

## Result

Recommended removal order:
1. `per_request_request_id`
2. `per_request_decision_path`
3. `per_request_result_path`

Only proceed through explicit bounded removal phases.

Status update after L3D/L3E:
- runtime/result mirror candidates above are removed from `LiveTransmissionRuntimeResultArtifact`
- session-side `per_request_request_id` mirror is removed
- typed `per_request_artifact_summary` remains the only per-request summary surface on runtime/session artifacts
