# Launch Verdict Reason Codes

Phase G10 documents how operators should interpret `runs/<runtime-id>/live_launch_verdict.json`.

This artifact is a derivative operator summary. It does not create live authority, production execution, a new execution mode, a second accounting system, or a new source of trusted account state.

## Allowed verdicts

| Verdict | Meaning | Operator posture |
|---|---|---|
| `launchable_here_now` | Existing preflight, canary, gate, readiness, and control artifacts all agree that this host is currently launchable for operator review. | Continue review only. This artifact still grants no execution authority. |
| `not_launchable_here_now` | One or more upstream artifacts does not support launching here now. | Stop. Inspect reason codes and upstream artifacts before any rerun. |

## Required launchable conditions

`launchable_here_now` is allowed only when all checks are true:

- `live_market_preflight.batch_readiness == true`
- `shadow_canary_evaluation.state == "pass"`
- `live_gate_threshold_summary.blocking_passed == true`
- `live_gate_threshold_summary.readiness_passed == true`
- `live_gate_decision.state == "ready"`
- `live_readiness_status.status == "ready"`
- `live_readiness_status.limited_live_gate_status == "ready_for_review"`
- no blocking reason codes are present from preflight, canary, gate, readiness, or controls

If any check fails, the verdict must be `not_launchable_here_now`.

## Reason-code map

| Reason code | Source artifact | Meaning | Operator action | Rerun allowed? | Stop? |
|---|---|---|---|---|---|
| `preflight_missing` | `live_market_preflight.json` | The launch verdict could not load a preflight artifact. | Stop and run the required preflight step before canary or longer shadow evidence. | Yes, rerun preflight after confirming config/runtime id. | Yes |
| `preflight_not_batch_ready` | `live_market_preflight.json` | Preflight exists but `batch_readiness` is false. | Inspect preflight status, feed health, venue constraints, and batch readiness reason. | Yes, only after feed/venue issue is understood. | Yes |
| `preflight_status_<status>` | `live_market_preflight.json` | Preflight status was propagated into the verdict. Example: `preflight_status_retries_exhausted`. | Inspect `live_market_preflight.json.status` and confirm whether the host/feed was healthy. | Yes, if the issue is transient and bounded retry is justified. | Yes |
| `preflight_status_retries_exhausted` | `live_market_preflight.json` | Preflight exhausted configured live-market polling retries. | Treat this host/feed as unavailable for launch review. Check network, venue availability, base URL, and symbol config. | Yes, after fixing or confirming feed availability. | Yes |
| `preflight_reason_<batch_readiness_reason>` | `live_market_preflight.json` | Preflight batch readiness reason was propagated into the verdict. | Read `batch_readiness_reason` and resolve the exact failure before continuing. | Depends on the reason. | Yes |
| `preflight_reason_retries_exhausted` | `live_market_preflight.json` | Batch readiness failed because retries were exhausted. | Same as `preflight_status_retries_exhausted`; do not proceed to launch review on this evidence. | Yes, after confirming feed recovery. | Yes |
| `preflight_reason_stability_probe_unavailable` | `live_market_preflight.json` | Single probe may have worked, but the stability/batch follow-up failed. | Do not trust the host for launch review. Recheck feed stability. | Yes, after stability is restored. | Yes |
| `shadow_canary_not_passed` | `shadow_canary_evaluation.json` | Canary state was not `pass`. | Inspect canary rows and skipped/unavailable-feed evidence. Do not continue to launch review. | Yes, after preflight is batch-ready and feed is stable. | Yes |
| `unavailable_feed_sessions_present` | `shadow_canary_evaluation.json` | Canary or shadow evidence includes sessions skipped because live feed was unavailable. | Treat host/feed as not launchable here now. Review feed and retry only after preflight passes. | Yes, after feed issue is resolved. | Yes |
| `not_all_sessions_executed` | `shadow_canary_evaluation.json` | Canary expected sessions did not all execute. | Inspect canary rows and runtime history. Do not accept the canary. | Yes, after fixing the cause. | Yes |
| `live_gate_blocking_thresholds_not_passed` | `live_gate_threshold_summary.json` | One or more blocking gate checks failed. | Inspect failed blocking checks before any further review. | Maybe, only after root cause is resolved. | Yes |
| `live_gate_readiness_thresholds_not_passed` | `live_gate_threshold_summary.json` | One or more readiness checks failed. | Inspect readiness checks and supporting artifacts. | Maybe, only after missing evidence/readiness is resolved. | Yes |
| `reconciliation_mismatch` | `live_gate_threshold_summary.json` | Reconciliation evidence did not match expected paper-derived state. | Stop. Inspect reconciliation report and account-state artifacts. | No, not until mismatch is explained. | Yes |
| `operator_not_ready_status` | `live_gate_threshold_summary.json` | Operator readiness status is not ready. | Set readiness intentionally only after evidence is reviewed. | Yes, after operator readiness is deliberately updated. | Yes |
| `operator_readiness_not_ready` | `live_readiness_status.json` | `live_readiness_status.status` is not `ready`. | Keep launch stopped until the operator explicitly marks readiness ready. | Yes, after operator review. | Yes |
| `manual_halt_active` | `live_gate_threshold_summary.json` / controls | Manual halt is active. | Keep stopped. Remove halt only through the approved operator workflow. | No, not until halt is cleared intentionally. | Yes |
| `control_status_<action>` | `live_control_status.json` / gate / verdict | Current control status is not `go`. Example: `control_status_stop`. | Inspect live control status and reason codes. | Maybe, only after control status is intentionally changed. | Yes |
| `limited_live_gate_not_ready_for_review` | `live_readiness_status.json` / gate | Limited-live gate status is not `ready_for_review`. | Keep stopped. Operator must explicitly move gate status to ready-for-review after evidence review. | Yes, after intentional readiness update. | Yes |
| `insufficient_completed_sessions` | `live_gate_threshold_summary.json` | Runtime did not complete enough sessions for gate readiness. | Run longer bounded shadow evidence if preflight and canary are healthy. | Yes, if preflight/canary pass. | Yes |
| `insufficient_executed_sessions` | `live_gate_threshold_summary.json` | Not enough sessions executed. | Inspect skips, unavailable feed evidence, and runtime history. | Yes, only after feed/runtime cause is addressed. | Yes |
| `failed_sessions_present` | `live_gate_threshold_summary.json` | One or more sessions failed. | Inspect failed session summaries and runtime history. | Maybe, after root cause is fixed. | Yes |
| `interrupted_sessions_present` | `live_gate_threshold_summary.json` | One or more sessions were interrupted. | Inspect runtime interruption cause. | Maybe, after interruption cause is fixed. | Yes |
| `insufficient_shadow_sessions` | `live_gate_threshold_summary.json` | Not enough valid shadow sessions were produced. | Run longer bounded shadow evidence only if preflight/canary are healthy. | Yes, if upstream evidence is healthy. | Yes |
| `insufficient_shadow_requests` | `live_gate_threshold_summary.json` | Shadow execution evidence did not include enough requests. | Inspect shadow evidence and runtime configuration. | Yes, if upstream evidence is healthy. | Yes |
| `insufficient_shadow_nonzero_request_sessions` | `live_gate_threshold_summary.json` | Too few executed shadow sessions produced at least one normalized request. | Treat executed zero-request sessions as non-firing; continue only after bounded evidence supports nonzero request sessions. | Yes, if upstream evidence is healthy. | Yes |
| `insufficient_shadow_would_send_requests` | `live_gate_threshold_summary.json` | Shadow evidence did not include enough `would_send` request outcomes. | Inspect shadow request/result artifacts and verify bounded request flow quality. | Yes, if upstream evidence is healthy. | Yes |
| `shadow_artifacts_missing` | `live_gate_threshold_summary.json` | Required shadow artifacts are missing. | Stop and inspect runtime artifact generation. | Yes, after artifact path/runtime issue is fixed. | Yes |
| `cumulative_net_realized_pnl_below_floor` | `live_gate_threshold_summary.json` | Cumulative net realized paper PnL is below the configured gate floor. | Stop and review soak performance and configured floor before any launchability claim. | Maybe, after bounded evidence improves or floor policy is intentionally adjusted. | Yes |
| `average_return_fraction_below_floor` | `live_gate_threshold_summary.json` | Average return fraction is below the configured gate floor. | Stop and review session-level returns and configured floor before continuing. | Maybe, after bounded evidence improves or floor policy is intentionally adjusted. | Yes |
| `live_gate_state_not_ready` | `live_gate_decision.json` | Gate decision state is `not_ready`. | Inspect gate decision reason codes and threshold summary. | Maybe, only after upstream failures are resolved. | Yes |
| `live_gate_state_blocked` | `live_gate_decision.json` | Gate decision state is `blocked`. | Treat as hard stop. Inspect blocking checks first. | No, not until blocking condition is resolved. | Yes |
| readiness-specific reason codes | `live_readiness_status.json` | Readiness artifact supplied additional operator/status reason codes. | Read the readiness artifact and resolve operator note/status issue. | Depends on reason. | Yes |
| control-specific reason codes | `live_control_status.json` | Controls supplied additional go/no-go reason codes. | Read control status and manual control state before continuing. | Depends on reason. | Yes |

## G9 rehearsal result mapping

Phase G9 observed a correct `not_launchable_here_now` verdict on this host.

Observed reason codes mapped as follows:

| G9 reason code | Operator interpretation |
|---|---|
| `preflight_not_batch_ready` | Stop at preflight. Host/feed did not support batch readiness. |
| `preflight_status_retries_exhausted` | Stop. Configured feed retries were exhausted. |
| `shadow_canary_not_passed` | Stop. Canary did not pass. |
| `unavailable_feed_sessions_present` | Stop. Evidence contains unavailable-feed sessions. |
| `live_gate_readiness_thresholds_not_passed` | Stop. Readiness checks failed. |
| `limited_live_gate_not_ready_for_review` | Stop. Operator readiness gate was not ready for review. |
| `insufficient_executed_sessions` | Stop. Runtime evidence did not include enough executed sessions. |
| `insufficient_shadow_requests` | Stop. Shadow evidence was insufficient. |
| `live_gate_state_not_ready` | Stop. Gate decision was not ready. |

## Operator rule

When `live_launch_verdict.json.verdict == "not_launchable_here_now"`, the operator must not continue by manually overriding the verdict. The only valid next action is to inspect the mapped reason codes, resolve the upstream artifact issue, and rerun the bounded workflow from the correct step.

When `live_launch_verdict.json.verdict == "launchable_here_now"`, the artifact still grants no execution authority. It only says the existing preflight, canary, gate, readiness, and controls agree that this host is launchable for operator review.
