# Phase L2X — Typed Summary Compatibility Cleanup Plan

## Purpose

This phase decides the compatibility posture between:
- the loose per-request trio
  - `per_request_request_id`
  - `per_request_decision_path`
  - `per_request_result_path`
- the typed summary object
  - `per_request_artifact_summary`

This phase is docs-only.

## Current repo truth

The runtime and session surfaces currently expose both:
- the loose trio
- the typed summary object

Tests already prove:
- valid single-request paths populate both surfaces consistently
- blocked zero-request and multi-request paths leave both surfaces unset

## Decision

Keep the loose trio for compatibility in the near term.

Treat `per_request_artifact_summary` as the preferred operator/runtime consumption surface for new work.

Do not remove the loose trio yet.

## Rationale

This keeps the system bounded and low-risk because:
- existing reads and assertions remain valid
- the typed summary object is already additive and stable
- no migration pressure is required immediately
- no authority or execution behavior changes

## Preferred usage rule

For new code:
- prefer `per_request_artifact_summary` when a typed per-request summary is needed
- use the loose trio only as compatibility mirrors or for legacy reads

## Removal gate

The loose trio should only be considered for removal after all of the following are true:
1. all runtime consumers prefer the typed summary object
2. all tests use the typed summary as the primary asserted surface
3. no operator-facing or downstream surface depends on the loose trio directly
4. a dedicated removal phase is approved

## Out of scope

This phase does not:
- remove fields
- change runtime behavior
- widen live authority
- alter blocked-path handling
- change artifact emission order

## Result

The typed summary object is the preferred forward surface.
The loose trio remains in place as a compatibility mirror until a later bounded removal phase.
