from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from crypto_agent.transport.boundary_response import LocalTransportBoundaryResponseArtifact
from crypto_agent.transport.pickup import (
    LocalTransportPickupReceipt,
    canonical_transport_context,
    read_handoff_request,
    validated_transport_fields,
)


class LocalTransportArchiveResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_kind: Literal["local_transport_archive_result"] = "local_transport_archive_result"
    status: Literal["archived_local_transport_artifacts"] = "archived_local_transport_artifacts"
    handoff_request_path: str
    pickup_receipt_path: str
    response_artifact_path: str
    archive_dir: str
    archived_handoff_request_path: str
    archived_pickup_receipt_path: str
    archived_response_artifact_path: str
    response_kind: Literal["ack", "reject"]
    correlation_id: str
    attempt_id: str
    idempotency_key: str


def _read_json_object(path: Path, *, error_prefix: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{error_prefix}_invalid_json:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{error_prefix}_invalid_json_object")
    return payload


def _load_pickup_receipt(path: Path) -> LocalTransportPickupReceipt:
    payload = _read_json_object(path, error_prefix="pickup_receipt")
    return LocalTransportPickupReceipt.model_validate(payload)


def _load_boundary_response(path: Path) -> LocalTransportBoundaryResponseArtifact:
    payload = _read_json_object(path, error_prefix="boundary_response_artifact")
    return LocalTransportBoundaryResponseArtifact.model_validate(payload)


def write_local_transport_archive(
    *,
    handoff_request_path: Path,
) -> LocalTransportArchiveResult:
    resolved_handoff_path = handoff_request_path.resolve()
    handoff_payload = read_handoff_request(resolved_handoff_path)
    correlation_id, idempotency_key = validated_transport_fields(handoff_payload)
    correlation_id_from_path, attempt_id, transport_root = canonical_transport_context(
        resolved_handoff_path
    )

    if correlation_id != correlation_id_from_path:
        raise ValueError("handoff_request_correlation_id_path_mismatch")

    pickup_receipt_path = (
        transport_root / "pickup" / correlation_id / attempt_id / "cryp_pickup_receipt.json"
    ).resolve()
    if not pickup_receipt_path.is_file():
        raise ValueError("pickup_receipt_missing")

    pickup_receipt = _load_pickup_receipt(pickup_receipt_path)
    if pickup_receipt.correlation_id != correlation_id:
        raise ValueError("pickup_receipt_correlation_id_mismatch")
    if pickup_receipt.idempotency_key != idempotency_key:
        raise ValueError("pickup_receipt_idempotency_key_mismatch")
    if pickup_receipt.source_handoff_request_path != str(resolved_handoff_path):
        raise ValueError("pickup_receipt_source_handoff_request_path_mismatch")

    responses_dir = (transport_root / "responses" / correlation_id / attempt_id).resolve()
    ack_path = responses_dir / f"{correlation_id}.execution_boundary_ack.json"
    reject_path = responses_dir / f"{correlation_id}.execution_boundary_reject.json"
    ack_exists = ack_path.is_file()
    reject_exists = reject_path.is_file()

    if ack_exists and reject_exists:
        raise ValueError("boundary_response_conflict_multiple_artifacts")
    if not ack_exists and not reject_exists:
        raise ValueError("boundary_response_artifact_missing")

    response_path = ack_path if ack_exists else reject_path
    response_kind: Literal["ack", "reject"] = "ack" if ack_exists else "reject"
    response_artifact = _load_boundary_response(response_path.resolve())

    if response_artifact.correlation_id != correlation_id:
        raise ValueError("boundary_response_correlation_id_mismatch")
    if response_artifact.idempotency_key != idempotency_key:
        raise ValueError("boundary_response_idempotency_key_mismatch")
    if response_artifact.source_handoff_request_path != str(resolved_handoff_path):
        raise ValueError("boundary_response_source_handoff_request_path_mismatch")
    if response_artifact.source_pickup_receipt_path != str(pickup_receipt_path):
        raise ValueError("boundary_response_source_pickup_receipt_path_mismatch")

    if response_kind == "ack":
        if response_artifact.artifact_kind != "execution_boundary_intake_ack":
            raise ValueError("boundary_response_artifact_kind_mismatch")
        if response_artifact.submission_status != "accepted_for_local_execution_review":
            raise ValueError("boundary_response_submission_status_mismatch")
    else:
        if response_artifact.artifact_kind != "execution_boundary_intake_reject":
            raise ValueError("boundary_response_artifact_kind_mismatch")
        if response_artifact.submission_status != "rejected_for_local_execution_review":
            raise ValueError("boundary_response_submission_status_mismatch")

    archive_dir = (transport_root / "archive" / correlation_id / attempt_id).resolve()
    archive_dir.mkdir(parents=True, exist_ok=True)

    archived_handoff_request_path = archive_dir / "handoff_request.json"
    archived_pickup_receipt_path = archive_dir / "cryp_pickup_receipt.json"
    archived_response_artifact_path = archive_dir / response_path.name
    opposite_response_name = (
        f"{correlation_id}.execution_boundary_reject.json"
        if response_kind == "ack"
        else f"{correlation_id}.execution_boundary_ack.json"
    )
    opposite_archived_response_path = archive_dir / opposite_response_name
    if opposite_archived_response_path.exists():
        raise ValueError("archive_conflict_existing_opposite_response_artifact")

    archived_handoff_request_path.write_text(
        resolved_handoff_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    archived_pickup_receipt_path.write_text(
        pickup_receipt_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    archived_response_artifact_path.write_text(
        response_path.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    return LocalTransportArchiveResult(
        handoff_request_path=str(resolved_handoff_path),
        pickup_receipt_path=str(pickup_receipt_path),
        response_artifact_path=str(response_path.resolve()),
        archive_dir=str(archive_dir),
        archived_handoff_request_path=str(archived_handoff_request_path),
        archived_pickup_receipt_path=str(archived_pickup_receipt_path),
        archived_response_artifact_path=str(archived_response_artifact_path),
        response_kind=response_kind,
        correlation_id=correlation_id,
        attempt_id=attempt_id,
        idempotency_key=idempotency_key,
    )
