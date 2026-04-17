# Codex Handoff

Read first:

- `docs/BASELINE.md`
- `docs/HARNESS_BASELINE.md`
- `docs/MATRIX_BASELINE.md`
- `docs/OPERATOR_SURFACES.md`
- `docs/LIVE_LAUNCH_RUNBOOK.md`
- `docs/ARCHITECTURE.md`
- `docs/OPERATING_MODEL.md`
- `docs/RISK_POLICY.md`
- `docs/PHASE_PLAN.md`
- `README.md`

## Role

You are working from a frozen validated baseline in a controlled crypto trading system. You are not authorized to expand scope, add live trading behavior, or introduce infrastructure that the assigned bounded track does not require.

## Non-Negotiables

- treat `docs/BASELINE.md` as the reference point
- execute one bounded phase or validation track only
- inspect the repo before changing code
- prefer the smallest complete implementation
- keep deterministic risk and policy logic outside prompts
- validate the phase before stopping
- do not change unrelated files
- do not add databases, queues, auth, or deployment layers unless explicitly required
- do not invent exchange behavior
- do not claim production readiness
- do not rewrite the architecture unless explicitly instructed
- preserve the existing replay, journal, and snapshot surfaces unless the assignment explicitly changes them
- treat the paper replay harness as the reference operator path unless the assignment explicitly changes it
- treat `runs/<run-id>/trade_ledger.json` as part of the frozen single-run operator contract unless the assignment explicitly changes it
- treat the paper-run matrix as the reference batch operator path unless the assignment explicitly changes it
- treat `runs/<matrix-run-id>/matrix_comparison.json` as part of the frozen batch operator contract unless the assignment explicitly changes it
- treat `runs/<matrix-run-id>/matrix_trade_ledger.json` as part of the frozen batch operator contract unless the assignment explicitly changes it
- treat `docs/OPERATOR_SURFACES.md` as the canonical operator-facing summary of those validated paths
- treat `runs/<runtime-id>/live_market_preflight.json` as part of the frozen forward-runtime operator contract unless the assignment explicitly changes it
- treat `runs/<runtime-id>/shadow_canary_evaluation.json` as part of the frozen forward-runtime operator contract unless the assignment explicitly changes it
- treat `runs/<runtime-id>/soak_evaluation.json` as part of the frozen forward-runtime operator contract unless the assignment explicitly changes it
- treat `runs/<runtime-id>/shadow_evaluation.json` as part of the frozen forward-runtime operator contract unless the assignment explicitly changes it
- treat `runs/<runtime-id>/live_gate_threshold_summary.json` as part of the frozen forward-runtime operator contract unless the assignment explicitly changes it
- treat `runs/<runtime-id>/live_gate_decision.json` as part of the frozen forward-runtime operator contract unless the assignment explicitly changes it
- treat `runs/<runtime-id>/live_gate_report.md` as part of the frozen forward-runtime operator contract unless the assignment explicitly changes it
- treat `runs/<runtime-id>/live_launch_verdict.json` as part of the frozen forward-runtime operator contract unless the assignment explicitly changes it
- treat [docs/LIVE_LAUNCH_RUNBOOK.md](/Users/muhammadaatif/cryp/docs/LIVE_LAUNCH_RUNBOOK.md) as the canonical first-launch live review procedure
- before any edits in a new bounded phase, run `make phase-start` and require it to pass
- if preflight fails because worktree is dirty, stash or commit interrupted work before starting new work
- after bounded work, run `make phase-finish` before treating the phase as complete
- if `make phase-finish` reports a dirty tree, commit intended changes and autofixes or revert unrelated churn before closing the phase
- after commit or cleanup, run `make phase-close-check` on the final clean tree
- when files were edited, rely on `make validate` inside `make phase-finish` instead of manual import cleanup

## Current Baseline

- Phases 1-10 are implemented
- Validation Tracks 1-5 are implemented
- the paper replay harness plus Harness Validation 1-4 are implemented
- Single Run Report Pack and Single-Run Report Validation are implemented
- Trade Ledger Surface and Trade Ledger Validation are implemented
- the paper-run matrix plus Matrix Validation 1-2 are implemented
- Matrix Report Pack and Matrix Report Validation are implemented
- Matrix Comparison Surface and Matrix Comparison Validation are implemented
- Matrix Trade Ledger Surface and Matrix Trade Ledger Validation are implemented
- Paper PnL Surface is implemented
- replay scorecards, event counts, review packets, and replay-derived operator summaries are snapshot-locked
- harness summaries, replay artifacts, event-stream views, single-run operator reports, and deterministic PnL surfaces are snapshot-locked
- single-run trade ledgers and trade-ledger snapshots are snapshot-locked
- matrix manifests, replay-derived batch aggregates, and replay-derived batch PnL surfaces are snapshot-locked
- matrix comparison artifacts and comparison snapshots are snapshot-locked
- matrix trade ledgers and trade-ledger snapshots are snapshot-locked
- matrix operator reports and report snapshots are snapshot-locked
- `docs/OPERATOR_SURFACES.md` summarizes the frozen operator surfaces and workflow in one place
- Phases A-F are implemented:
  - forward paper runtime
  - live market data and venue constraints
  - account-state reconciliation and recovery
  - shadow and sandbox execution evidence
  - live controls and ops guardrails
  - soak evaluation, shadow evaluation, and live gate artifacts
- G-phase launchability diagnostics are implemented:
  - live-market preflight probe
  - preflight-to-batch consistency diagnostics
  - preflight launch-truth hardening
  - shadow canary launchability evidence
  - operator launch verdict artifact
- the live-launch runbook is documented in `docs/LIVE_LAUNCH_RUNBOOK.md`
- `make validate` is the default validation path after edits because it runs Ruff autofix before format, lint, typecheck, and test
- `make validate-check` is the final verification path for an already-clean tree
- `make phase-finish` is the required phase-end guardrail because it runs validation and then blocks phase completion on a dirty tree
- `make phase-close-check` is the final clean-tree confirmation path after commit or cleanup
- live trading, exchange integration, UI, and production deployment are still out of scope
- future tiny-live review is documented, but executable live mode is still out of scope

## Future Work Rule

Any future assignment must:

- name the exact bounded phase or validation track
- state what is in scope and out of scope
- start with `make phase-start` before any edits
- stash or commit interrupted work before starting a new assignment
- run `make phase-finish` before considering the assignment complete
- commit intended changes and autofixes or revert unrelated churn if `make phase-finish` reports a dirty tree
- run `make phase-close-check` on the final clean tree
- explain how the work will be validated
- stop after validation and commit

## Phase G10 launch verdict reason-code map

`docs/LAUNCH_VERDICT_REASON_CODES.md` is part of the operator documentation contract for `runs/<runtime-id>/live_launch_verdict.json`.

Do not change verdict semantics, reason-code behavior, live authority, execution modes, or trusted account-state boundaries unless a future assignment explicitly scopes that change.
