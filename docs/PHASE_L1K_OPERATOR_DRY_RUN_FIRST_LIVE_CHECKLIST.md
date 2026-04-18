# Phase L1K — Operator Dry Run / First Live Checklist

## Status

Phase L1K closes out the current limited-live track with an operator-facing dry-run checklist for the first bounded live attempt.

This phase is docs-only.

It does not:
- enable live order transmission
- add a new execution mode
- change runtime behavior
- change CLI behavior
- widen strategy, risk, or accounting boundaries

## Purpose

The repository now has:

- bounded limited-live authority state
- bounded launch-window state
- bounded approval state
- bounded transmission-decision state
- positive-path authorization coverage
- no executable `limited_live` transmission path

L1K converts the frozen live-review order and bounded L1A-L1J control stack into one operator checklist for a first supervised live attempt in a future explicitly scoped phase.

## Dry-run objective

Before any future real-money attempt, operators must be able to rehearse the full go/no-go workflow without improvisation.

The dry run must prove:

- the operator can inspect artifacts in the correct order
- the second reviewer can confirm preconditions independently
- halt and rollback decisions are obvious
- no artifact is mistaken for executable live authority
- the first attempt stays inside the tiny bounded envelope

## Operator roles

Required participants:

- one primary operator
- one second reviewer

The primary operator owns:
- runtime observation
- readiness state
- manual halt
- checklist execution
- artifact preservation

The second reviewer owns:
- independent artifact review
- explicit go/no-go confirmation before the launch window begins
- explicit stop recommendation on any unclear condition

No single-person launch is allowed.

## First-attempt envelope

The first attempt must remain inside the frozen envelope:

- one runtime only
- one venue path only
- one approved symbol only
- max open positions = 1
- tiny per-symbol max notional only
- manual approval required for every first-launch request
- one short launch window only
- no unattended operation
- no overnight operation

## Required artifact review order

Review artifacts in this exact order:

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

Do not change this order.

## Dry-run go/no-go checklist

Before any future bounded live attempt, confirm all of the following:

### Workflow and verdict

- `live_market_preflight.json.batch_readiness == true`
- `shadow_canary_evaluation.json.state == "pass"`
- `shadow_canary_evaluation.json.reason_codes` is empty
- `live_gate_threshold_summary.json.blocking_passed == true`
- `live_gate_threshold_summary.json.readiness_passed == true`
- `live_gate_decision.json.state == "ready"`
- `live_gate_decision.json.reason_codes` is empty
- `live_launch_verdict.json.verdict == "launchable_here_now"`

### Runtime control state

- `live_control_status.json.go_no_go_action == "go"`
- `live_readiness_status.json.status == "ready"`
- `live_readiness_status.json.limited_live_gate_status == "ready_for_review"`
- `manual_control_state.json.halt_active == false`

### Reconciliation and evidence

- `reconciliation_report.json.status == "clean"`
- `forward_paper_status.json.reconciliation_status == "clean"`
- `forward_paper_status.json.mismatch_detected == false`
- `shadow_evaluation.json.all_shadow_artifacts_present == true`
- `shadow_evaluation.json.request_count >= 1`
- `soak_evaluation.json.completed_session_count >= 3`
- `soak_evaluation.json.executed_session_count >= 2`
- `soak_evaluation.json.failed_session_count == 0`
- `soak_evaluation.json.interrupted_session_count == 0`

### Bounded limited-live state

- limited-live authority artifact exists and is operator-readable
- launch-window artifact exists and reflects the intended bounded window state
- approval-state artifact exists and reflects the intended bounded approval state
- transmission-decision artifact exists and reflects the bounded boundary result
- no artifact is treated as direct live trading permission by itself

If any single check fails, status is `no_go`.

## First-window supervision checklist

Immediately before the window starts:

- primary operator confirms full continuous availability
- second reviewer confirms the artifact review order was followed
- second reviewer confirms the bounded envelope is unchanged
- operator confirms manual halt path is available
- operator confirms readiness can be downgraded immediately
- operator confirms artifact directory path for preservation
- operator confirms no other runtime is active for the attempt

During the window:

- monitor feed health continuously
- monitor reconciliation continuously
- monitor go/no-go action continuously
- monitor manual halt state continuously
- stop immediately on the first unclear or unexpected condition

## Immediate no-go conditions

Treat the attempt as `no_go` immediately if any of the following is true:

- gate state is not `ready`
- launch verdict is not `launchable_here_now`
- readiness is not `ready`
- limited-live gate status is not `ready_for_review`
- manual halt is active
- reconciliation is not clean
- feed health is stale, degraded, or unavailable
- symbol scope widens beyond the approved symbol
- notional scope widens beyond the tiny approved cap
- a request appears without explicit manual approval
- duplicate, rejection, or execution-status behavior is not immediately understood
- any unexpected balance or position mismatch appears

## Rollback checklist

If a halt condition fires, do all of the following in order:

1. set readiness to `not_ready`
2. activate manual halt
3. reduce execution posture back to `paper` or `shadow` only
4. stop new launch attempts
5. preserve the full runtime artifact directory
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

Same-window retry is blocked by default.

## Non-negotiables

- do not treat artifact readiness as live trading permission by itself
- do not widen beyond one symbol, tiny notional, and manual supervision
- do not allow unattended operation
- do not ignore reconciliation drift
- do not improvise a second checklist outside this document and the canonical runbook

## Exit criteria

Phase L1K is complete when:

- one operator-facing dry-run checklist exists
- the checklist matches the canonical runbook and frozen L1A-L1J boundaries
- no runtime or CLI behavior changed
- the repository remains in a clean validated state

## Closeout conclusion

L1K closes the limited-live preparation track with one bounded operator dry-run and first-live checklist.

Any future phase that attempts real live transmission must still be explicitly respecified.
