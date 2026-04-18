# Phase L2G — First Bounded Live Transmit Evidence Review Closeout

## Status

Phase L2G freezes the required evidence review procedure after the first bounded real transmitted order.

This phase is docs-only.

It does not:
- widen runtime authority
- change CLI behavior
- change tests
- change strategy, risk, or accounting boundaries

## Purpose

L2F froze the operator-enforced rehearsal procedure for the first real transmitted order.

L2G freezes how operators must review the evidence from that first transmitted order before any second live attempt is allowed.

## Review objective

After the first bounded real transmitted order, operators must be able to answer all of the following with evidence:

- was exactly one bounded request emitted
- did the live request stay inside the frozen tiny envelope
- did the adapter result match the request
- did the live order state match the adapter result
- did reconciliation remain clean
- did any unexpected exposure, retry, duplicate, or mismatch appear

If any one of these cannot be answered clearly, status is `no_go` for any second attempt.

## Required artifact review set

Review all of the following artifacts together:

1. bounded live request artifact
2. bounded live result artifact
3. bounded live state artifact
4. `live_transmission_decision.json`
5. `live_control_status.json`
6. `manual_control_state.json`
7. `reconciliation_report.json`
8. `forward_paper_status.json`
9. `forward_paper_history.jsonl`

Do not review these selectively.

## Evidence checklist

Confirm all of the following:

### Request evidence

- exactly one request was emitted
- request symbol matches the approved symbol
- request side matches the approved request
- request quantity and estimated notional remain inside the approved tiny cap
- request references the correct authority / approval / launch-window / transmission-decision artifacts

### Result evidence

- result artifact exists
- result request id matches the request artifact
- result client order id matches the request artifact
- venue identifier matches the approved venue path
- adapter result is operator-readable
- no duplicate submission evidence appears
- no implicit retry evidence appears

### State evidence

- state artifact exists
- state request id matches the request/result artifacts
- state client order id matches the request/result artifacts
- state is operator-readable
- terminal / non-terminal meaning is clear
- any fill quantity and price are understandable
- no ambiguous order-state transition appears

### Runtime evidence

- transmission decision remained bounded and explicit
- go/no-go control state remained valid through the attempt
- manual halt was not silently triggered
- reconciliation remained clean
- no unexpected position or balance mismatch appeared
- forward runtime history is consistent with the request/result/state artifacts

## Automatic no-go findings

Treat the first transmit attempt as `no_go` for any follow-up live attempt if any of the following appears:

- more than one request emitted
- request symbol mismatch
- request notional breach
- venue mismatch
- duplicate request evidence
- retry evidence not explicitly approved
- missing result artifact
- missing state artifact
- result/state mismatch
- ambiguous order state
- unexpected rejection
- unexplained adapter error
- reconciliation drift
- unexpected balance or position mismatch
- unclear runtime history around the transmitted order

## Required closeout record

Before any second live attempt is allowed, operators must document:

- whether the first transmitted order stayed inside the bounded envelope
- whether request/result/state artifacts matched cleanly
- whether reconciliation remained clean
- whether any stop condition fired
- exact reason for pass or no-go
- whether the same envelope is still safe for a second bounded attempt

## Second-attempt rule

A second live attempt is blocked by default.

It is only allowed if:

- the full evidence checklist passed
- no automatic no-go finding appeared
- both operator and second reviewer sign off on the evidence
- the bounded envelope remains unchanged

## Non-negotiables

- do not allow a second live attempt on unclear evidence
- do not normalize away duplicate or retry behavior
- do not ignore reconciliation drift
- do not widen symbol, venue, or notional scope based on one successful attempt
- do not create a second evidence-review process outside this document

## Exit criteria

Phase L2G is complete when:

- one bounded evidence-review closeout document exists
- the document defines pass / fail / no-go evidence for the first transmitted order
- no runtime or CLI behavior changed
- the repository remains in a clean validated state

## Closeout conclusion

L2G freezes the evidence-review closeout procedure required after the first bounded real transmitted order.

Any second live attempt remains blocked until this review is completed and explicitly passed.
