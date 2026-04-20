# Phase L2I — Scoped Rehearsal Gate Operator Contract

## Purpose

This phase documents the operator-facing contract for the scoped first-live rehearsal gate added in L2H.

This phase is docs-only.

It does not add executable live trading behavior.

## Contract summary

The bounded live adapter seam must remain fail-closed unless the scoped rehearsal gate matches the intended bounded launch context.

The scoped gate is operator-enforced and must match the bounded runtime context before the seam can proceed.

## Required scoped gate fields

The scoped rehearsal gate must be defined with:

- `runtime_id`
- `session_id`
- `request_id`

These values are the operator-reviewed identity tuple for the bounded first-live rehearsal attempt.

## Matching rule

The rehearsal gate is valid only when all required scoped fields match the current bounded launch context.

Required matching posture:
- runtime must match exactly
- session must match exactly
- request must match exactly unless the bounded implementation explicitly uses the existing `single_request` scope token in the shipped contract

If the scope does not match, the bounded live adapter seam must remain blocked.

## Fail-closed operator expectation

Operators must assume:

- missing scoped gate means `no_go`
- partially filled scoped gate means `no_go`
- stale scoped gate means `no_go`
- mismatched runtime/session/request values mean `no_go`
- a scoped gate never grants general live authority
- a scoped gate only applies to the bounded reviewed launch context

## Mismatch handling

If scoped gate matching fails, operators should treat the result as a bounded contract mismatch, not as a recoverable soft warning.

Expected handling:
1. stop the attempt
2. review the scoped gate values
3. confirm the intended runtime/session/request identity
4. correct the gate values if the attempt should proceed
5. rerun only through the same bounded seam and review flow

Do not bypass the mismatch with manual assumptions.

## Reason handling expectation

Mismatch or absence should be reflected as a fail-closed bounded result in runtime transmission artifacts.

Operator interpretation:
- gate not present: blocked by missing scoped rehearsal gate
- gate present but mismatched: blocked by scoped gate mismatch
- gate present and matched: still not sufficient by itself; the full bounded authority chain must also pass

## Non-authority rule

The scoped rehearsal gate is not an independent authority surface.

It does not replace:
- limited-live authority state
- launch-window state
- approval state
- reconciliation cleanliness
- readiness state
- manual halt state
- live control go/no-go decision

All other bounded controls remain required.

## Out of scope

This contract does not authorize:
- wildcard gate widening
- multi-request broadening
- multi-session broadening
- multi-runtime broadening
- alternate transmission paths
- retries outside the bounded reviewed flow
- unattended live operation

## Result

The scoped rehearsal gate must be interpreted as one fail-closed operator-reviewed identity check inside the existing bounded live transmission chain, not as a general live-trading permission surface.
