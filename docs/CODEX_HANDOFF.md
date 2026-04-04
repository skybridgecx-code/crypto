# Codex Handoff

Read first:

- `docs/BASELINE.md`
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

## Current Baseline

- Phases 1-10 are implemented
- Validation Tracks 1-5 are implemented
- replay scorecards, event counts, review packets, and replay-derived operator summaries are snapshot-locked
- `make validate` is the default validation path
- live trading, exchange integration, UI, and production deployment are still out of scope

## Future Work Rule

Any future assignment must:

- name the exact bounded phase or validation track
- state what is in scope and out of scope
- explain how the work will be validated
- stop after validation and commit
