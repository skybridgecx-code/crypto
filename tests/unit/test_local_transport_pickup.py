from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.transport_pickup import main
from crypto_agent.transport.pickup import (
    LocalTransportPickupReceipt,
    LocalTransportPickupResult,
    write_local_transport_pickup_receipt,
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


def test_write_local_transport_pickup_receipt_writes_canonical_receipt(tmp_path: Path) -> None:
    correlation_id = "theme_ctx_strong.analysis_success_export"
    attempt_id = "1700000000000000001_approve"
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / correlation_id / attempt_id / "handoff_request.json",
        correlation_id=correlation_id,
        idempotency_key=f"{correlation_id}:1700000000000000001:approve",
    )

    result = write_local_transport_pickup_receipt(
        handoff_request_path=handoff_request_path,
        pickup_operator="operator-alpha",
        picked_up_at_epoch_ns=1700000000000000999,
    )

    validated_result = LocalTransportPickupResult.model_validate(
        json.loads(json.dumps(result.model_dump(mode="json")))
    )
    receipt_path = Path(validated_result.pickup_receipt_path)
    receipt = LocalTransportPickupReceipt.model_validate(
        json.loads(receipt_path.read_text(encoding="utf-8"))
    )

    assert (
        receipt_path
        == (
            tmp_path
            / "transport"
            / "pickup"
            / correlation_id
            / attempt_id
            / "cryp_pickup_receipt.json"
        ).resolve()
    )
    assert validated_result.result_kind == "local_transport_pickup_receipt_result"
    assert validated_result.status == "picked_up_for_local_execution_review"
    assert validated_result.attempt_id == attempt_id
    assert validated_result.correlation_id == correlation_id
    assert validated_result.idempotency_key == f"{correlation_id}:1700000000000000001:approve"
    assert validated_result.pickup_operator == "operator-alpha"
    assert validated_result.picked_up_at_epoch_ns == 1700000000000000999
    assert receipt.contract_version == "37A.v1"
    assert receipt.producer_system == "polymarket-arb"
    assert receipt.consumer_system == "cryp"
    assert receipt.pickup_status == "picked_up_for_local_execution_review"
    assert receipt.correlation_id == correlation_id


def test_write_local_transport_pickup_receipt_rejects_missing_required_field(
    tmp_path: Path,
) -> None:
    handoff_request_path = (
        tmp_path / "transport" / "inbound" / "run-1" / "att-1" / "handoff_request.json"
    )
    handoff_request_path.parent.mkdir(parents=True, exist_ok=True)
    handoff_request_path.write_text(
        json.dumps(
            {
                "contract_version": "37A.v1",
                "producer_system": "polymarket-arb",
                "consumer_system": "cryp",
                "correlation_id": "run-1",
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError) as exc_info:
        write_local_transport_pickup_receipt(
            handoff_request_path=handoff_request_path,
            pickup_operator="operator-alpha",
            picked_up_at_epoch_ns=1700000000000000999,
        )
    assert "handoff_request_missing_required_field:idempotency_key" in str(exc_info.value)


def test_write_local_transport_pickup_receipt_rejects_correlation_id_path_mismatch(
    tmp_path: Path,
) -> None:
    handoff_request_path = _write_handoff_request(
        tmp_path / "transport" / "inbound" / "run-on-path" / "att-1" / "handoff_request.json",
        correlation_id="run-in-payload",
        idempotency_key="run-in-payload:1700000000000000001:approve",
    )

    with pytest.raises(ValueError) as exc_info:
        write_local_transport_pickup_receipt(
            handoff_request_path=handoff_request_path,
            pickup_operator="operator-alpha",
            picked_up_at_epoch_ns=1700000000000000999,
        )
    assert "handoff_request_correlation_id_path_mismatch" in str(exc_info.value)


def test_transport_pickup_cli_emits_machine_readable_result(
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
            "operator-beta",
            "--picked-up-at-epoch-ns",
            "1700000000000000777",
        ]
    )
    captured = capsys.readouterr()
    output = json.loads(captured.out)

    assert exit_code == 0
    assert output["result_kind"] == "local_transport_pickup_receipt_result"
    assert output["status"] == "picked_up_for_local_execution_review"
    assert output["correlation_id"] == correlation_id
    assert output["attempt_id"] == attempt_id
    assert output["pickup_operator"] == "operator-beta"
    assert output["picked_up_at_epoch_ns"] == 1700000000000000777
