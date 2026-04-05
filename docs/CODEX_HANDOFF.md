# Codex Handoff

Read first:

- `docs/BASELINE.md`
- `docs/HARNESS_BASELINE.md`
- `docs/MATRIX_BASELINE.md`
- `docs/OPERATOR_SURFACES.md`
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
- treat the paper-run matrix as the reference batch operator path unless the assignment explicitly changes it
- treat `docs/OPERATOR_SURFACES.md` as the canonical operator-facing summary of those validated paths
- before any edits in a new bounded phase, run `make phase-start` and require it to pass
- if preflight fails because worktree is dirty, stash or commit interrupted work before starting new work
- when files were edited, run the autofix step before validation instead of relying on manual import cleanup

## Current Baseline

- Phases 1-10 are implemented
- Validation Tracks 1-5 are implemented
- the paper replay harness plus Harness Validation 1-4 are implemented
- Single Run Report Pack and Single-Run Report Validation are implemented
- the paper-run matrix plus Matrix Validation 1-2 are implemented
- Matrix Report Pack and Matrix Report Validation are implemented
- Paper PnL Surface is implemented
- replay scorecards, event counts, review packets, and replay-derived operator summaries are snapshot-locked
- harness summaries, replay artifacts, event-stream views, single-run operator reports, and deterministic PnL surfaces are snapshot-locked
- matrix manifests, replay-derived batch aggregates, and replay-derived batch PnL surfaces are snapshot-locked
- matrix operator reports and report snapshots are snapshot-locked
- `docs/OPERATOR_SURFACES.md` summarizes the frozen operator surfaces and workflow in one place
- `make validate` is the default validation path after edits because it runs Ruff autofix before format, lint, typecheck, and test
- `make validate-check` is the non-mutating verification path for an already-clean tree
- live trading, exchange integration, UI, and production deployment are still out of scope

## Future Work Rule

Any future assignment must:

- name the exact bounded phase or validation track
- state what is in scope and out of scope
- start with `make phase-start` before any edits
- stash or commit interrupted work before starting a new assignment
- explain how the work will be validated
- stop after validation and commit
