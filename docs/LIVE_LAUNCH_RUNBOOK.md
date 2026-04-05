# Live Launch Runbook

## What Matters

This runbook freezes the operator review order and first-launch constraints for the first tiny live launch under manual supervision.

Current limitation:

- this repository does not yet implement `limited_live` execution
- `paper`, `shadow`, and `sandbox` remain the only executable modes
- `runs/<runtime-id>/live_gate_decision.json` is an artifact-only gate, not executable live authority

This document defines what must be true before any future bounded phase is allowed to widen into a tiny live launch.

## Canonical Review Order

For a candidate runtime `runs/<runtime-id>/`, review artifacts in this order:

1. `live_gate_decision.json`
2. `live_gate_threshold_summary.json`
3. `live_gate_report.md`
4. `soak_evaluation.json`
5. `shadow_evaluation.json`
6. `live_control_status.json`
7. `live_readiness_status.json`
8. `manual_control_state.json`
9. `account_state.json`
10. `reconciliation_report.json`
11. `forward_paper_status.json`
12. `forward_paper_history.jsonl`

Do not review these out of order. The gate decision is only trustworthy when the threshold summary, control status, and reconciliation report all agree.

## Pre-Launch Checks

Before any future tiny live launch is attempted, all of the following must be true:

- `live_gate_decision.json` exists and `state == "ready"`
- `live_gate_threshold_summary.json` exists and both `blocking_passed` and `readiness_passed` are `true`
- `live_gate_decision.json.reason_codes` is empty
- `reconciliation_report.json.status == "clean"`
- `forward_paper_status.json.reconciliation_status == "clean"`
- `forward_paper_status.json.mismatch_detected == false`
- `live_control_status.json.go_no_go_action == "go"`
- `live_readiness_status.json.status == "ready"`
- `live_readiness_status.json.limited_live_gate_status == "ready_for_review"`
- `manual_control_state.json.halt_active == false`
- `shadow_evaluation.json.all_shadow_artifacts_present == true`
- `shadow_evaluation.json.request_count >= 1`
- `soak_evaluation.json.completed_session_count >= 3`
- `soak_evaluation.json.executed_session_count >= 2`
- `soak_evaluation.json.failed_session_count == 0`
- `soak_evaluation.json.interrupted_session_count == 0`

If any one of these checks fails, launch status is `no_go`.

## First-Launch Constraints

These constraints are documentation-only today. A future bounded limited-live phase must enforce them explicitly before any real order authority exists.

- one runtime only
- one allowed symbol only
- restricted symbol allowlist:
  - recommended first symbol: one of the currently validated symbols only
- tiny per-symbol max notional:
  - `per_symbol_max_notional_usd <= 25.0`
- max open positions:
  - `max_open_positions = 1`
- manual approval required:
  - set `manual_approval_above_notional_usd` low enough that every first-launch order requires approval
  - recommended first-launch value: `1.0`
- no unattended operation
- no overnight or background operation
- one launch window only
- halt immediately on the first unexpected condition

## Manual Supervision Requirements

- one named operator must be actively present for the full launch window
- one second reviewer must independently confirm the gate artifacts before launch starts
- the operator must be able to toggle readiness to `not_ready`
- the operator must be able to set manual halt immediately
- the operator must review every control decision before any live-order authority is widened in a future phase
- no launch is allowed if the operator cannot monitor the runtime continuously

## Halt Conditions

Immediately halt and treat the launch as failed if any of the following occurs:

- `live_gate_decision.json.state` is no longer `ready`
- `live_control_status.json.go_no_go_action` becomes `no_go` or `manual_approval_required`
- `manual_control_state.json.halt_active == true`
- `reconciliation_report.json.status != "clean"`
- feed health becomes stale, degraded, or unavailable
- any symbol outside the approved allowlist appears in control or request evidence
- any request exceeds the approved tiny notional cap
- any request appears without explicit manual approval
- any duplicate, rejection, or execution-status behavior is not understood immediately
- any session loss or daily loss cap is breached
- any unexpected position or balance mismatch appears

## Rollback Procedure

If a halt condition fires, do all of the following in order:

1. set operator readiness to `not_ready`
2. activate manual halt
3. reduce execution mode back to `paper` or `shadow` only
4. stop new launch attempts
5. preserve the full runtime artifact directory without cleanup
6. review:
   - `live_gate_decision.json`
   - `live_gate_threshold_summary.json`
   - `live_control_status.json`
   - `manual_control_state.json`
   - `reconciliation_report.json`
   - `forward_paper_history.jsonl`
7. document the no-go reason before any retry

Retries are not allowed in the same launch window unless a new bounded operator decision explicitly approves them.

## Non-Negotiables

- do not treat `ready` gate status as permission to trade live today
- do not widen beyond one symbol, tiny notional, and manual supervision on a first launch
- do not allow unattended operation
- do not ignore reconciliation mismatches or control drift
- do not create a second launch checklist outside this runbook
