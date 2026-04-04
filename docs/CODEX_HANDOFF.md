# Codex Handoff

Read first:

- `docs/ARCHITECTURE.md`
- `docs/OPERATING_MODEL.md`
- `docs/RISK_POLICY.md`
- `docs/PHASE_PLAN.md`
- `README.md`

## Role

You are implementing one bounded phase in a controlled crypto trading system. You are not authorized to expand scope, add live trading behavior, or introduce infrastructure that the current phase does not require.

## Non-Negotiables

- execute one phase only
- inspect the repo before changing code
- prefer the smallest complete implementation
- keep deterministic risk and policy logic outside prompts
- validate the phase before stopping
- do not change unrelated files
- do not add databases, queues, auth, or deployment layers unless explicitly required
- do not invent exchange behavior
- do not claim production readiness

## Current Assignment

Phase 1 only:

- scaffold the repository foundation
- add packaging and quality gates
- add config skeleton
- add shared event envelope
- add docs skeleton
- add initial unit tests
