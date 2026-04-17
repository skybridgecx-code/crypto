# Phase G11 — Launch Verdict Workflow Closeout

## Status

Phase G11 closes out the current launch-verdict workflow.

The crypto-agent remains a controlled, auditable, non-production-live system. Trusted state remains paper-derived. Execution modes remain bounded to:

- `paper`
- `shadow`
- `sandbox`

No production live execution is authorized by this closeout.

## Frozen workflow

The current operator launchability workflow is frozen in this order:

1. Run phase guardrail:
   - `make phase-start`
2. Run live-market preflight:
   - write `runs/<runtime-id>/live_market_preflight.json`
3. Run bounded shadow canary:
   - write `runs/<runtime-id>/shadow_canary_evaluation.json`
4. Run longer bounded shadow evidence:
   - write soak, shadow, gate, readiness, control, reconciliation, and status artifacts
5. Review gate artifacts:
   - `live_gate_threshold_summary.json`
   - `live_gate_decision.json`
   - `live_gate_report.md`
6. Review final operator verdict:
   - `live_launch_verdict.json`
7. Resolve any reason codes using:
   - `docs/LAUNCH_VERDICT_REASON_CODES.md`
8. Finish/close the phase:
   - `make phase-finish`
   - commit intended changes
   - `make phase-close-check`

## Frozen operator artifacts

The following forward-runtime operator artifacts are part of the frozen review contract:

- `runs/<runtime-id>/live_market_preflight.json`
- `runs/<runtime-id>/shadow_canary_evaluation.json`
- `runs/<runtime-id>/soak_evaluation.json`
- `runs/<runtime-id>/shadow_evaluation.json`
- `runs/<runtime-id>/live_gate_threshold_summary.json`
- `runs/<runtime-id>/live_gate_decision.json`
- `runs/<runtime-id>/live_gate_report.md`
- `runs/<runtime-id>/live_launch_verdict.json`
- `runs/<runtime-id>/live_readiness_status.json`
- `runs/<runtime-id>/live_control_status.json`
- `runs/<runtime-id>/manual_control_state.json`
- `runs/<runtime-id>/account_state.json`
- `runs/<runtime-id>/reconciliation_report.json`
- `runs/<runtime-id>/recovery_status.json`
- `runs/<runtime-id>/forward_paper_status.json`
- `runs/<runtime-id>/forward_paper_history.jsonl`

## Stop conditions

The operator must stop if any of the following are true:

- `live_market_preflight.json.batch_readiness != true`
- `shadow_canary_evaluation.json.state != "pass"`
- `live_gate_threshold_summary.json.blocking_passed != true`
- `live_gate_threshold_summary.json.readiness_passed != true`
- `live_gate_decision.json.state != "ready"`
- `live_launch_verdict.json.verdict != "launchable_here_now"`
- `live_launch_verdict.json.reason_codes` is non-empty
- `live_readiness_status.json.status != "ready"`
- `live_readiness_status.json.limited_live_gate_status != "ready_for_review"`
- `live_control_status.json.go_no_go_action != "go"`
- any manual halt/control stop is active
- reconciliation evidence does not match expected paper-derived state
- required artifacts are missing
- runtime evidence includes unresolved unavailable-feed, failed, interrupted, or skipped sessions

When stopped, the operator must inspect the upstream artifact and mapped reason code before rerunning from the correct workflow step.

## What the verdict does not authorize

`live_launch_verdict.json` does not authorize:

- production live trading
- live order transmission
- account-state trust widening
- bypassing paper-derived reconciliation
- changing execution modes
- bypassing controls
- bypassing readiness gates
- manual override of failed preflight, canary, gate, or control evidence

The verdict is derivative. It summarizes existing artifact truth for operator review.

## Current validation status

As of this closeout, the G8-G10 workflow has:

- typed launch verdict artifact support
- deterministic reason-code aggregation
- runtime materialization beside existing gate/canary artifacts
- operator rehearsal evidence from Phase G9
- reason-code operator map from Phase G10
- validation passing with:
  - `ruff`
  - `mypy src`
  - `pytest -q`

## Future allowed work

Future work may include:

- docs polish
- additional evidence collection
- sandbox-only tests
- improved operator examples
- bug fixes inside the current artifact contract
- clearer reason-code wording without changing verdict semantics
- additional tests that preserve the frozen boundaries

## Future disallowed work unless explicitly re-scoped

Future work must not add or widen:

- production live execution
- new execution modes
- live order authority
- trusted account-state beyond paper-derived reconciliation
- strategy/risk/execution rewrites
- second accounting system
- silent agent actions
- automatic override of stop conditions
- hidden launch authority behind `launchable_here_now`

## Closeout conclusion

The launch-verdict workflow is frozen as an operator review surface.

The system remains controlled, auditable, paper-derived, and non-production-live.
