from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LocalTransportPickupReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["37A.v1"] = "37A.v1"
    producer_system: Literal["polymarket-arb"] = "polymarket-arb"
    consumer_system: Literal["cryp"] = "cryp"
    correlation_id: str
    idempotency_key: str
    pickup_status: Literal["picked_up_for_local_execution_review"] = (
        "picked_up_for_local_execution_review"
    )
    picked_up_at_epoch_ns: int = Field(ge=0)
    pickup_operator: str
    source_handoff_request_path: str


class LocalTransportPickupResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_kind: Literal["local_transport_pickup_receipt_result"] = (
        "local_transport_pickup_receipt_result"
    )
    status: Literal["picked_up_for_local_execution_review"] = "picked_up_for_local_execution_review"
    handoff_request_path: str
    pickup_receipt_path: str
    correlation_id: str
    attempt_id: str
    idempotency_key: str
    pickup_operator: str
    picked_up_at_epoch_ns: int = Field(ge=0)


def read_handoff_request(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"handoff_request_invalid_json:{path}") from exc
    if not isinstance(raw, dict):
        raise ValueError("handoff_request_invalid_json_object")
    return raw


def _require_non_empty_str(
    payload: dict[str, Any],
    *,
    field_name: str,
) -> str:
    value = payload.get(field_name)
    if value is None:
        raise ValueError(f"handoff_request_missing_required_field:{field_name}")
    if not isinstance(value, str):
        raise ValueError(f"handoff_request_invalid_field_type:{field_name}")
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"handoff_request_invalid_field_empty:{field_name}")
    return normalized


def validated_transport_fields(payload: dict[str, Any]) -> tuple[str, str]:
    contract_version = _require_non_empty_str(payload, field_name="contract_version")
    producer_system = _require_non_empty_str(payload, field_name="producer_system")
    consumer_system = _require_non_empty_str(payload, field_name="consumer_system")
    correlation_id = _require_non_empty_str(payload, field_name="correlation_id")
    idempotency_key = _require_non_empty_str(payload, field_name="idempotency_key")

    if contract_version != "37A.v1":
        raise ValueError("handoff_request_contract_version_mismatch")
    if producer_system != "polymarket-arb":
        raise ValueError("handoff_request_producer_system_mismatch")
    if consumer_system != "cryp":
        raise ValueError("handoff_request_consumer_system_mismatch")

    return correlation_id, idempotency_key


def canonical_transport_context(handoff_request_path: Path) -> tuple[str, str, Path]:
    if handoff_request_path.name != "handoff_request.json":
        raise ValueError("handoff_request_path_invalid_filename")

    attempt_dir = handoff_request_path.parent
    correlation_dir = attempt_dir.parent
    inbound_dir = correlation_dir.parent
    transport_root = inbound_dir.parent

    if inbound_dir.name != "inbound":
        raise ValueError("handoff_request_path_not_inbound_tree")
    attempt_id = attempt_dir.name.strip()
    correlation_id_from_path = correlation_dir.name.strip()
    if not attempt_id:
        raise ValueError("handoff_request_path_missing_attempt_id")
    if not correlation_id_from_path:
        raise ValueError("handoff_request_path_missing_correlation_id")

    return correlation_id_from_path, attempt_id, transport_root


def write_local_transport_pickup_receipt(
    *,
    handoff_request_path: Path,
    pickup_operator: str,
    picked_up_at_epoch_ns: int,
) -> LocalTransportPickupResult:
    resolved_handoff_path = handoff_request_path.resolve()
    payload = read_handoff_request(resolved_handoff_path)
    correlation_id, idempotency_key = validated_transport_fields(payload)
    correlation_id_from_path, attempt_id, transport_root = canonical_transport_context(
        resolved_handoff_path
    )
    normalized_operator = pickup_operator.strip()
    if not normalized_operator:
        raise ValueError("pickup_operator_empty")
    if correlation_id != correlation_id_from_path:
        raise ValueError("handoff_request_correlation_id_path_mismatch")

    pickup_receipt_path = (
        transport_root / "pickup" / correlation_id / attempt_id / "cryp_pickup_receipt.json"
    ).resolve()

    receipt = LocalTransportPickupReceipt(
        correlation_id=correlation_id,
        idempotency_key=idempotency_key,
        picked_up_at_epoch_ns=picked_up_at_epoch_ns,
        pickup_operator=normalized_operator,
        source_handoff_request_path=str(resolved_handoff_path),
    )

    pickup_receipt_path.parent.mkdir(parents=True, exist_ok=True)
    pickup_receipt_path.write_text(
        json.dumps(receipt.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    return LocalTransportPickupResult(
        handoff_request_path=str(resolved_handoff_path),
        pickup_receipt_path=str(pickup_receipt_path),
        correlation_id=correlation_id,
        attempt_id=attempt_id,
        idempotency_key=idempotency_key,
        pickup_operator=normalized_operator,
        picked_up_at_epoch_ns=picked_up_at_epoch_ns,
    )
