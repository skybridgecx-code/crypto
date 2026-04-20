# Phase L2A — Bounded Live Transmission Scope Lock

## Purpose

This phase defines the smallest acceptable first real live transmission envelope before any code widens authority beyond the current limited-live boundary.

L2A is a scope-lock and design-constraint phase only.

It does not add executable live trading behavior.

## Why L2A exists

The L1 track established the deny-by-default limited-live authority foundation, approval state, launch-window controls, explicit transmission boundary wiring, bounded positive-path authority test coverage, and operator dry-run checklist.

Before any future implementation attempts real live order transmission, the repository needs a tighter scope lock for:
- what exact first transmission path is allowed
- what must still remain denied by default
- what artifacts and controls are authoritative
- what conditions must already be satisfied before implementation can begin

## Current baseline carried forward from L1

The following remain required and authoritative:
- deny-by-default live authority
- explicit bounded approval state
- explicit bounded launch-window state
- explicit transmission boundary wiring
- operator-reviewed launch process
- artifact-first review path
- no implicit widening of execution authority

Nothing in L2A changes those conditions.

## L2A scope

L2A defines the smallest acceptable first real live transmission envelope as:

- one explicitly approved runtime
- one explicitly approved symbol or market path if future implementation requires symbol-level narrowing
- one explicitly approved execution path through the existing limited-live boundary
- one operator-controlled launch window
- one explicit approval artifact chain
- one bounded operator review path before transmission attempt
- one bounded transmission attempt path with deny-by-default behavior outside the approved envelope

## Required assumptions before any future implementation

Any future live transmission implementation must assume all of the following already exist and remain authoritative:

1. approval state is explicit, persisted, and deny-by-default
2. launch-window state is explicit, persisted, and deny-by-default outside the approved window
3. runtime-level operator review remains required
4. transmission authority is bounded to the existing limited-live execution seam
5. review artifacts remain the source of truth for operator go or no-go decisions
6. existing risk, policy, and guardrail decisions remain in force
7. all behavior outside the approved envelope remains denied

## Authoritative controls and artifacts

The following are authoritative for any future live transmission path:

- limited-live authority state
- live approval state
- launch-window state
- live gate artifacts
- live launch verdict artifact
- operator runbook and first-live checklist
- existing execution-boundary wiring already introduced in the limited-live track

No future implementation should bypass these controls with ad hoc flags, hidden fallbacks, or alternate authority paths.

## Smallest acceptable first live transmission envelope

The first acceptable live transmission implementation must be tightly bounded.

Minimum envelope:
- explicit operator-approved run
- explicit launch-window open state
- explicit live approval present
- explicit limited-live enablement present
- explicit boundary path used for transmission
- explicit post-attempt artifact recording
- explicit fail-closed behavior on any missing prerequisite

The first implementation must not attempt to solve broader live-trading workflow needs.

## Deny-by-default requirements that remain mandatory

The following must remain denied by default:
- transmission without explicit live approval
- transmission outside the active launch window
- transmission through any path other than the bounded live transmission seam
- transmission when gate artifacts or verdict artifacts are missing or non-authoritative
- widening from one bounded runtime into general live execution authority
- silent retries or autonomous recovery loops
- hidden operator bypasses
- background scheduling or worker-driven live attempts

## Explicit out of scope for L2A

L2A does not allow:
- executable live order transmission
- multiple venue support expansion
- unattended live operation
- autonomous retry or recovery logic
- new queues, schedulers, workers, or services
- auth, DB, or deployment expansion
- UI control planes for live launch
- strategy rewrites
- risk model rewrites
- exchange-behavior assumptions beyond already documented boundaries
- widening from bounded first transmission into general production live trading

## Future implementation prerequisites

Before any future implementation phase is allowed to add real transmission behavior, it must explicitly scope:
- exact runtime entrypoint
- exact authority checks
- exact artifact prerequisites
- exact denial conditions
- exact operator review flow
- exact post-attempt artifact set
- exact validation strategy
- exact rollback or fail-closed behavior

That future phase must also preserve:
- no silent authority widening
- no hidden live path
- no second control surface
- no second accounting truth
- no bypass of the review artifacts already established

## Operator expectations

Operators should treat L2A as a boundary-setting document only.

Current expected posture:
- limited-live review remains artifact-first
- launch remains operator-mediated
- live transmission remains unimplemented
- any future implementation must arrive as a separate bounded phase
- absence of an implementation phase means live transmission is still out of scope

## Exit criteria for L2A

L2A is complete when:
- the smallest acceptable first live transmission envelope is defined
- deny-by-default conditions are explicitly recorded
- authoritative controls are named
- out-of-scope items are explicit
- no code or authority widening is introduced

## Result

L2A locks the first real live transmission track to the smallest possible future envelope without adding live trading behavior in this phase.
