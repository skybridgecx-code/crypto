# Phase L2E — Bounded Live Adapter Call Wiring

## Status

Phase L2E adds the first actual bounded live adapter invocation at the forward-runtime seam.

This phase remains tightly bounded:
- one request only
- one venue path only
- one symbol only
- no retries
- no new execution mode
- no strategy/risk/accounting widening
- no shadow/sandbox behavior changes

## What changed

- added a bounded live execution adapter protocol and scripted test adapter in:
  - `src/crypto_agent/execution/live_adapter.py`
- extended live transmission models in:
  - `src/crypto_agent/execution/models.py`
  to capture adapter acknowledgment and order-state evidence while preserving fail-closed defaults
- updated runtime seam behavior in:
  - `src/crypto_agent/runtime/loop.py`
  so that when limited-live transmission is authorized:
  1. write live request artifact first
  2. invoke the live adapter only under bounded single-request/single-symbol prerequisites
  3. write live result artifact
  4. write live state artifact

## Fail-closed behavior

The runtime blocks live submission and records bounded `not_submitted` evidence when:

- request count is not exactly one
- bounded live symbol is missing or mismatched
- live execution adapter is not provided

If an adapter error occurs, the runtime records `submission_status: "error"` and a terminal blocked state.

No retry behavior is added.

## Test coverage

Focused updates in `tests/unit/test_forward_paper_live_execution.py` verify:

- authorized bounded path invokes the live adapter exactly once for submit/fetch
- live result/state artifacts capture accepted and terminal state evidence
- shadow and sandbox execution behavior remains unchanged under authorized boundary conditions

## Boundary confirmation

L2E does not add:

- generalized live execution
- a new execution mode
- unattended transmission loops
- approval-granting workflows
- launch-window workflow expansion

## Closeout conclusion

L2E wires a single bounded live adapter call into the existing authorized runtime seam with deterministic artifacting and explicit fail-closed behavior.
