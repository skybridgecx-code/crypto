from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.transport.archive import write_local_transport_archive
from crypto_agent.transport.boundary_response import write_local_transport_boundary_response
from crypto_agent.transport.pickup import write_local_transport_pickup_receipt


class LocalTransportOneShotResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_kind: Literal["local_transport_one_shot_result"] = "local_transport_one_shot_result"
    status: Literal["accepted_for_local_execution_review", "rejected_for_local_execution_review"]
    handoff_request_path: str
    pickup_receipt_path: str
    response_artifact_path: str
    archive_dir: str
    archived_handoff_request_path: str
    archived_pickup_receipt_path: str
    archived_response_artifact_path: str
    correlation_id: str
    attempt_id: str
    idempotency_key: str
    response_kind: Literal["ack", "reject"]
    pickup_operator: str
    picked_up_at_epoch_ns: int = Field(ge=0)
    responded_at_epoch_ns: int = Field(ge=0)


def run_local_transport_one_shot(
    *,
    handoff_request_path: Path,
    pickup_operator: str,
    picked_up_at_epoch_ns: int,
    response_kind: Literal["ack", "reject"],
    responded_at_epoch_ns: int,
    reason_codes: list[str] | None = None,
    validation_error: str | None = None,
) -> LocalTransportOneShotResult:
    pickup_result = write_local_transport_pickup_receipt(
        handoff_request_path=handoff_request_path,
        pickup_operator=pickup_operator,
        picked_up_at_epoch_ns=picked_up_at_epoch_ns,
    )
    boundary_result = write_local_transport_boundary_response(
        handoff_request_path=handoff_request_path,
        response_kind=response_kind,
        responded_at_epoch_ns=responded_at_epoch_ns,
        reason_codes=reason_codes,
        validation_error=validation_error,
    )
    archive_result = write_local_transport_archive(handoff_request_path=handoff_request_path)

    return LocalTransportOneShotResult(
        status=boundary_result.status,
        handoff_request_path=pickup_result.handoff_request_path,
        pickup_receipt_path=pickup_result.pickup_receipt_path,
        response_artifact_path=boundary_result.response_artifact_path,
        archive_dir=archive_result.archive_dir,
        archived_handoff_request_path=archive_result.archived_handoff_request_path,
        archived_pickup_receipt_path=archive_result.archived_pickup_receipt_path,
        archived_response_artifact_path=archive_result.archived_response_artifact_path,
        correlation_id=pickup_result.correlation_id,
        attempt_id=pickup_result.attempt_id,
        idempotency_key=pickup_result.idempotency_key,
        response_kind=boundary_result.response_kind,
        pickup_operator=pickup_result.pickup_operator,
        picked_up_at_epoch_ns=pickup_result.picked_up_at_epoch_ns,
        responded_at_epoch_ns=boundary_result.responded_at_epoch_ns,
    )
