# Phase Plan

## Execution Rule

Complete one bounded phase at a time. Validate that phase before starting the next. Do not backfill future-phase functionality opportunistically.

## Completed Implementation Phases

- Phase 1: repository foundation
- Phase 2: core contracts and config expansion
- Phase 3: market data and replay skeleton
- Phase 4: features and regime rules
- Phase 5: signal engine
- Phase 6: risk and policy layer
- Phase 7: paper execution simulator
- Phase 8: monitoring and journaling
- Phase 9: evaluation and replay
- Phase 10: LLM advisory layer

## Completed Validation Tracks

- Validation Track 1: incident drills and replay fixture expansion
- Validation Track 2: mixed replay runs and recovery drills
- Validation Track 3: multi-run replay suites
- Validation Track 4: replay regression snapshots
- Validation Track 5: review packet and operator-summary regression snapshots

## Completed Harness Work

- Paper Run Harness: end-to-end replay runner
- Harness Validation 1: paper-run summary regression snapshots
- Harness Validation 2: replay artifact regression snapshots
- Harness Validation 3: adverse paper-run snapshots
- Harness Validation 4: event-stream regression snapshots
- Single Run Report Pack: operator-readable single-run report artifact
- Single-Run Report Validation: report regression snapshot coverage
- Trade Ledger Surface: operator-readable single-run trade ledger artifact
- Trade Ledger Validation: trade-ledger regression snapshot coverage

## Completed Matrix Work

- Paper Run Matrix: fixed five-case batch replay runner
- Matrix Validation 1: manifest regression snapshots
- Matrix Validation 2: replay aggregate regression snapshots
- Matrix Report Pack: operator-readable batch report artifact
- Matrix Report Validation: report regression snapshot coverage
- Matrix Comparison Surface: operator-readable batch comparison artifact
- Matrix Comparison Validation: batch comparison regression snapshot coverage
- Matrix Trade Ledger Surface: operator-readable batch trade ledger artifact
- Matrix Trade Ledger Validation: batch trade-ledger regression snapshot coverage
- Paper PnL Surface: deterministic replay-derived PnL and ending-equity accounting

## Baseline Freeze

The current repository state is frozen as the validated baseline documented in [docs/BASELINE.md](/Users/muhammadaatif/cryp/docs/BASELINE.md). Future work should treat that document as the reference point and propose new bounded tracks relative to it.

## Completed Forward Runtime Work

- Phase A: forward paper runtime
- Phase B: live market data and venue constraints
- Phase C: account state, reconciliation, and recovery
- Phase D: shadow and sandbox execution adapter
- Phase E: live risk controls and ops guardrails
- Phase F: soak evaluation, shadow evaluation, and live gate
- Phase G3: venue preflight probe and operator fail-fast diagnostics
- Phase G4: preflight-to-batch consistency diagnostics
- Phase G5: preflight launch-truth hardening
- Phase G6: shadow canary launchability evidence
- Phase G7: freeze shadow canary operator path
- Phase G8: operator live-launch verdict artifact
- Phase G9: launch verdict operator rehearsal
- Live Launch Runbook Freeze: canonical first tiny-live review procedure without executable live mode

## Harness Freeze

The paper replay harness is frozen as the validated operator path documented in [docs/HARNESS_BASELINE.md](/Users/muhammadaatif/cryp/docs/HARNESS_BASELINE.md). Future operator-facing work should extend that path rather than introducing a second CLI or parallel harness.

## Matrix Freeze

The paper-run matrix is frozen as the validated batch operator path documented in [docs/MATRIX_BASELINE.md](/Users/muhammadaatif/cryp/docs/MATRIX_BASELINE.md). Future batch operator work should extend that path rather than introducing a second matrix runner or parallel batch flow.

## Current Validation Path

- `make validate`
- `make validate-check`

## Stop Conditions

Stop and report if:

- a dependency or environment issue blocks validation
- the requested phase would require out-of-scope infrastructure
- existing repo state conflicts with the bounded phase

## Phase G10 — Launch verdict reason-code operator map

Phase G10 adds `docs/LAUNCH_VERDICT_REASON_CODES.md`, an operator-facing map for `live_launch_verdict.json.reason_codes`.

Scope is docs/runbook only. The verdict remains artifact-only and grants no live execution authority.

## Phase G11 — Launch verdict workflow closeout

Phase G11 freezes the G8-G10 launch-verdict workflow as the current operator review endpoint.

Closeout doc:
- `docs/PHASE_G11_LAUNCH_VERDICT_WORKFLOW_CLOSEOUT.md`

The workflow remains artifact-only and does not authorize production live execution.

## Phase H1A — Sandbox CLI wiring

Phase H1A wires the existing explicit sandbox adapter into the CLI for bounded sandbox rehearsals.

Closeout doc:
- `docs/PHASE_H1A_SANDBOX_CLI_WIRING.md`

The phase remains sandbox-only and does not authorize production live execution.

## Phase H1B — Sandbox executable-order rehearsal blocker

Phase H1B documents that CLI-level non-zero sandbox order rehearsal is blocked under current safety boundaries.

Closeout doc:
- `docs/PHASE_H1B_SANDBOX_EXECUTABLE_ORDER_REHEARSAL_BLOCKER.md`

Future work should explicitly scope fixture-backed sandbox CLI rehearsal before changing replay/sandbox guards.

## Phase H1C — Fixture-backed sandbox CLI rehearsal design

Phase H1C defines a design-only path for future deterministic fixture-backed sandbox CLI rehearsal.

Closeout doc:
- `docs/PHASE_H1C_FIXTURE_BACKED_SANDBOX_CLI_REHEARSAL_DESIGN.md`

No code is added in H1C. Implementation must be separately scoped.

## Phase H1D — Implement fixture-backed sandbox rehearsal

Phase H1D implements the explicit fixture-backed sandbox CLI rehearsal designed in H1C.

Closeout doc:
- `docs/PHASE_H1D_IMPLEMENT_FIXTURE_BACKED_SANDBOX_REHEARSAL.md`

## Phase H1E — Sandbox rehearsal operator docs

Phase H1E documents the shipped fixture-backed sandbox CLI rehearsal for operators.

Closeout doc:
- `docs/PHASE_H1E_SANDBOX_REHEARSAL_OPERATOR_DOCS.md`

## Phase H1G — Sandbox track closeout

Phase H1G closes out the H1 sandbox track as a bounded operator rehearsal surface.

Closeout doc:
- `docs/PHASE_H1G_SANDBOX_TRACK_CLOSEOUT.md`

## Phase H2A — Shipped vs blocked surface audit

Phase H2A records the current operator-facing boundary between shipped surfaces and intentionally blocked surfaces.

Closeout doc:
- `docs/PHASE_H2A_SHIPPED_VS_BLOCKED_SURFACE_AUDIT.md`

## Phase H2B — Guard and flag coverage audit

Phase H2B audits the shipped forward-runtime guardrails and operator-facing flag contract against the current docs and tests.

Closeout doc:
- `docs/PHASE_H2B_GUARD_FLAG_COVERAGE_AUDIT.md`

## Phase H2C — Operator command reference audit

Phase H2C audits the operator-facing command references in the frozen docs against the shipped CLI entrypoints and current guard contract.

Closeout doc:
- `docs/PHASE_H2C_OPERATOR_COMMAND_REFERENCE_AUDIT.md`

## Phase L1A — Tiny limited-live scope lock

Phase L1A locks the smallest acceptable first live-authority envelope without enabling live order transmission.

Closeout doc:
- `docs/PHASE_L1A_TINY_LIMITED_LIVE_SCOPE_LOCK.md`

## Phase L1B — Limited-live authority design

Phase L1B defines the bounded control surface required before any live-order transmission code is added.

Closeout doc:
- `docs/PHASE_L1B_LIMITED_LIVE_AUTHORITY_DESIGN.md`

## Phase L1C — Limited-live implementation scope map

Phase L1C maps the exact code touchpoints for the first bounded live-authority implementation.

Closeout doc:
- `docs/PHASE_L1C_LIMITED_LIVE_IMPLEMENTATION_SCOPE_MAP.md`

## Phase L1D — Limited-live implementation foundation

Phase L1D adds the deny-by-default limited-live foundation artifacts and runtime path wiring required before any live transmission logic is introduced.

Closeout doc:
- `docs/PHASE_L1D_LIMITED_LIVE_IMPLEMENTATION_FOUNDATION.md`

## Phase L1E — Limited-live gate evaluation

Phase L1E adds deny-by-default limited-live gate evaluation using the L1D authority and launch-window artifacts.

Closeout doc:
- `docs/PHASE_L1E_LIMITED_LIVE_GATE_EVALUATION.md`

## Phase L1F — Live approval foundation

Phase L1F adds the typed approval-state artifact and deny-by-default approval wiring required before any bounded limited-live transmission path can advance.

Closeout doc:
- `docs/PHASE_L1F_LIVE_APPROVAL_FOUNDATION.md`

## Phase L1G — Launch window foundation

Phase L1G upgrades the limited-live launch-window artifact from a static placeholder to runtime-controlled state.

Closeout doc:
- `docs/PHASE_L1G_LAUNCH_WINDOW_FOUNDATION.md`

## Phase L1H — Limited-live enable toggle

Phase L1H upgrades the limited-live authority artifact from a static default into runtime-controlled enabled or disabled state.

Closeout doc:
- `docs/PHASE_L1H_LIMITED_LIVE_ENABLE_TOGGLE.md`

## Phase L1I — Real transmission boundary wiring

Phase L1I wires the explicit limited-live transmission boundary into the forward runtime execution seam while keeping the repository without executable live trading behavior.

Closeout doc:
- `docs/PHASE_L1I_REAL_TRANSMISSION_BOUNDARY_WIRING.md`

## Phase L1J — Tiny positive-path live-authority test

Phase L1J closes out the bounded positive-path limited-live authority test coverage already present after L1I.

Closeout doc:
- `docs/PHASE_L1J_TINY_POSITIVE_PATH_LIVE_AUTHORITY_TEST.md`

## Phase L1K — Operator dry run / first live checklist

Phase L1K closes the limited-live preparation track with one bounded operator dry-run and first-live checklist.

Closeout doc:
- `docs/PHASE_L1K_OPERATOR_DRY_RUN_FIRST_LIVE_CHECKLIST.md`


## Phase C6-C11 — Transport runner hardening sequence closeout

The C6-C11 transport runner hardening sequence is complete.

Shipped scope:
- C6: one-shot local transport runner
- C7: manual smoke and rerun guidance
- C8: additive one-shot step-state artifact
- C9: pinned non-canonical inbound-path failure behavior
- C10: operator-facing pre-canonical failure clarification
- C11: transport runner hardening checkpoint

Reference docs:
- `docs/OPERATOR_SURFACES.md`
- `docs/PHASE_C7_TRANSPORT_RUNNER_MANUAL_SMOKE.md`
- `docs/PHASE_C11_TRANSPORT_RUNNER_HARDENING_CHECKPOINT.md`

Current boundary:
- local file-based consumer-side transport only
- no network transport
- no auth, DB, queue, or worker behavior
- no polling or watcher behavior
- no producer-side changes
- no live execution expansion

Future work rule:
- do not reopen this sequence unless a new bounded consumer-side requirement is explicitly scoped

## Phase L2A — Bounded live transmission scope lock

Phase L2A defines the smallest acceptable first real live transmission envelope before any code widens authority.

Closeout doc:
- `docs/PHASE_L2A_BOUNDED_LIVE_TRANSMISSION_SCOPE_LOCK.md`

## Phase L2B — Bounded live transmission adapter design

Phase L2B defines the exact live adapter boundary for the first bounded real live transmission phase.

Closeout doc:
- `docs/PHASE_L2B_BOUNDED_LIVE_TRANSMISSION_ADAPTER_DESIGN.md`

## Phase L2C — Bounded live transmission implementation map

Phase L2C maps the exact code touchpoints for the first bounded live transmission implementation.

Closeout doc:
- `docs/PHASE_L2C_BOUNDED_LIVE_TRANSMISSION_IMPLEMENTATION_MAP.md`

## Phase L2D — Bounded live transmission artifact foundation

Phase L2D adds bounded live request/result/state artifact foundations at the runtime seam without enabling live transmission.

Closeout doc:
- `docs/PHASE_L2D_BOUNDED_LIVE_TRANSMISSION_ARTIFACT_FOUNDATION.md`

## Phase L2E — Bounded live adapter call wiring

Phase L2E wires the first bounded live adapter call at the authorized runtime seam with fail-closed artifacted behavior.

Closeout doc:
- `docs/PHASE_L2E_BOUNDED_LIVE_ADAPTER_CALL_WIRING.md`

## Phase L2F — Operator-enforced first live transmit rehearsal

Phase L2F freezes the operator-enforced rehearsal procedure for the first real transmitted order inside the bounded live-transmission envelope.

Closeout doc:
- `docs/PHASE_L2F_OPERATOR_ENFORCED_FIRST_LIVE_TRANSMIT_REHEARSAL.md`

## Phase L2G — First bounded live transmit evidence review closeout

Phase L2G freezes the evidence-review closeout procedure required after the first bounded real transmitted order.

Closeout doc:
- `docs/PHASE_L2G_FIRST_BOUNDED_LIVE_TRANSMIT_EVIDENCE_REVIEW_CLOSEOUT.md`

## Phase L2H — First bounded live transmit outcome closeout

Phase L2H records the outcome of the first bounded real live transmitted order and whether a second attempt is allowed or blocked.

Closeout doc:
- `docs/PHASE_L2H_FIRST_BOUNDED_LIVE_TRANSMIT_OUTCOME_CLOSEOUT.md`

## Phase L2I — Second-attempt decision closeout

Phase L2I records whether a second bounded live transmit attempt is allowed or blocked after the first bounded attempt and its L2H outcome review.

Closeout doc:
- `docs/PHASE_L2I_SECOND_ATTEMPT_DECISION_CLOSEOUT.md`

## Phase L2K — Orphaned forward runtime operator closeout

Phase L2K freezes the operator handling contract for orphaned forward runtimes after L2J interrupt hardening.

Closeout doc:
- `docs/PHASE_L2K_ORPHANED_RUNTIME_OPERATOR_CLOSEOUT.md`

## Phase L2L — Shadow zero-request diagnosis closeout

Phase L2L records that an `executed` shadow session can still have zero shadow requests when the underlying paper run emits no order intents.

Closeout doc:
- `docs/PHASE_L2L_SHADOW_ZERO_REQUEST_DIAGNOSIS_CLOSEOUT.md`

## Phase L2M — Second-attempt prerequisites closeout

Phase L2M records the exact prerequisites that must be true before any future bounded second soak attempt can even be considered. It is a decision-criteria closeout, not a retry authorization.

Closeout doc:
- `docs/PHASE_L2M_SECOND_ATTEMPT_PREREQUISITES_CLOSEOUT.md`

## Phase L2N — Live edge qualification gate

Phase L2N adds bounded edge-quality readiness checks to the live-gate threshold summary so session completion alone cannot be misread as launchable edge evidence.

Closeout doc:
- `docs/PHASE_L2N_LIVE_EDGE_QUALIFICATION_GATE.md`

## Phase L2O — Edge qualification reason-code freeze

Phase L2O freezes the operator-facing reason-code contract for L2N edge-qualification checks.

Closeout doc:
- `docs/PHASE_L2O_EDGE_REASON_CODE_FREEZE.md`

## Phase L2P — Live gate config artifact surface

Phase L2P persists `live_gate_config.json` and threads `live_gate_config_path` through runtime status, registry, and CLI/shared operator surfaces.

Closeout doc:
- `docs/PHASE_L2P_LIVE_GATE_CONFIG_ARTIFACT_SURFACE.md`

## Phase L2Q — Live gate config regression snapshots

Phase L2Q adds deterministic regression snapshot coverage for `live_gate_config.json` and asserts runtime status and CLI path reconciliation for `live_gate_config_path`.

Closeout doc:
- `docs/PHASE_L2Q_LIVE_GATE_CONFIG_REGRESSION_SNAPSHOTS.md`

## Phase L2R — Runtime status index regression snapshot

Phase L2R adds deterministic snapshot coverage for canonical `forward_paper_status.json` index fields, including `live_gate_config_path`, to prevent operator-surface path drift.

Closeout doc:
- `docs/PHASE_L2R_RUNTIME_STATUS_INDEX_REGRESSION_SNAPSHOT.md`

## Phase L2S — Runtime registry entry regression snapshot

Phase L2S adds deterministic snapshot coverage for canonical `forward_paper_registry.json` runtime entry path fields, including `live_gate_config_path`, to prevent status/registry surface drift.

Closeout doc:
- `docs/PHASE_L2S_RUNTIME_REGISTRY_ENTRY_REGRESSION_SNAPSHOT.md`
