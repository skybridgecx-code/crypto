# Phase L2K — Orphaned Forward Runtime Operator Closeout

## Status

Phase L2K is docs-only.

It does not:
- change runtime code
- change tests
- change execution behavior
- widen strategy, risk, or launch policy scope

## What happened

During the second bounded shadow soak (`first-live-soak-btcusdt-binanceus-r2`), runtime evidence showed an orphaned running state:

- `forward_paper_status.json` stayed `status: running` with zero completed sessions
- `forward_paper_history.jsonl` recorded only `session.started` for `session-0001`
- `sessions/session-0001.json` remained `status: running` without completion metadata
- no matching forward-paper process remained alive

This produced an operator-visible mismatch between persisted runtime state and actual process liveness.

## What L2J fixed

Phase L2J hardened interrupt-like exits:

- `KeyboardInterrupt` and `SystemExit` now persist interrupted session/runtime state before re-raising
- restart-safe behavior remains deterministic and file-backed
- next-invocation recovery remains the canonical recovery path for persisted interrupted state

## What remains intentionally not recoverable in-process

Hard kills (for example `SIGKILL`) are still not recoverable in-process.

That limit is intentional:
- there is no in-process signal handling path for a hard kill
- evidence must be preserved and assessed from persisted artifacts
- any further hardening must be separately scoped as a bounded durability phase

## Operator decision after L2J

Current evidence does not support another fresh live/shadow retry yet.

Reason:
- L2J addressed interrupt-like persistence durability
- hard-kill behavior remains a known boundary
- no new bounded evidence phase has yet revalidated launchability end-to-end after the orphaned r2 incident

## Bounded operator procedure for orphaned runtimes

When a runtime appears stuck in `running`:

1. Preserve evidence first. Do not delete or rewrite runtime artifacts.
2. Confirm whether a matching process is alive.
3. Inspect:
   - `runs/<runtime-id>/forward_paper_status.json`
   - `runs/<runtime-id>/forward_paper_history.jsonl`
   - `runs/<runtime-id>/sessions/session-<nnnn>.json`
4. If the process is gone, treat the runtime as interrupted and rely on next-invocation recovery for restart-safe cases.
5. If evidence shows a real shutdown durability gap, open a bounded hardening phase before any further launch decision.
6. Do not re-run live/shadow solely to "unstick" persisted running state.

## Closeout conclusion

L2K freezes the operator handling contract for orphaned forward runtimes after L2J:
- preserve evidence
- verify liveness explicitly
- trust bounded recovery paths
- escalate only via a scoped durability phase
- no retry-by-default behavior
