# Phase L1F — Live approval foundation

## Status

Phase L1F adds the typed live-approval artifact foundation required before any bounded limited-live transmission path can even be considered.

## What changed

- added typed live approval models:
  - `LiveApprovalRecord`
  - `LiveApprovalStateArtifact`
- wired runtime path, status, result, and registry surfaces to include `live_approval_state_path`
- initialized `live_approval_state.json` at runtime startup with:
  - zero approvals
  - approval required for live transmission
  - deny-by-default reason codes
- extended the limited-live transmission decision artifact so it includes `approval_state_path`
- updated limited-live transmission evaluation to deny when no active live approval exists
- added focused tests proving the approval artifact exists, defaults to zero approvals, and does not weaken deny-by-default behavior

## Boundary confirmation

L1F does not add:

- live order transmission
- real execution authority
- approval-granting workflows
- launch-window activation logic
- strategy or risk redesign
- accounting or trusted-state widening

## Closeout conclusion

L1F completes the minimum typed approval-state foundation while keeping limited-live transmission explicitly denied by default.
