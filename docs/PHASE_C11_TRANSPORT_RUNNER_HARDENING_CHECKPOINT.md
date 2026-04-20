# Phase C11 — Transport Runner Hardening Checkpoint

## Scope

This checkpoint closes the bounded transport runner hardening sequence across C6-C10.

Included scope:
- one-shot local transport runner
- machine-readable step-state artifact
- manual smoke verification guidance
- non-canonical inbound-path failure policy
- operator-facing clarification for pre-canonical failures

Out of scope:
- network transport
- live execution expansion
- auth, DB, queue, or worker additions
- producer-side changes
- polling or watcher behavior
- retry orchestration beyond manual rerun by operator

## Shipped phases

### C6 — one-shot local transport runner
Shipped a deterministic local consumer-side runner that composes the already-landed transport steps in order:
1. pickup
2. boundary response
3. archive

The runner reads one canonical inbound `handoff_request.json`, writes the pickup artifact, writes exactly one boundary response artifact (`ack` or `reject`), archives the attempt bundle, and returns a machine-readable result object.

### C7 — manual smoke and rerun guidance
Verified the shipped runner manually with:
- one known-good local flow
- one known-bad local flow
- rerun behavior after correcting invalid reject metadata

Documented exact expected artifacts and the operator rerun expectation for deterministic partial-progress failures.

### C8 — additive step-state artifact
Added one machine-readable step-state artifact for one-shot local transport runs.

The step-state artifact is written at:

`state/<correlation_id>/<attempt_id>/cryp_transport_run_once_step_state.json`

This artifact records:
- pickup step state
- boundary response step state
- archive step state
- final outcome

The artifact is additive only and does not change core transport behavior.

### C9 — non-canonical inbound-path policy
Pinned non-canonical inbound handoff-path behavior with a focused regression test.

Current pinned behavior:
- the one-shot runner fails with `handoff_request_path_not_inbound_tree`
- no step-state artifact is emitted
- failure occurs before canonical inbound context exists

### C10 — operator-facing clarification
Added a brief operator note clarifying that non-canonical inbound handoff-path failures happen before canonical context exists, so no one-shot step-state artifact is written in that case.

## Current one-shot runner artifact flow

For a canonical inbound handoff request, the current intended flow is:

1. read:
   - `inbound/<correlation_id>/<attempt_id>/handoff_request.json`
2. write pickup receipt:
   - canonical pickup receipt artifact
3. write exactly one boundary response artifact:
   - `ack` or `reject`
4. archive the attempt bundle
5. write one additive step-state artifact
6. return a machine-readable result object

## Step-state artifact behavior

The step-state artifact is intended to improve operator visibility into one-shot runner progress without requiring manual filesystem inspection.

For successful runs, it should show:
- pickup complete
- boundary response complete
- archive complete
- final outcome set

For fail-closed partial-progress cases, it should show:
- completed step states up to the point of failure
- blocked or not-run downstream steps
- final outcome reflecting failure state

The step-state artifact is additive visibility only. It is not a new transport contract and does not expand execution scope.

## Deterministic partial-progress and rerun policy

The runner is intentionally fail-closed.

If a downstream validation failure occurs after pickup is written, partial progress may exist. For example:
- pickup artifact may already exist
- boundary response may be absent
- archive may be absent

Current operator expectation:
- correct the invalid input or metadata
- rerun the one-shot command for the same canonical attempt from the canonical inbound location
- do not treat partial progress as implicit success

This bounded partial-progress behavior is acceptable because it remains deterministic, local-only, and explicit.

## Non-canonical inbound-path failure policy

If the provided handoff request path is non-canonical or outside the inbound tree:
- the runner fails with `handoff_request_path_not_inbound_tree`
- no step-state artifact is emitted
- operators must correct the path and rerun from the canonical inbound location

This is intentional because canonical context is required before the runner can resolve the state artifact location and transport attempt context.

## Current operator expectations

Operators should assume the following:
- one-shot runner is local-only
- one-shot runner does not poll or watch for new work
- one-shot runner does not perform live execution
- exactly one boundary response artifact is expected per run
- step-state artifact is helpful visibility, not a substitute for canonical transport artifacts
- non-canonical path failures must be corrected before rerun
- reruns should use the same canonical attempt when recovering from deterministic partial-progress failures

## Boundary decisions confirmed

The current boundary decisions remain:

- consumer-side local transport only
- deterministic file-based artifacts only
- no producer-side changes in this hardening sequence
- no network transport
- no auth or database integration
- no queue, scheduler, or worker behavior
- no automatic retry loop
- no expansion into live runtime execution

## Result

The C6-C10 sequence leaves the transport runner in a bounded, documented, and operator-verifiable state with:
- a shipped one-shot local runner
- additive step-state visibility
- manual smoke guidance
- pinned pre-canonical failure behavior
- explicit operator expectations for reruns and boundaries
