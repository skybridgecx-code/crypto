# Phase 37J — Local Transport Consumer Workflow Contract (`cryp`)

## What Matters

This document aligns `cryp` with the shipped producer-side local transport contract in:

- `/Users/muhammadaatif/polymarket-arb/docs/PHASE_37I_LOCAL_TRANSPORT_WORKFLOW_CONTRACT.md`
- `/Users/muhammadaatif/polymarket-arb/docs/PHASE_37K_CROSS_REPO_CONTRACT_DRIFT_CHECKLIST.md` (cross-repo drift gate/checklist)

Scope is consumer-side docs only. No runtime behavior changes.

## Consumer Role

`cryp` acts as the local consumer of a producer-written transport request:

- input artifact: `handoff_request.json`
- producer system: `polymarket-arb`
- consumer system: `cryp`
- contract focus: local pickup plus execution-boundary intake review

`cryp` does not own producer packaging. `cryp` owns pickup receipt, intake boundary decision, and local archival.

## Canonical Local Paths (Consumer View)

Transport root is operator-configured:

- `TRANSPORT_ROOT=<absolute/local/path>`

For a specific `<correlation_id>/<attempt_id>` pair, `cryp` reads and writes only these canonical paths:

- inbound request (read):
  - `<TRANSPORT_ROOT>/inbound/<correlation_id>/<attempt_id>/handoff_request.json`
- pickup receipt (write):
  - `<TRANSPORT_ROOT>/pickup/<correlation_id>/<attempt_id>/cryp_pickup_receipt.json`
- boundary ack (write when accepted):
  - `<TRANSPORT_ROOT>/responses/<correlation_id>/<attempt_id>/<correlation_id>.execution_boundary_ack.json`
- boundary reject (write when rejected):
  - `<TRANSPORT_ROOT>/responses/<correlation_id>/<attempt_id>/<correlation_id>.execution_boundary_reject.json`
- archive location (write):
  - `<TRANSPORT_ROOT>/archive/<correlation_id>/<attempt_id>/...`

## Pickup and Review Boundary Behavior

For each attempt directory:

1. Read `handoff_request.json` from canonical inbound path.
2. Write exactly one pickup receipt at the canonical pickup path.
3. Preserve `correlation_id` and `idempotency_key` unchanged through intake.
4. Produce exactly one boundary response artifact per attempt:
   - ack: accepted for local execution review boundary
   - reject: failed boundary validation or contract checks
5. If reject:
   - stop; do not advance into runtime review/execution preparation
6. If ack:
   - continue only as bounded local execution review under existing `cryp` guardrails
7. Archive request, receipt, and boundary response under canonical archive path.

Boundary semantics:

- ack means `accepted_for_local_execution_review`
- reject means `rejected_for_local_execution_review`
- neither ack nor reject authorizes production live execution

## Required Consumer Artifacts

### Pickup receipt

Required fields:

- `contract_version` (`"37A.v1"`)
- `producer_system` (`"polymarket-arb"`)
- `consumer_system` (`"cryp"`)
- `correlation_id`
- `idempotency_key`
- `pickup_status` (`"picked_up_for_local_execution_review"`)
- `picked_up_at_epoch_ns`
- `pickup_operator`
- `source_handoff_request_path`

### Boundary response

Exactly one response artifact per attempt:

- ack artifact kind: `execution_boundary_intake_ack`
- reject artifact kind: `execution_boundary_intake_reject`

Reject responses must include:

- `reason_codes`
- `validation_error`

## Idempotency and Duplicate Handling

- idempotency tuple: `<run_id>:<updated_at_epoch_ns>:<operator_decision>`
- same `<correlation_id>/<attempt_id>` is the same attempt, not a new request
- duplicate pickup of the same attempt must not be treated as new work
- new `updated_at_epoch_ns` or decision produces a new `attempt_id` directory
- latest-attempt selection is operator policy, not automatic supersession

## Preserved Boundaries and Non-Goals

This Phase 37J consumer contract does not introduce:

- network transport
- auth, key exchange, DB, queue, worker, or scheduler
- automatic cross-repo orchestration
- production live execution expansion
- replacement of existing `cryp` runtime guardrails

This document aligns local intake boundary behavior only.

## Advisory External Confirmation (Forward-Paper Only)

Optional advisory context can be provided to forward-paper evaluation without changing
transport contract shape and without authoring executable trade parameters:

```bash
python -m crypto_agent.cli.forward_paper tests/fixtures/paper_candles_breakout_long.jsonl \
  --runtime-id phase-37j-advisory-demo \
  --execution-mode paper \
  --external-confirmation-path /absolute/path/external_confirmation.json
```

Deterministic advisory-proof command (proposal-level, no live/replay dependency):

```bash
pytest -q tests/unit/test_external_confirmation_deterministic_proof.py
```

OMEGA fixture seam-proof command (loader -> proposal evaluation seam):

```bash
pytest -q tests/unit/test_external_confirmation_deterministic_proof.py -k omega_fixture_loader_to_proposal_seam_proof
```

Advisory vs control forward-paper comparison command:

```bash
python -m crypto_agent.cli.forward_paper_compare \
  --advisory-run-id omega-advisory-btcusdt-us \
  --control-run-id omega-control-btcusdt-us \
  --runs-dir runs
```

Repeatable multi-symbol advisory/control experiment command:

```bash
python -m crypto_agent.cli.forward_paper_experiment \
  --symbols BTCUSDT ETHUSDT SOLUSDT \
  --advisory-artifact-path /absolute/path/external_confirmation.json \
  --binance-base-url https://api.binance.us \
  --run-id-prefix omega-us-phase37j \
  --session-interval-seconds 60 \
  --max-sessions 2 \
  --output-dir runs/advisory_control_experiments \
  --runs-dir runs
```
