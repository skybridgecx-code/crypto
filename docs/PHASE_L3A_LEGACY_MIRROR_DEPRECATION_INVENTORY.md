# Phase L3A — Legacy Mirror Deprecation Inventory

## Purpose

Inventory every remaining direct dependency on the loose per-request mirror fields:
- `per_request_request_id`
- `per_request_decision_path`
- `per_request_result_path`

This phase is docs-only.

## Current posture

Repo truth after L2V-L2Z:
- typed `per_request_artifact_summary` exists on the relevant runtime/session surfaces
- the loose trio still exists as compatibility mirrors
- typed summary consistency is now validated at the model boundary

## Inventory

### Runtime/model definitions

1. `src/crypto_agent/runtime/models.py`
   - `ForwardPaperSessionSummary`
     - `per_request_request_id`
   - `LiveTransmissionRuntimeResultArtifact`
     - `per_request_request_id`
     - `per_request_decision_path`
     - `per_request_result_path`

### Runtime/model validation and mirror wiring

2. `src/crypto_agent/runtime/models.py`
   - model validators still explicitly validate the loose fields against the typed summary

3. `src/crypto_agent/runtime/loop.py`
   - runtime live transmission result still writes the loose trio as compatibility mirrors
   - session summary helper still writes `per_request_request_id` as a compatibility mirror

### Test dependencies

4. `tests/unit/test_forward_paper_live_execution.py`
   - happy-path assertions still directly assert:
     - `runtime_transmission_result.per_request_request_id`
     - `runtime_transmission_result.per_request_decision_path`
     - `runtime_transmission_result.per_request_result_path`
     - `session.per_request_request_id`
   - blocked-path assertions still directly assert the loose trio is unset
   - validator mismatch fixtures still construct objects using the loose trio directly

### Documentation references

5. `docs/PHASE_L2X_TYPED_SUMMARY_COMPATIBILITY_PLAN.md`
   - explicitly documents the loose trio as part of the current compatibility posture

## Categorization

### Primary dependency
None identified from this inventory pass.

### Compatibility mirror
- `src/crypto_agent/runtime/models.py`
- `src/crypto_agent/runtime/loop.py`

### Test-only compatibility assertion
- `tests/unit/test_forward_paper_live_execution.py`

### Documentation/reference only
- `docs/PHASE_L2X_TYPED_SUMMARY_COMPATIBILITY_PLAN.md`

## Removal readiness criteria

A future removal phase should require:
1. no runtime/model compatibility mirror is still needed
2. typed summary is the only primary consumption surface
3. tests no longer require direct loose-trio assertions except in dedicated backward-compat coverage, if intentionally retained
4. documentation is updated to remove or explicitly retire the loose trio
5. a bounded removal phase is explicitly approved

## Recommendation

Default recommendation:
- keep the loose trio for now
- treat it as compatibility-only
- avoid adding any new direct dependency on the loose trio
- prefer `per_request_artifact_summary` for all new work
- plan a later bounded removal phase only after test and model consumers are fully reduced

## Status update after L3D/L3E

Current repo truth:
- session-side `per_request_request_id` mirror is removed
- runtime-side loose trio (`per_request_request_id`, `per_request_decision_path`, `per_request_result_path`) is removed from `LiveTransmissionRuntimeResultArtifact`
- runtime loop no longer writes those runtime loose mirrors
- typed `per_request_artifact_summary` remains the asserted source-of-truth summary surface
