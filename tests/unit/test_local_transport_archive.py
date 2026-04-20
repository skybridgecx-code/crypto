from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.transport_archive import main
from crypto_agent.transport.archive import (
    LocalTransportArchiveResult,
    write_local_transport_archive,
)
from crypto_agent.transport.boundary_response import write_local_transport_boundary_response
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


def _write_pickup_and_response(handoff_request_path: Path, *, response_kind: str) -> None:
    write_local_transport_pickup_receipt(
        handoff_request_path=handoff_request_path,
        pickup_operator="operator-alpha",
        picked_up_at_epoch_ns=1700000000000000999,
    )
    if response_kind == "ack":
        write_local_transport_boundary_response(
            handoff_request_path=handoff_request_path,
            response_kind="ack",
            responded_at_epoch_ns=1700000000000001111,
        )
    else:
        write_local_transport_boundary_response(
            handoff_request_path=handoff_request_path,
            response_kind="reject",
            responded_at_epoch_ns=1700000000000001222,
            reason_codes=["validation_error"],
            validation_error="handoff payload failed local boundary checks",
        )


def test_write_local_transport_archive_copies_canonical_ack_artifacts(tmp_path: Path) -> None:
    correlation_id = "theme_ctx_strong.analysis_success_export"
    attempt_id = "1700000000000000001_approve"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key=f"{correlation_id}:1700000000000000001:approve",
    )
    _write_pickup_and_response(handoff_request_path, response_kind="ack")

    result = write_local_transport_archive(handoff_request_path=handoff_request_path)
    validated = LocalTransportArchiveResult.model_validate(
        json.loads(json.dumps(result.model_dump(mode="json")))
    )

    archive_dir = tmp_path / "transport" / "archive" / correlation_id / attempt_id
    expected_response_name = f"{correlation_id}.execution_boundary_ack.json"
    assert Path(validated.archive_dir) == archive_dir.resolve()
    assert validated.result_kind == "local_transport_archive_result"
    assert validated.status == "archived_local_transport_artifacts"
    assert validated.response_kind == "ack"
    assert Path(validated.archived_handoff_request_path).name == "handoff_request.json"
    assert Path(validated.archived_pickup_receipt_path).name == "cryp_pickup_receipt.json"
    assert Path(validated.archived_response_artifact_path).name == expected_response_name
    assert Path(validated.archived_handoff_request_path).read_text(encoding="utf-8") == Path(
        validated.handoff_request_path
    ).read_text(encoding="utf-8")
    assert Path(validated.archived_pickup_receipt_path).read_text(encoding="utf-8") == Path(
        validated.pickup_receipt_path
    ).read_text(encoding="utf-8")
    assert Path(validated.archived_response_artifact_path).read_text(encoding="utf-8") == Path(
        validated.response_artifact_path
    ).read_text(encoding="utf-8")


def test_write_local_transport_archive_copies_canonical_reject_artifacts(tmp_path: Path) -> None:
    correlation_id = "theme_ctx_strong.analysis_success_export"
    attempt_id = "1700000000000000001_approve"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key=f"{correlation_id}:1700000000000000001:approve",
    )
    _write_pickup_and_response(handoff_request_path, response_kind="reject")

    result = write_local_transport_archive(handoff_request_path=handoff_request_path)
    validated = LocalTransportArchiveResult.model_validate(
        json.loads(json.dumps(result.model_dump(mode="json")))
    )

    expected_response_name = f"{correlation_id}.execution_boundary_reject.json"
    assert validated.response_kind == "reject"
    assert Path(validated.archived_response_artifact_path).name == expected_response_name


def test_write_local_transport_archive_rejects_missing_pickup_receipt(tmp_path: Path) -> None:
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / "run-1" / "att-1" / "handoff_request.json",
        correlation_id="run-1",
        idempotency_key="run-1:1700000000000000001:approve",
    )

    with pytest.raises(ValueError, match="pickup_receipt_missing"):
        write_local_transport_archive(handoff_request_path=handoff_request_path)


def test_write_local_transport_archive_rejects_missing_response_artifact(tmp_path: Path) -> None:
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / "run-1" / "att-1" / "handoff_request.json",
        correlation_id="run-1",
        idempotency_key="run-1:1700000000000000001:approve",
    )
    write_local_transport_pickup_receipt(
        handoff_request_path=handoff_request_path,
        pickup_operator="operator-alpha",
        picked_up_at_epoch_ns=1700000000000000999,
    )

    with pytest.raises(ValueError, match="boundary_response_artifact_missing"):
        write_local_transport_archive(handoff_request_path=handoff_request_path)


def test_write_local_transport_archive_rejects_conflicting_ack_and_reject(tmp_path: Path) -> None:
    correlation_id = "run-1"
    attempt_id = "att-1"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key="run-1:1700000000000000001:approve",
    )
    _write_pickup_and_response(handoff_request_path, response_kind="ack")

    responses_dir = tmp_path / "transport" / "responses" / correlation_id / attempt_id
    reject_path = responses_dir / f"{correlation_id}.execution_boundary_reject.json"
    reject_path.write_text(
        json.dumps(
            {
                "contract_version": "37A.v1",
                "producer_system": "polymarket-arb",
                "consumer_system": "cryp",
                "artifact_kind": "execution_boundary_intake_reject",
                "correlation_id": correlation_id,
                "idempotency_key": "run-1:1700000000000000001:approve",
                "submission_status": "rejected_for_local_execution_review",
                "responded_at_epoch_ns": 1700000000000001222,
                "reason_codes": ["validation_error"],
                "validation_error": "forced conflict fixture",
                "source_handoff_request_path": str(handoff_request_path.resolve()),
                "source_pickup_receipt_path": str(
                    (
                        tmp_path
                        / "transport"
                        / "pickup"
                        / correlation_id
                        / attempt_id
                        / "cryp_pickup_receipt.json"
                    ).resolve()
                ),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="boundary_response_conflict_multiple_artifacts"):
        write_local_transport_archive(handoff_request_path=handoff_request_path)


def test_transport_archive_cli_emits_machine_readable_result(
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
    _write_pickup_and_response(handoff_request_path, response_kind="ack")

    exit_code = main([str(handoff_request_path)])
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 0
    assert output["result_kind"] == "local_transport_archive_result"
    assert output["status"] == "archived_local_transport_artifacts"
    assert output["response_kind"] == "ack"
    assert output["correlation_id"] == correlation_id
    assert output["attempt_id"] == attempt_id
