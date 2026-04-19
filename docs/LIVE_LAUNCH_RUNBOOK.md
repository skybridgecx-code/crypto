# Live Launch Runbook

## What Matters

This runbook freezes the operator review order and first-launch constraints for the first tiny live launch under manual supervision.

Current limitation:

- this repository does not yet implement `limited_live` execution
- `paper`, `shadow`, and `sandbox` remain the only executable modes
- `runs/<runtime-id>/live_gate_decision.json` is an artifact-only gate, not executable live authority
- `runs/<runtime-id>/live_launch_verdict.json` is an artifact-only operator verdict, not executable live authority

This document defines what must be true before any future bounded phase is allowed to widen into a tiny live launch.

## Canonical Review Order

For a candidate runtime `runs/<runtime-id>/`, review artifacts in this order:

1. `live_market_preflight.json`
2. `shadow_canary_evaluation.json`
3. `live_gate_threshold_summary.json`
4. `live_gate_decision.json`
5. `live_launch_verdict.json`
6. `live_gate_report.md`
7. `soak_evaluation.json`
8. `shadow_evaluation.json`
9. `live_control_status.json`
10. `live_readiness_status.json`
11. `manual_control_state.json`
12. `account_state.json`
13. `reconciliation_report.json`
14. `forward_paper_status.json`
15. `forward_paper_history.jsonl`

Do not review these out of order. The gate decision is only trustworthy when the preflight and canary were passable first, and when the threshold summary, control status, and reconciliation report all agree.

## Canonical Launchability Sequence

For a new environment or host path, use this sequence:

1. run the live-market preflight probe
2. stop immediately if `live_market_preflight.json.batch_readiness != true`
3. run a bounded shadow canary
4. stop immediately if `shadow_canary_evaluation.json.state != "pass"`
5. run the longer bounded shadow evidence set
6. review the gate and readiness artifacts
7. require `live_launch_verdict.json.verdict == "launchable_here_now"` before proposing any future limited-live review phase

Do not skip from preflight directly to a long shadow evidence run.
Do not continue past a failed preflight or failed canary unless you are doing an explicit bounded rehearsal to inspect downstream artifact consistency.

## Pre-Launch Checks

Before any future tiny live launch is attempted, all of the following must be true:

- `live_launch_verdict.json` exists and `verdict == "launchable_here_now"`
- `live_gate_decision.json` exists and `state == "ready"`
- `live_market_preflight.json` exists and `batch_readiness == true`
- `shadow_canary_evaluation.json` exists and `state == "pass"`
- `shadow_canary_evaluation.json.reason_codes` is empty
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

Operator interpretation note for shadow sessions:
- an `executed` shadow session can still produce `request_count == 0` when the underlying paper run emits no proposals or `ORDER_INTENT_CREATED`
- treat this as a non-firing signal session, not an artifact bug
- readiness remains blocked until shadow request thresholds are met

For a launch-review rehearsal, set operator readiness intentionally:

- `live_readiness_status.json.status == "ready"`
- `live_readiness_status.json.limited_live_gate_status == "ready_for_review"`

If `limited_live_gate_status` remains `not_ready`, `live_launch_verdict.json` should remain `not_launchable_here_now` even when market availability improves. That is an operator hold, not a venue-readiness signal.

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
   - `live_market_preflight.json`
   - `shadow_canary_evaluation.json`
   - `live_launch_verdict.json`
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

## Orphaned Runtime Handling

If a forward runtime is persisted as `running` but no process is alive:

1. preserve the runtime evidence directory as-is
2. verify process liveness explicitly before taking any action
3. inspect `forward_paper_status.json`, `forward_paper_history.jsonl`, and session summary artifacts
4. use next-invocation recovery for restart-safe interrupted cases
5. open a bounded hardening phase if evidence shows a real shutdown durability gap
6. do not run live/shadow again just to "unstick" runtime state

This is an operator diagnostics and durability boundary, not a launch override.

## Launch verdict reason-code map

Use `docs/LAUNCH_VERDICT_REASON_CODES.md` when reviewing `live_launch_verdict.json.reason_codes`.

If the verdict is `not_launchable_here_now`, stop and resolve the mapped upstream artifact issue before rerunning from the correct workflow step. Do not manually override the verdict.

## Fixture-backed sandbox rehearsal is separate

The H1D fixture-backed sandbox CLI rehearsal is not part of the live-market launch workflow.

Do not substitute fixture-backed sandbox rehearsal for:
- live-market preflight
- shadow canary
- bounded shadow evidence
- live gate review
- launch verdict review

See:
- `docs/PHASE_H1E_SANDBOX_REHEARSAL_OPERATOR_DOCS.md`
