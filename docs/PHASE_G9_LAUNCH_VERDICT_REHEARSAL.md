# Phase G9 Launch Verdict Rehearsal

## What Matters

This rehearsal tested the operator workflow for reviewing `runs/<runtime-id>/live_launch_verdict.json` using the current bounded forward-runtime path on this host.

No code changes were required. The rehearsal exposed operator-facing clarification needs only.

## Runtime Id Used

- `phase-g9-launch-verdict-rehearsal-btcusdt-01`

## Operator Order Rehearsed

Target operator order:

1. preflight
2. canary
3. bounded shadow evidence
4. gate artifacts
5. `live_launch_verdict.json` review

Observed result on this host:

- step 1 already returned a no-go condition
- steps 2-5 were still run for rehearsal completeness only
- in real operator use, the workflow should have stopped after step 1

## Exact Commands Run

Command 1: preflight probe

```bash
.venv/bin/crypto-agent-forward-paper-run \
  --config config/paper.yaml \
  --runtime-id phase-g9-launch-verdict-rehearsal-btcusdt-01 \
  --market-source binance_spot \
  --live-symbol BTCUSDT \
  --live-interval 1m \
  --live-lookback-candles 8 \
  --feed-stale-after-seconds 120 \
  --execution-mode shadow \
  --live-market-poll-retry-count 2 \
  --live-market-poll-retry-delay-seconds 2.0 \
  --preflight-only
```

- exit code: `1`

Command 2: shadow canary

```bash
.venv/bin/crypto-agent-forward-paper-run \
  --config config/paper.yaml \
  --runtime-id phase-g9-launch-verdict-rehearsal-btcusdt-01 \
  --market-source binance_spot \
  --live-symbol BTCUSDT \
  --live-interval 1m \
  --live-lookback-candles 8 \
  --feed-stale-after-seconds 120 \
  --execution-mode shadow \
  --session-interval-seconds 60 \
  --max-sessions 2 \
  --live-market-poll-retry-count 2 \
  --live-market-poll-retry-delay-seconds 2.0 \
  --canary-only
```

- exit code: `1`

Command 3: bounded shadow evidence

```bash
.venv/bin/crypto-agent-forward-paper-run \
  --config config/paper.yaml \
  --runtime-id phase-g9-launch-verdict-rehearsal-btcusdt-01 \
  --market-source binance_spot \
  --live-symbol BTCUSDT \
  --live-interval 1m \
  --live-lookback-candles 8 \
  --feed-stale-after-seconds 120 \
  --execution-mode shadow \
  --session-interval-seconds 60 \
  --max-sessions 3 \
  --live-market-poll-retry-count 2 \
  --live-market-poll-retry-delay-seconds 2.0
```

- exit code: `0`

## Generated Artifact List

Generated under `runs/phase-g9-launch-verdict-rehearsal-btcusdt-01/`:

- `account_state.json`
- `forward_paper_history.jsonl`
- `forward_paper_status.json`
- `live_control_config.json`
- `live_control_status.json`
- `live_gate_decision.json`
- `live_gate_report.md`
- `live_gate_threshold_summary.json`
- `live_launch_verdict.json`
- `live_market_preflight.json`
- `live_readiness_status.json`
- `manual_control_state.json`
- `reconciliation_report.json`
- `recovery_status.json`
- `shadow_canary_evaluation.json`
- `shadow_evaluation.json`
- `soak_evaluation.json`
- `sessions/session-0001.json`
- `sessions/session-0001.skip_evidence.json`
- `sessions/session-0002.json`
- `sessions/session-0002.skip_evidence.json`
- `sessions/session-0003.json`
- `sessions/session-0003.skip_evidence.json`

Not materialized because all sessions skipped unavailable feed:

- `live_market_status.json`
- `venue_constraints.json`
- execution request/result/status artifacts

## Upstream Artifact Summary

Preflight:

- `status == "retries_exhausted"`
- `batch_readiness == false`
- `batch_readiness_reason == "retries_exhausted"`
- `feed_health_message` reported `HTTP Error 451`

Canary:

- `state == "fail"`
- `reason_codes == ["unavailable_feed_sessions_present", "not_all_sessions_executed"]`
- `executed_session_count == 0`
- `skipped_unavailable_feed_session_count == 3`

Gate threshold summary:

- `blocking_passed == true`
- `readiness_passed == false`
- readiness failures:
  - `limited_live_gate_not_ready_for_review`
  - `insufficient_executed_sessions`
  - `insufficient_shadow_requests`

Gate decision:

- `state == "not_ready"`
- `reason_codes == ["limited_live_gate_not_ready_for_review", "insufficient_executed_sessions", "insufficient_shadow_requests"]`

Readiness status:

- `status == "ready"`
- `limited_live_gate_status == "not_ready"`

## Live Launch Verdict

Artifact:

- `runs/phase-g9-launch-verdict-rehearsal-btcusdt-01/live_launch_verdict.json`

Verdict:

- `verdict == "not_launchable_here_now"`

Reason codes:

- `preflight_not_batch_ready`
- `preflight_status_retries_exhausted`
- `preflight_reason_retries_exhausted`
- `shadow_canary_not_passed`
- `unavailable_feed_sessions_present`
- `not_all_sessions_executed`
- `live_gate_readiness_thresholds_not_passed`
- `limited_live_gate_not_ready_for_review`
- `insufficient_executed_sessions`
- `insufficient_shadow_requests`
- `live_gate_state_not_ready`

Checks:

- `preflight_batch_ready == false`
- `shadow_canary_passed == false`
- `blocking_thresholds_passed == true`
- `readiness_thresholds_passed == false`
- `live_gate_ready == false`
- `operator_readiness_ready == true`
- `limited_live_gate_ready_for_review == false`

## Did The Verdict Match Upstream Artifacts?

Yes.

The verdict matched the upstream artifact chain exactly:

- preflight said the venue path was not batch-ready
- the canary showed all shadow sessions skipped unavailable feed
- the gate remained `not_ready`
- the readiness artifact still held `limited_live_gate_status == "not_ready"`

The verdict did not invent any new failure mode. It summarized the existing no-go state correctly.

## Operator Confusion Found

1. Stop conditions were implicit, not explicit enough.
   - The runbook ordered preflight, canary, shadow evidence, and verdict review, but it did not say plainly enough to stop immediately if preflight fails or if the canary fails.
   - During this rehearsal, steps 2-5 were still executable after step 1 had already produced a clear no-go.

2. Operator readiness defaults can add an additional no-go reason.
   - `live_readiness_status.json` defaulted to `limited_live_gate_status == "not_ready"`.
   - That is a legitimate guardrail, but if the operator is rehearsing launchability rather than holding launch, they need to know that this state will keep the verdict negative even if venue conditions improve.

3. CLI output can name runtime-level market paths that are not materialized.
   - The runtime printed `live_market_status_path` and `venue_constraints_path`.
   - In this rehearsal, those files were not actually written because every session skipped unavailable feed.
   - This is not a verdict bug, but it is an operator review detail worth calling out.

## Final Conclusion

- artifact is usable for operator review

Why:

- the verdict was deterministic
- the verdict matched the upstream artifacts
- the verdict stayed artifact-only and did not imply live authority
- the reason codes were specific enough for an operator to see both the environmental blocker and the operator-readiness hold

What needed improvement:

- the runbook and operator summary docs should say more explicitly when to stop after failed preflight/canary
- the docs should call out that `limited_live_gate_status == "ready_for_review"` is required if the operator wants the verdict to reflect launch-review readiness rather than a deliberate hold state
