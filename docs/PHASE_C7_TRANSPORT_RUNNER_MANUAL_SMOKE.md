# Phase C7 — Manual Smoke and Rerun Guidance for `crypto-agent-transport-run-once`

## Scope

This phase is docs/manual-verification only for the shipped one-shot local transport runner:

- CLI: `crypto-agent-transport-run-once`
- module: `src/crypto_agent/cli/transport_run_once.py`
- orchestration: `src/crypto_agent/transport/runner.py`

No runtime behavior changes are introduced in this phase.

## Contract Anchors

The manual smoke below validates the shipped consumer-side contract alignment from:

- `docs/PHASE_37J_LOCAL_TRANSPORT_CONSUMER_WORKFLOW_CONTRACT.md`
- `/Users/muhammadaatif/polymarket-arb/docs/PHASE_37I_LOCAL_TRANSPORT_WORKFLOW_CONTRACT.md`

Canonical local paths under `<TRANSPORT_ROOT>`:

- inbound request:
  - `inbound/<correlation_id>/<attempt_id>/handoff_request.json`
- pickup receipt:
  - `pickup/<correlation_id>/<attempt_id>/cryp_pickup_receipt.json`
- boundary response (exactly one):
  - `responses/<correlation_id>/<attempt_id>/<correlation_id>.execution_boundary_ack.json`
  - or `responses/<correlation_id>/<attempt_id>/<correlation_id>.execution_boundary_reject.json`
- archive:
  - `archive/<correlation_id>/<attempt_id>/...`

## Manual Smoke Setup

Executed locally in `cryp` with deterministic test values:

- `TRANSPORT_ROOT=/tmp/cryp-c7-smoke`
- `correlation_id=theme_ctx_strong.analysis_success_export`
- good attempt id: `1700000000000000001_approve`
- bad/rerun attempt id: `1700000000000000002_reject`

CLI invocation uses module mode with local path wiring:

```bash
PYTHONPATH=src python3.11 -m crypto_agent.cli.transport_run_once ...
```

## Case 1 — Known-Good Flow (Ack)

### Command

```bash
PYTHONPATH=src python3.11 -m crypto_agent.cli.transport_run_once \
  /tmp/cryp-c7-smoke/inbound/theme_ctx_strong.analysis_success_export/1700000000000000001_approve/handoff_request.json \
  --pickup-operator operator@example.com \
  --picked-up-at-epoch-ns 1700000000000000100 \
  --response-kind ack \
  --responded-at-epoch-ns 1700000000000000200
```

### Observed result shape

- `result_kind=local_transport_one_shot_result`
- `status=accepted_for_local_execution_review`
- `response_kind=ack`
- includes absolute paths for:
  - `pickup_receipt_path`
  - `response_artifact_path`
  - `archive_dir`
  - `archived_handoff_request_path`
  - `archived_pickup_receipt_path`
  - `archived_response_artifact_path`

### Expected artifacts

- `/tmp/cryp-c7-smoke/pickup/theme_ctx_strong.analysis_success_export/1700000000000000001_approve/cryp_pickup_receipt.json`
- `/tmp/cryp-c7-smoke/responses/theme_ctx_strong.analysis_success_export/1700000000000000001_approve/theme_ctx_strong.analysis_success_export.execution_boundary_ack.json`
- `/tmp/cryp-c7-smoke/archive/theme_ctx_strong.analysis_success_export/1700000000000000001_approve/handoff_request.json`
- `/tmp/cryp-c7-smoke/archive/theme_ctx_strong.analysis_success_export/1700000000000000001_approve/cryp_pickup_receipt.json`
- `/tmp/cryp-c7-smoke/archive/theme_ctx_strong.analysis_success_export/1700000000000000001_approve/theme_ctx_strong.analysis_success_export.execution_boundary_ack.json`

## Case 2 — Known-Bad Flow (Reject metadata missing reason codes)

This uses a canonical inbound handoff request but intentionally invalid reject arguments.

### Command

```bash
PYTHONPATH=src python3.11 -m crypto_agent.cli.transport_run_once \
  /tmp/cryp-c7-smoke/inbound/theme_ctx_strong.analysis_success_export/1700000000000000002_reject/handoff_request.json \
  --pickup-operator operator@example.com \
  --picked-up-at-epoch-ns 1700000000000000300 \
  --response-kind reject \
  --responded-at-epoch-ns 1700000000000000400 \
  --validation-error "missing reasons should fail"
```

### Observed failure

- exit code: `2`
- stderr:
  - `transport_run_once_cli_error: boundary_response_reject_reason_codes_required`

### Expected artifacts after this failure

- pickup exists for attempt:
  - `/tmp/cryp-c7-smoke/pickup/theme_ctx_strong.analysis_success_export/1700000000000000002_reject/cryp_pickup_receipt.json`
- no boundary response artifact for attempt
- no archive directory for attempt

This is the deterministic partial-progress behavior of the shipped runner:

1. pickup step succeeds first
2. boundary response step fails on reject metadata validation
3. archive step does not run

## Rerun Guidance After Failure

Use the same `<correlation_id>/<attempt_id>` and rerun with corrected reject arguments.

### Corrective rerun command

```bash
PYTHONPATH=src python3.11 -m crypto_agent.cli.transport_run_once \
  /tmp/cryp-c7-smoke/inbound/theme_ctx_strong.analysis_success_export/1700000000000000002_reject/handoff_request.json \
  --pickup-operator operator@example.com \
  --picked-up-at-epoch-ns 1700000000000000300 \
  --response-kind reject \
  --responded-at-epoch-ns 1700000000000000400 \
  --reason-codes contract_validation_failed \
  --validation-error "missing reasons fixed"
```

### Observed rerun outcome

- `result_kind=local_transport_one_shot_result`
- `status=rejected_for_local_execution_review`
- `response_kind=reject`
- writes canonical reject response artifact
- writes canonical archive copies for the same attempt

### Rerun expectations (exact)

- allowed: rerun same attempt after this specific failure mode
- required: provide non-empty `--reason-codes` and non-empty `--validation-error` for reject
- preserved: existing pickup receipt may be overwritten deterministically for same attempt path
- blocked: writing opposite response kind if one already exists (existing boundary conflict guard remains in force)

## Operator Notes

- The runner is deterministic and strictly local file-based.
- The runner does not perform polling/watching or cross-repo orchestration.
- `ack` and `reject` both remain bounded review artifacts only and never authorize live execution.
- If a run fails with a pickup already written and no response/archive, treat it as a bounded partial-progress state and rerun with corrected arguments for the same attempt.
