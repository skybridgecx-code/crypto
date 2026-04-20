from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.transport.pickup import (
    LocalTransportPickupReceipt,
    canonical_transport_context,
    read_handoff_request,
    validated_transport_fields,
)


class LocalTransportBoundaryResponseArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["37A.v1"] = "37A.v1"
    producer_system: Literal["polymarket-arb"] = "polymarket-arb"
    consumer_system: Literal["cryp"] = "cryp"
    artifact_kind: Literal["execution_boundary_intake_ack", "execution_boundary_intake_reject"]
    correlation_id: str
    idempotency_key: str
    submission_status: Literal[
        "accepted_for_local_execution_review",
        "rejected_for_local_execution_review",
    ]
    responded_at_epoch_ns: int = Field(ge=0)
    reason_codes: list[str] = Field(default_factory=list)
    validation_error: str | None = None
    source_handoff_request_path: str
    source_pickup_receipt_path: str


class LocalTransportBoundaryResponseResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_kind: Literal["local_transport_boundary_response_result"] = (
        "local_transport_boundary_response_result"
    )
    status: Literal["accepted_for_local_execution_review", "rejected_for_local_execution_review"]
    handoff_request_path: str
    pickup_receipt_path: str
    response_artifact_path: str
    correlation_id: str
    attempt_id: str
    idempotency_key: str
    response_kind: Literal["ack", "reject"]
    responded_at_epoch_ns: int = Field(ge=0)


def _non_empty_reason_codes(reason_codes: list[str]) -> list[str]:
    cleaned = [code.strip() for code in reason_codes if code.strip()]
    if not cleaned:
        raise ValueError("boundary_response_reject_reason_codes_required")
    return cleaned


def _load_pickup_receipt(path: Path) -> LocalTransportPickupReceipt:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"pickup_receipt_invalid_json:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("pickup_receipt_invalid_json_object")
    return LocalTransportPickupReceipt.model_validate(payload)


def _validate_pickup_matches_handoff(
    *,
    pickup_receipt: LocalTransportPickupReceipt,
    resolved_handoff_path: Path,
    correlation_id: str,
    idempotency_key: str,
) -> None:
    if pickup_receipt.correlation_id != correlation_id:
        raise ValueError("pickup_receipt_correlation_id_mismatch")
    if pickup_receipt.idempotency_key != idempotency_key:
        raise ValueError("pickup_receipt_idempotency_key_mismatch")
    if pickup_receipt.source_handoff_request_path != str(resolved_handoff_path):
        raise ValueError("pickup_receipt_source_handoff_request_path_mismatch")


def write_local_transport_boundary_response(
    *,
    handoff_request_path: Path,
    response_kind: Literal["ack", "reject"],
    responded_at_epoch_ns: int,
    reason_codes: list[str] | None = None,
    validation_error: str | None = None,
) -> LocalTransportBoundaryResponseResult:
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
    _validate_pickup_matches_handoff(
        pickup_receipt=pickup_receipt,
        resolved_handoff_path=resolved_handoff_path,
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
    )

    responses_dir = (transport_root / "responses" / correlation_id / attempt_id).resolve()
    ack_path = responses_dir / f"{correlation_id}.execution_boundary_ack.json"
    reject_path = responses_dir / f"{correlation_id}.execution_boundary_reject.json"

    if response_kind == "ack":
        if reject_path.exists():
            raise ValueError("boundary_response_conflict_existing_reject")
        artifact_path = ack_path
        artifact = LocalTransportBoundaryResponseArtifact(
            artifact_kind="execution_boundary_intake_ack",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            submission_status="accepted_for_local_execution_review",
            responded_at_epoch_ns=responded_at_epoch_ns,
            reason_codes=[],
            validation_error=None,
            source_handoff_request_path=str(resolved_handoff_path),
            source_pickup_receipt_path=str(pickup_receipt_path),
        )
    else:
        if ack_path.exists():
            raise ValueError("boundary_response_conflict_existing_ack")
        cleaned_reason_codes = _non_empty_reason_codes(reason_codes or [])
        normalized_validation_error = (validation_error or "").strip()
        if not normalized_validation_error:
            raise ValueError("boundary_response_reject_validation_error_required")
        artifact_path = reject_path
        artifact = LocalTransportBoundaryResponseArtifact(
            artifact_kind="execution_boundary_intake_reject",
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
            submission_status="rejected_for_local_execution_review",
            responded_at_epoch_ns=responded_at_epoch_ns,
            reason_codes=cleaned_reason_codes,
            validation_error=normalized_validation_error,
            source_handoff_request_path=str(resolved_handoff_path),
            source_pickup_receipt_path=str(pickup_receipt_path),
        )

    responses_dir.mkdir(parents=True, exist_ok=True)
    artifact_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return LocalTransportBoundaryResponseResult(
        status=artifact.submission_status,
        handoff_request_path=str(resolved_handoff_path),
        pickup_receipt_path=str(pickup_receipt_path),
        response_artifact_path=str(artifact_path.resolve()),
        correlation_id=correlation_id,
        attempt_id=attempt_id,
        idempotency_key=idempotency_key,
        response_kind=response_kind,
        responded_at_epoch_ns=responded_at_epoch_ns,
    )
