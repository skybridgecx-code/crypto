# Phase H2A Shipped vs Blocked Surface Audit

## What Matters

This document is the operator-facing audit of what is actually shipped in this repository versus what is intentionally blocked.

It separates:

- artifact generation
- operator review surfaces
- executable authority

It does not authorize new behavior.

## Canonical References

Read these first when using this audit:

- [README.md](/Users/muhammadaatif/cryp/README.md)
- [docs/CODEX_HANDOFF.md](/Users/muhammadaatif/cryp/docs/CODEX_HANDOFF.md)
- [docs/BASELINE.md](/Users/muhammadaatif/cryp/docs/BASELINE.md)
- [docs/OPERATOR_SURFACES.md](/Users/muhammadaatif/cryp/docs/OPERATOR_SURFACES.md)
- [docs/LIVE_LAUNCH_RUNBOOK.md](/Users/muhammadaatif/cryp/docs/LIVE_LAUNCH_RUNBOOK.md)
- [docs/PHASE_PLAN.md](/Users/muhammadaatif/cryp/docs/PHASE_PLAN.md)
- [docs/PHASE_G11_LAUNCH_VERDICT_WORKFLOW_CLOSEOUT.md](/Users/muhammadaatif/cryp/docs/PHASE_G11_LAUNCH_VERDICT_WORKFLOW_CLOSEOUT.md)
- [docs/PHASE_H1A_SANDBOX_CLI_WIRING.md](/Users/muhammadaatif/cryp/docs/PHASE_H1A_SANDBOX_CLI_WIRING.md)
- [docs/PHASE_H1B_SANDBOX_EXECUTABLE_ORDER_REHEARSAL_BLOCKER.md](/Users/muhammadaatif/cryp/docs/PHASE_H1B_SANDBOX_EXECUTABLE_ORDER_REHEARSAL_BLOCKER.md)
- [docs/PHASE_H1C_FIXTURE_BACKED_SANDBOX_CLI_REHEARSAL_DESIGN.md](/Users/muhammadaatif/cryp/docs/PHASE_H1C_FIXTURE_BACKED_SANDBOX_CLI_REHEARSAL_DESIGN.md)
- [docs/PHASE_H1D_IMPLEMENT_FIXTURE_BACKED_SANDBOX_REHEARSAL.md](/Users/muhammadaatif/cryp/docs/PHASE_H1D_IMPLEMENT_FIXTURE_BACKED_SANDBOX_REHEARSAL.md)
- [docs/PHASE_H1E_SANDBOX_REHEARSAL_OPERATOR_DOCS.md](/Users/muhammadaatif/cryp/docs/PHASE_H1E_SANDBOX_REHEARSAL_OPERATOR_DOCS.md)
- [docs/PHASE_H1G_SANDBOX_TRACK_CLOSEOUT.md](/Users/muhammadaatif/cryp/docs/PHASE_H1G_SANDBOX_TRACK_CLOSEOUT.md)
- [docs/LAUNCH_VERDICT_REASON_CODES.md](/Users/muhammadaatif/cryp/docs/LAUNCH_VERDICT_REASON_CODES.md)

## Shipped Surfaces

### Single-run replay harness

- Surface:
  - `crypto-agent-paper-run`
  - `journals/<run-id>.jsonl`
  - `runs/<run-id>/summary.json`
  - `runs/<run-id>/report.md`
  - `runs/<run-id>/trade_ledger.json`
- Authority level:
  - trusted replay and paper-evaluation surface
- What it is allowed to do:
  - run deterministic paper replay
  - write replay-derived operator artifacts
- What it is not:
  - live execution
  - exchange authority

### Matrix replay operator path

- Surface:
  - `crypto-agent-paper-matrix-run`
  - `runs/<matrix-run-id>/manifest.json`
  - `runs/<matrix-run-id>/matrix_comparison.json`
  - `runs/<matrix-run-id>/matrix_trade_ledger.json`
  - `runs/<matrix-run-id>/report.md`
- Authority level:
  - trusted batch replay and comparison surface
- What it is allowed to do:
  - run the fixed replay matrix
  - write batch operator artifacts
- What it is not:
  - live execution
  - venue authority

### Forward runtime in `paper`

- Surface:
  - `crypto-agent-forward-paper-run --execution-mode paper`
  - `runs/<runtime-id>/forward_paper_status.json`
  - `runs/<runtime-id>/forward_paper_history.jsonl`
  - `runs/<runtime-id>/account_state.json`
  - `runs/<runtime-id>/reconciliation_report.json`
- Authority level:
  - trusted forward paper runtime baseline
- What it is allowed to do:
  - run bounded paper sessions
  - preserve file-backed runtime history
  - maintain paper-derived trusted account state
- What it is not:
  - live order authority

### Forward runtime in `shadow`

- Surface:
  - `crypto-agent-forward-paper-run --execution-mode shadow`
  - shadow request/result/status evidence
  - `runs/<runtime-id>/shadow_evaluation.json`
  - `runs/<runtime-id>/shadow_canary_evaluation.json`
- Authority level:
  - evidence-only execution-review surface
- What it is allowed to do:
  - normalize venue-compatible requests
  - record would-send evidence
  - support preflight, canary, soak, and launch-verdict review
- What it is not:
  - transmit orders
  - mutate trusted account truth

### Forward runtime in `sandbox`

- Surface:
  - `crypto-agent-forward-paper-run --execution-mode sandbox`
  - sandbox request/result/status evidence
- Authority level:
  - bounded sandbox-only adapter evidence
- What it is allowed to do:
  - use explicit sandbox/testnet adapter paths
  - record acknowledgements and bounded lifecycle evidence
- What it is not:
  - production live trading
  - trusted account reconciliation truth

### Live-review operator artifacts

- Surface:
  - `runs/<runtime-id>/live_market_preflight.json`
  - `runs/<runtime-id>/live_gate_threshold_summary.json`
  - `runs/<runtime-id>/live_gate_decision.json`
  - `runs/<runtime-id>/live_gate_report.md`
  - `runs/<runtime-id>/live_launch_verdict.json`
- Authority level:
  - artifact-only operator review surfaces
- What they are allowed to do:
  - summarize launchability, readiness, and reasons
  - tell the operator to stop or continue review
- What they are not:
  - execution permissions
  - live authority
  - substitutes for operator judgment

### Fixture-backed sandbox CLI rehearsal

- Surface:
  - shipped H1 fixture-backed sandbox rehearsal path
  - operator docs and closeout docs in the H1 series
- Authority level:
  - bounded rehearsal-only sandbox surface
- What it is allowed to do:
  - rehearse explicit sandbox behavior against fixture-backed inputs
- What it is not:
  - live-market launch workflow
  - production order path

## Artifact Generation vs Execution Authority

These must stay separate:

- generated artifact:
  - means the system recorded state or evidence
- execution authority:
  - means the system is allowed to place or transmit orders in a real venue

Examples:

- `live_market_preflight.json` can say a host is batch-ready.
  - that does not grant live trading authority.
- `live_gate_decision.json` can say `ready`.
  - that does not grant live trading authority.
- `live_launch_verdict.json` can say `launchable_here_now`.
  - that does not grant live trading authority.
- sandbox result/status artifacts can exist.
  - that does not make sandbox fills trusted account truth.

Current executable authority remains bounded to:

- paper simulation
- shadow no-transmit evidence
- sandbox-only bounded adapter evidence

## Intentionally Blocked Surfaces

### Production live trading

- Status:
  - blocked
- Why:
  - this repository does not ship executable production live mode
  - canonical docs explicitly keep live production trading out of scope

### Executable `limited_live`

- Status:
  - blocked
- Why:
  - the repo ships live-review artifacts and runbook guidance only
  - no executable `limited_live` mode is present

### Treating launch-review artifacts as authority

- Blocked combinations:
  - `live_market_preflight.json` as a permission signal
  - `live_gate_decision.json` as a permission signal
  - `live_launch_verdict.json` as a permission signal
- Why:
  - they are artifact-only review surfaces
  - they were intentionally shipped without execution authority

### Shadow transmitting real orders

- Status:
  - blocked
- Why:
  - shadow remains no-transmit by contract
  - its job is normalized request evidence only

### Sandbox evidence mutating trusted account state

- Status:
  - blocked
- Why:
  - trusted account state remains paper-derived
  - sandbox execution evidence is not settled account truth

### Production venue authority through sandbox surfaces

- Status:
  - blocked
- Why:
  - sandbox is bounded to explicit sandbox/testnet configuration
  - sandbox does not widen into production credentials or production routing

### Fixture-backed sandbox rehearsal replacing live-market review

- Status:
  - blocked
- Why:
  - H1 docs explicitly keep fixture-backed sandbox rehearsal separate from the live-market launch workflow
  - it does not replace:
    - preflight
    - shadow canary
    - bounded shadow evidence
    - live gate review
    - launch verdict review

### Replay plus sandbox without explicit fixture-backed rehearsal guard

- Status:
  - blocked except for the explicit shipped fixture-backed rehearsal path
- Why:
  - H1B/H1D intentionally preserve this guardrail
  - replay+sandbox is not a general-purpose executable trading path

## Intentionally Blocked Combinations

### `paper` plus live authority

- Status:
  - blocked
- Why:
  - `paper` is the trusted simulation baseline, not a live-order mode

### `shadow` plus trusted accounting

- Status:
  - blocked
- Why:
  - shadow evidence must not become a second accounting system

### `sandbox` plus production venue assumptions

- Status:
  - blocked
- Why:
  - sandbox is bounded to rehearsal and evidence
  - production credentials flow is not shipped

### Launch verdict plus unattended launch

- Status:
  - blocked
- Why:
  - the runbook requires manual supervision and explicit review
  - verdict review is a stop/go artifact, not unattended launch automation

## Bottom Line

Shipped:

- deterministic replay operator paths
- forward paper runtime
- live-review artifacts
- shadow evidence
- sandbox-only bounded rehearsal evidence

Not shipped:

- production live trading
- executable `limited_live`
- production order authority
- widening trusted account truth beyond paper-derived reconciliation

If there is any conflict between a generated artifact and authority assumptions, follow the authority boundary, not the artifact label.
