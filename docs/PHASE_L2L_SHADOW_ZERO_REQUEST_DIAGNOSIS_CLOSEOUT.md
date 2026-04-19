# Phase L2L — Shadow Zero-Request Diagnosis Closeout

## Status

Phase L2L is docs-only.

It does not:
- change runtime code
- change tests
- change execution behavior
- widen strategy, risk, or launch policy scope

## Diagnosis

The first soak runtime produced one `executed` shadow session with zero shadow execution requests because the underlying paper run emitted zero events and zero `ORDER_INTENT_CREATED` records.

This is expected under current semantics:
- `session_outcome: "executed"` means the paper replay completed on healthy live market input
- it does **not** mean at least one proposal or order intent was produced

Therefore, empty shadow request/result/status artifacts for that executed session were produced by design, not by artifact materialization failure.

## Archived Evidence Used

Archive root:
- `/Users/muhammadaatif/crypto-agent-evidence/20260419T102712Z-l2j-runtime-interrupt-hardening`

Primary evidence:
- `runs/first-live-soak-btcusdt-binanceus/sessions/session-0003.json`
- `runs/first-live-soak-btcusdt-binanceus/sessions/session-0003.execution_requests.json`
- `runs/first-live-soak-btcusdt-binanceus/sessions/session-0003.execution_results.json`
- `runs/first-live-soak-btcusdt-binanceus/sessions/session-0003.execution_status.json`
- `journals/first-live-soak-btcusdt-binanceus-session-0003.jsonl` (empty)
- `runs/first-live-soak-btcusdt-binanceus-session-0003/report.md`
- `runs/first-live-soak-btcusdt-binanceus-session-0003/summary.json`
- `runs/first-live-soak-btcusdt-binanceus/soak_evaluation.json`
- `runs/first-live-soak-btcusdt-binanceus/shadow_evaluation.json`
- `runs/first-live-soak-btcusdt-binanceus/live_gate_threshold_summary.json`
- `runs/first-live-soak-btcusdt-binanceus/live_gate_decision.json`

Observed facts from those artifacts:
- session `session-0003` is `executed`
- `execution_request_count` is `0`
- shadow request/result/status artifact counts are all `0`
- operator summary and scorecard show `proposal_count=0`, `order_intent_count=0`, `event_count=0`
- gate remains `not_ready` with `insufficient_shadow_requests` and `insufficient_executed_sessions`

## Code-Path Interpretation

Relevant runtime and shadow paths:
- `src/crypto_agent/runtime/loop.py`
  - marks session outcome `executed` when `run_paper_replay(...)` completes on healthy feed input
  - then builds execution requests from the session journal
- `src/crypto_agent/execution/shadow.py`
  - request artifacts are derived only from `ORDER_INTENT_CREATED` events in the journal
  - if none exist, request/result/status artifacts are valid but empty
- `src/crypto_agent/runtime/shadow_evaluation.py`
  - counts request/result/status artifacts exactly as produced
  - allows executed sessions with zero request counts

## Operational Conclusion

This was a non-firing signal session, not an artifact bug.

Current evidence does not justify a fresh live/shadow retry from this diagnosis alone. Readiness remains correctly blocked until threshold requirements are met through bounded evidence runs.

## Closeout Conclusion

L2L freezes the diagnosis that executed sessions can legitimately produce zero shadow requests under current runtime semantics, and that this condition should be treated as a signal/output fact, not an artifact failure.
