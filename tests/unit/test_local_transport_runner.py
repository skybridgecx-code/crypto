from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.transport_run_once import main
from crypto_agent.transport.boundary_response import write_local_transport_boundary_response
from crypto_agent.transport.pickup import write_local_transport_pickup_receipt
from crypto_agent.transport.runner import (
    LocalTransportOneShotResult,
    LocalTransportOneShotStepState,
    run_local_transport_one_shot,
)


def _write_handoff_request(
    path: Path,
    *,
    correlation_id: str = "theme_ctx_strong.analysis_success_export",
    idempotency_key: str = "theme_ctx_strong.analysis_success_export:1700000000000000001:approve",
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "contract_version": "37A.v1",
                "producer_system": "polymarket-arb",
                "consumer_system": "cryp",
                "correlation_id": correlation_id,
                "idempotency_key": idempotency_key,
                "handoff_payload": {"run_id": correlation_id},
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return path


def test_run_local_transport_one_shot_ack_writes_pickup_response_and_archive(
    tmp_path: Path,
) -> None:
    correlation_id = "theme_ctx_strong.analysis_success_export"
    attempt_id = "1700000000000000001_approve"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key=f"{correlation_id}:1700000000000000001:approve",
    )

    result = run_local_transport_one_shot(
        handoff_request_path=handoff_request_path,
        pickup_operator="operator-alpha",
        picked_up_at_epoch_ns=1700000000000000100,
        response_kind="ack",
        responded_at_epoch_ns=1700000000000000200,
    )
    validated = LocalTransportOneShotResult.model_validate(
        json.loads(json.dumps(result.model_dump(mode="json")))
    )

    assert validated.result_kind == "local_transport_one_shot_result"
    assert validated.status == "accepted_for_local_execution_review"
    assert validated.response_kind == "ack"
    assert validated.correlation_id == correlation_id
    assert validated.attempt_id == attempt_id
    assert Path(validated.pickup_receipt_path).is_file()
    assert Path(validated.response_artifact_path).is_file()
    assert Path(validated.archived_handoff_request_path).is_file()
    assert Path(validated.archived_pickup_receipt_path).is_file()
    assert Path(validated.archived_response_artifact_path).is_file()
    assert Path(validated.step_state_artifact_path).is_file()
    step_state = LocalTransportOneShotStepState.model_validate(
        json.loads(Path(validated.step_state_artifact_path).read_text(encoding="utf-8"))
    )
    assert step_state.final_outcome == "succeeded"
    assert step_state.pickup_step_state == "succeeded"
    assert step_state.boundary_response_step_state == "succeeded"
    assert step_state.archive_step_state == "succeeded"
    assert step_state.final_status == "accepted_for_local_execution_review"


def test_run_local_transport_one_shot_reject_writes_pickup_response_and_archive(
    tmp_path: Path,
) -> None:
    correlation_id = "theme_ctx_strong.analysis_success_export"
    attempt_id = "1700000000000000001_approve"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key=f"{correlation_id}:1700000000000000001:approve",
    )

    result = run_local_transport_one_shot(
        handoff_request_path=handoff_request_path,
        pickup_operator="operator-beta",
        picked_up_at_epoch_ns=1700000000000000100,
        response_kind="reject",
        responded_at_epoch_ns=1700000000000000200,
        reason_codes=["contract_validation_failed"],
        validation_error="contract validation failed",
    )

    assert result.status == "rejected_for_local_execution_review"
    assert result.response_kind == "reject"
    assert Path(result.response_artifact_path).name.endswith(".execution_boundary_reject.json")
    assert Path(result.archived_response_artifact_path).name.endswith(
        ".execution_boundary_reject.json"
    )


def test_run_local_transport_one_shot_reject_validation_failure_creates_no_response(
    tmp_path: Path,
) -> None:
    correlation_id = "run-1"
    attempt_id = "att-1"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key="run-1:1700000000000000001:approve",
    )

    with pytest.raises(ValueError, match="boundary_response_reject_reason_codes_required"):
        run_local_transport_one_shot(
            handoff_request_path=handoff_request_path,
            pickup_operator="operator-gamma",
            picked_up_at_epoch_ns=1700000000000000100,
            response_kind="reject",
            responded_at_epoch_ns=1700000000000000200,
            reason_codes=[],
            validation_error="required reject metadata missing",
        )

    pickup_path = (
        tmp_path / "transport" / "pickup" / correlation_id / attempt_id / "cryp_pickup_receipt.json"
    )
    responses_dir = tmp_path / "transport" / "responses" / correlation_id / attempt_id
    step_state_path = (
        tmp_path
        / "transport"
        / "state"
        / correlation_id
        / attempt_id
        / "cryp_transport_run_once_step_state.json"
    )
    assert pickup_path.is_file()
    assert not responses_dir.exists()
    assert step_state_path.is_file()
    step_state = LocalTransportOneShotStepState.model_validate(
        json.loads(step_state_path.read_text(encoding="utf-8"))
    )
    assert step_state.final_outcome == "failed"
    assert step_state.pickup_step_state == "succeeded"
    assert step_state.boundary_response_step_state == "failed"
    assert step_state.archive_step_state == "not_started"
    assert step_state.final_status == "failed_before_boundary_response"
    assert step_state.error_code == "boundary_response_reject_reason_codes_required"


def test_run_local_transport_one_shot_blocks_opposite_existing_response(tmp_path: Path) -> None:
    correlation_id = "run-1"
    attempt_id = "att-1"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key="run-1:1700000000000000001:approve",
    )
    write_local_transport_pickup_receipt(
        handoff_request_path=handoff_request_path,
        pickup_operator="operator-alpha",
        picked_up_at_epoch_ns=1700000000000000100,
    )
    write_local_transport_boundary_response(
        handoff_request_path=handoff_request_path,
        response_kind="reject",
        responded_at_epoch_ns=1700000000000000200,
        reason_codes=["contract_validation_failed"],
        validation_error="forced reject before one-shot ack",
    )

    with pytest.raises(ValueError, match="boundary_response_conflict_existing_reject"):
        run_local_transport_one_shot(
            handoff_request_path=handoff_request_path,
            pickup_operator="operator-alpha",
            picked_up_at_epoch_ns=1700000000000000100,
            response_kind="ack",
            responded_at_epoch_ns=1700000000000000300,
        )

    responses_dir = tmp_path / "transport" / "responses" / correlation_id / attempt_id
    ack_path = responses_dir / f"{correlation_id}.execution_boundary_ack.json"
    reject_path = responses_dir / f"{correlation_id}.execution_boundary_reject.json"
    assert reject_path.is_file()
    assert not ack_path.exists()


def test_run_local_transport_one_shot_noncanonical_path_writes_no_step_state(
    tmp_path: Path,
) -> None:
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "not_inbound" / "run-1" / "att-1" / "handoff_request.json",
        correlation_id="run-1",
        idempotency_key="run-1:1700000000000000001:approve",
    )

    with pytest.raises(ValueError, match="handoff_request_path_not_inbound_tree"):
        run_local_transport_one_shot(
            handoff_request_path=handoff_request_path,
            pickup_operator="operator-epsilon",
            picked_up_at_epoch_ns=1700000000000000100,
            response_kind="ack",
            responded_at_epoch_ns=1700000000000000200,
        )

    assert not (tmp_path / "transport" / "state").exists()


def test_transport_run_once_cli_emits_machine_readable_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    correlation_id = "theme_ctx_strong.analysis_success_export"
    attempt_id = "1700000000000000001_approve"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key=f"{correlation_id}:1700000000000000001:approve",
    )

    exit_code = main(
        [
            str(handoff_request_path),
            "--pickup-operator",
            "operator-delta",
            "--picked-up-at-epoch-ns",
            "1700000000000000100",
            "--response-kind",
            "ack",
            "--responded-at-epoch-ns",
            "1700000000000000200",
        ]
    )
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 0
    assert output["result_kind"] == "local_transport_one_shot_result"
    assert output["status"] == "accepted_for_local_execution_review"
    assert output["response_kind"] == "ack"
    assert output["correlation_id"] == correlation_id
    assert output["attempt_id"] == attempt_id
    assert output["step_state_artifact_path"].endswith(
        "/state/theme_ctx_strong.analysis_success_export/1700000000000000001_approve/"
        "cryp_transport_run_once_step_state.json"
    )
