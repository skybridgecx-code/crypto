from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.transport_boundary_response import main
from crypto_agent.transport.boundary_response import (
    LocalTransportBoundaryResponseArtifact,
    LocalTransportBoundaryResponseResult,
    write_local_transport_boundary_response,
)
from crypto_agent.transport.pickup import write_local_transport_pickup_receipt


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


def _write_valid_pickup_receipt(handoff_request_path: Path) -> Path:
    result = write_local_transport_pickup_receipt(
        handoff_request_path=handoff_request_path,
        pickup_operator="operator-alpha",
        picked_up_at_epoch_ns=1700000000000000999,
    )
    return Path(result.pickup_receipt_path)


def test_write_boundary_response_writes_canonical_ack_artifact(tmp_path: Path) -> None:
    correlation_id = "theme_ctx_strong.analysis_success_export"
    attempt_id = "1700000000000000001_approve"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key=f"{correlation_id}:1700000000000000001:approve",
    )
    _write_valid_pickup_receipt(handoff_request_path)

    result = write_local_transport_boundary_response(
        handoff_request_path=handoff_request_path,
        response_kind="ack",
        responded_at_epoch_ns=1700000000000001111,
    )
    validated_result = LocalTransportBoundaryResponseResult.model_validate(
        json.loads(json.dumps(result.model_dump(mode="json")))
    )
    artifact_path = Path(validated_result.response_artifact_path)
    artifact = LocalTransportBoundaryResponseArtifact.model_validate(
        json.loads(artifact_path.read_text(encoding="utf-8"))
    )

    assert (
        artifact_path
        == (
            tmp_path
            / "transport"
            / "responses"
            / correlation_id
            / attempt_id
            / f"{correlation_id}.execution_boundary_ack.json"
        ).resolve()
    )
    assert validated_result.status == "accepted_for_local_execution_review"
    assert validated_result.response_kind == "ack"
    assert artifact.artifact_kind == "execution_boundary_intake_ack"
    assert artifact.submission_status == "accepted_for_local_execution_review"
    assert artifact.reason_codes == []
    assert artifact.validation_error is None


def test_write_boundary_response_writes_canonical_reject_artifact(tmp_path: Path) -> None:
    correlation_id = "theme_ctx_strong.analysis_success_export"
    attempt_id = "1700000000000000001_approve"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key=f"{correlation_id}:1700000000000000001:approve",
    )
    _write_valid_pickup_receipt(handoff_request_path)

    result = write_local_transport_boundary_response(
        handoff_request_path=handoff_request_path,
        response_kind="reject",
        responded_at_epoch_ns=1700000000000001222,
        reason_codes=["validation_error", "missing_field"],
        validation_error="handoff payload failed local boundary checks",
    )
    validated_result = LocalTransportBoundaryResponseResult.model_validate(
        json.loads(json.dumps(result.model_dump(mode="json")))
    )
    artifact_path = Path(validated_result.response_artifact_path)
    artifact = LocalTransportBoundaryResponseArtifact.model_validate(
        json.loads(artifact_path.read_text(encoding="utf-8"))
    )

    assert (
        artifact_path
        == (
            tmp_path
            / "transport"
            / "responses"
            / correlation_id
            / attempt_id
            / f"{correlation_id}.execution_boundary_reject.json"
        ).resolve()
    )
    assert validated_result.status == "rejected_for_local_execution_review"
    assert validated_result.response_kind == "reject"
    assert artifact.artifact_kind == "execution_boundary_intake_reject"
    assert artifact.submission_status == "rejected_for_local_execution_review"
    assert artifact.reason_codes == ["validation_error", "missing_field"]
    assert artifact.validation_error == "handoff payload failed local boundary checks"


def test_write_boundary_response_rejects_missing_pickup_receipt(tmp_path: Path) -> None:
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / "run-1" / "att-1" / "handoff_request.json",
        correlation_id="run-1",
        idempotency_key="run-1:1700000000000000001:approve",
    )

    with pytest.raises(ValueError, match="pickup_receipt_missing"):
        write_local_transport_boundary_response(
            handoff_request_path=handoff_request_path,
            response_kind="ack",
            responded_at_epoch_ns=1700000000000001111,
        )


def test_write_boundary_response_rejects_pickup_receipt_mismatch(tmp_path: Path) -> None:
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / "run-1" / "att-1" / "handoff_request.json",
        correlation_id="run-1",
        idempotency_key="run-1:1700000000000000001:approve",
    )
    pickup_receipt_path = _write_valid_pickup_receipt(handoff_request_path)
    payload = json.loads(pickup_receipt_path.read_text(encoding="utf-8"))
    payload["idempotency_key"] = "run-1:999:approve"
    pickup_receipt_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    with pytest.raises(ValueError, match="pickup_receipt_idempotency_key_mismatch"):
        write_local_transport_boundary_response(
            handoff_request_path=handoff_request_path,
            response_kind="ack",
            responded_at_epoch_ns=1700000000000001111,
        )


def test_write_boundary_response_reject_requires_reason_and_validation_error(
    tmp_path: Path,
) -> None:
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / "run-1" / "att-1" / "handoff_request.json",
        correlation_id="run-1",
        idempotency_key="run-1:1700000000000000001:approve",
    )
    _write_valid_pickup_receipt(handoff_request_path)

    with pytest.raises(ValueError, match="boundary_response_reject_reason_codes_required"):
        write_local_transport_boundary_response(
            handoff_request_path=handoff_request_path,
            response_kind="reject",
            responded_at_epoch_ns=1700000000000001111,
            reason_codes=[],
            validation_error="failed checks",
        )

    with pytest.raises(ValueError, match="boundary_response_reject_validation_error_required"):
        write_local_transport_boundary_response(
            handoff_request_path=handoff_request_path,
            response_kind="reject",
            responded_at_epoch_ns=1700000000000001111,
            reason_codes=["validation_error"],
            validation_error="",
        )


def test_write_boundary_response_blocks_conflicting_existing_artifact(tmp_path: Path) -> None:
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / "run-1" / "att-1" / "handoff_request.json",
        correlation_id="run-1",
        idempotency_key="run-1:1700000000000000001:approve",
    )
    _write_valid_pickup_receipt(handoff_request_path)

    write_local_transport_boundary_response(
        handoff_request_path=handoff_request_path,
        response_kind="ack",
        responded_at_epoch_ns=1700000000000001111,
    )

    with pytest.raises(ValueError, match="boundary_response_conflict_existing_ack"):
        write_local_transport_boundary_response(
            handoff_request_path=handoff_request_path,
            response_kind="reject",
            responded_at_epoch_ns=1700000000000001222,
            reason_codes=["validation_error"],
            validation_error="cannot write reject after ack",
        )


def test_transport_boundary_response_cli_emits_machine_readable_result(
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
    _write_valid_pickup_receipt(handoff_request_path)

    exit_code = main(
        [
            str(handoff_request_path),
            "--response-kind",
            "ack",
            "--responded-at-epoch-ns",
            "1700000000000001333",
        ]
    )
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 0
    assert output["result_kind"] == "local_transport_boundary_response_result"
    assert output["status"] == "accepted_for_local_execution_review"
    assert output["response_kind"] == "ack"
    assert output["correlation_id"] == correlation_id
    assert output["attempt_id"] == attempt_id
    assert output["responded_at_epoch_ns"] == 1700000000000001333
