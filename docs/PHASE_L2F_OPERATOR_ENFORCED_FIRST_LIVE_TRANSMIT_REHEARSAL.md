# Phase L2F — Operator-Enforced First Live Transmit Rehearsal

## Status

Phase L2F closes the first bounded live-transmission implementation track with an operator-enforced rehearsal checklist for the first real transmitted order.

This phase is docs-only.

It does not:
- widen runtime authority
- change CLI behavior
- change tests
- change strategy, risk, or accounting boundaries

## Purpose

The repository now has:

- bounded live transmission scope lock
- bounded live adapter design
- bounded implementation map
- bounded live request/result/state artifact foundation
- bounded live adapter call wiring

This checklist freezes exactly how operators must prepare for, supervise, and review the first real transmitted order.

## Rehearsal objective

The first live transmit rehearsal must prove all of the following:

- the bounded live transmission prerequisites are reviewed in the correct order
- one operator and one second reviewer can execute the first transmit window without improvisation
- the first transmitted order remains inside the frozen tiny envelope
- stop conditions are obvious and immediate
- post-order artifact review is deterministic

## Required operator roles

- one primary operator
- one second reviewer

The primary operator owns:
- runtime launch execution
- readiness and halt control
- real-time monitoring
- artifact preservation

The second reviewer owns:
- independent pre-window confirmation
- independent stop recommendation on any unclear condition
- post-order artifact review confirmation

No single-person first live transmit attempt is allowed.

## Pre-window checklist

Before the first transmitted order is allowed, confirm all of the following:

### Review workflow

- `live_market_preflight.json.batch_readiness == true`
- `shadow_canary_evaluation.json.state == "pass"`
- `live_gate_threshold_summary.json.blocking_passed == true`
- `live_gate_threshold_summary.json.readiness_passed == true`
- `live_gate_decision.json.state == "ready"`
- `live_launch_verdict.json.verdict == "launchable_here_now"`

### Runtime control state

- limited-live authority is explicitly enabled for the runtime
- launch window is active for the intended bounded session
- active approval exists for the exact intended request
- readiness is `ready`
- limited-live gate status is `ready_for_review`
- manual halt is inactive
- reconciliation is `clean`
- latest live control decision action is `go`

### Bounded live request shape

- exactly one approved symbol
- exactly one request only
- exactly one venue path only
- tiny notional only
- max open positions remains `1`
- no batching
- no parallel request emission

If any one of these checks fails, status is `no_go`.

## In-window operator checklist

During the first live transmit window:

- operator remains continuously present
- second reviewer remains available for stop recommendation
- monitor feed health continuously
- monitor reconciliation continuously
- monitor go/no-go action continuously
- monitor manual halt continuously
- monitor live request/result/state artifacts as they appear
- stop immediately on the first unclear or unexpected condition

## Exact first transmitted order artifact sequence

For the first real transmitted order, operators must confirm this order:

1. bounded live request artifact written
2. bounded live result artifact written
3. bounded live state artifact written

No result artifact is trustworthy if the request artifact is missing.
No state artifact is trustworthy if the result artifact is missing.

## Immediate stop conditions

Immediately halt and treat the rehearsal as failed if any of the following occurs:

- authority is no longer enabled
- launch window is no longer active
- approval is missing, expired, or mismatched
- readiness is no longer `ready`
- limited-live gate status is no longer `ready_for_review`
- manual halt becomes active
- reconciliation is not clean
- feed health is stale, degraded, or unavailable
- symbol scope widens beyond the approved symbol
- request count is not exactly one
- notional exceeds the tiny approved cap
- adapter error occurs
- adapter response is ambiguous
- result/state artifacts do not match the bounded request
- duplicate or unexplained request behavior appears
- any unexpected balance or position mismatch appears

## Post-order artifact review checklist

Immediately after the first transmitted order, review all of the following:

- bounded live request artifact
- bounded live result artifact
- bounded live state artifact
- `live_transmission_decision.json`
- `live_control_status.json`
- `manual_control_state.json`
- `reconciliation_report.json`
- `forward_paper_status.json`
- `forward_paper_history.jsonl`

Confirm:

- exactly one bounded request was emitted
- request symbol matches the approved symbol
- request notional remains inside the approved tiny cap
- result artifact matches the request
- state artifact matches the result
- no duplicate request was emitted
- no retry widened exposure
- reconciliation remains clean
- no unexpected position or balance mismatch appeared

## Rollback procedure

If a stop condition fires, do all of the following in order:

1. set readiness to `not_ready`
2. activate manual halt
3. stop new live transmit attempts
4. preserve the full runtime artifact directory
5. review all request/result/state and reconciliation artifacts
6. document the exact no-go reason before any retry

Same-window retry is blocked by default unless explicitly re-approved by operators.

## Non-negotiables

- do not widen beyond one symbol, one request, one venue path, and tiny notional
- do not allow unattended operation
- do not improvise a second operator checklist outside this document and the canonical runbook
- do not continue after ambiguous execution evidence
- do not continue after reconciliation drift

## Exit criteria

Phase L2F is complete when:

- one operator-enforced first-live-transmit rehearsal checklist exists
- the checklist matches the frozen L2A-L2E bounded envelope
- no runtime or CLI behavior changed
- the repository remains in a clean validated state

## Closeout conclusion

L2F freezes the operator-enforced rehearsal procedure for the first real transmitted order inside the bounded live-transmission envelope.
