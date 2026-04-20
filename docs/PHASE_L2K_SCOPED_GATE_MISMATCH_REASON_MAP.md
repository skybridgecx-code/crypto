# Phase L2K — Scoped Gate Mismatch Reason Map

## Purpose

This phase documents the operator-facing meaning of scoped rehearsal gate mismatch reasons emitted by the bounded live transmission artifact path.

This phase is docs-only.

It does not add executable live trading behavior.

## Scope

This document applies only to fail-closed scoped rehearsal gate diagnostics inside the bounded live transmission chain.

These reasons are:
- operator-readable
- fail-closed
- non-authoritative
- bounded to the reviewed live transmission seam

## Non-authority rule

Scoped gate mismatch reasons do not grant live authority.

They do not replace:
- limited-live authority state
- launch-window state
- live approval state
- readiness state
- reconciliation cleanliness
- manual halt state
- live control go/no-go decision

A matched scoped gate is still insufficient by itself. The full bounded authority chain must also pass.

## Required interpretation

All scoped gate mismatch reasons must be interpreted as `no_go` until corrected and re-evaluated through the same bounded review flow.

Do not treat any mismatch reason as a soft warning.

## Reason map

### missing_scoped_rehearsal_gate

Meaning:
- no scoped rehearsal gate was present for the bounded attempt

Operator action:
1. stop the attempt
2. confirm the intended runtime/session/request tuple
3. create or load the correct scoped gate values
4. rerun only through the same bounded seam

### scoped_rehearsal_gate_runtime_mismatch

Meaning:
- the gate `runtime_id` does not match the current bounded runtime

Operator action:
1. stop the attempt
2. verify the intended runtime id
3. correct the gate runtime value
4. rerun only through the same bounded seam

### scoped_rehearsal_gate_session_mismatch

Meaning:
- the gate `session_id` does not match the current bounded session

Operator action:
1. stop the attempt
2. verify the intended session id
3. correct the gate session value
4. rerun only through the same bounded seam

### scoped_rehearsal_gate_request_mismatch

Meaning:
- the gate `request_id` does not match the current bounded request identity

Operator action:
1. stop the attempt
2. verify the intended request id
3. correct the gate request value
4. rerun only through the same bounded seam

### scoped_rehearsal_gate_scope_not_single_request

Meaning:
- the gate scope is outside the bounded single-request contract

Operator action:
1. stop the attempt
2. revert to the bounded single-request scope
3. confirm the exact request identity
4. rerun only through the same bounded seam

## Fail-closed handling rule

If any scoped gate mismatch reason appears:
- transmission remains blocked
- no alternate transmission path is allowed
- no retry loop is allowed
- no operator bypass is allowed
- correction must happen inside the same bounded review flow

## Operator expectation

Operators should treat the mismatch reasons as:
- bounded diagnostics
- exact identity mismatch indicators
- review inputs for correction
- not as workflow shortcuts or permissions

## Result

Scoped gate mismatch reasons are fail-closed bounded diagnostics for the live transmission artifact path and must never be interpreted as authority-granting signals.
