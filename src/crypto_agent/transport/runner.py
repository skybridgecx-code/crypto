from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.transport.archive import write_local_transport_archive
from crypto_agent.transport.boundary_response import write_local_transport_boundary_response
from crypto_agent.transport.pickup import (
    canonical_transport_context,
    read_handoff_request,
    validated_transport_fields,
    write_local_transport_pickup_receipt,
)


class LocalTransportOneShotStepState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_kind: Literal["local_transport_one_shot_step_state"] = (
        "local_transport_one_shot_step_state"
    )
    handoff_request_path: str
    correlation_id: str
    attempt_id: str
    response_kind_requested: Literal["ack", "reject"]
    pickup_step_state: Literal["not_started", "succeeded", "failed"]
    boundary_response_step_state: Literal["not_started", "succeeded", "failed"]
    archive_step_state: Literal["not_started", "succeeded", "failed"]
    final_outcome: Literal["succeeded", "failed"]
    final_status: Literal[
        "accepted_for_local_execution_review",
        "rejected_for_local_execution_review",
        "failed_before_boundary_response",
        "failed_after_boundary_response",
    ]
    pickup_receipt_path: str | None = None
    response_artifact_path: str | None = None
    archive_dir: str | None = None
    step_state_artifact_path: str
    error_code: str | None = None
    error_message: str | None = None


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
    step_state_artifact_path: str


def _write_step_state_artifact(
    *,
    state: LocalTransportOneShotStepState,
) -> None:
    step_state_path = Path(state.step_state_artifact_path)
    step_state_path.parent.mkdir(parents=True, exist_ok=True)
    step_state_path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


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
    resolved_handoff_path = handoff_request_path.resolve()
    correlation_id_from_path, attempt_id, transport_root = canonical_transport_context(
        resolved_handoff_path
    )
    step_state_path = (
        transport_root
        / "state"
        / correlation_id_from_path
        / attempt_id
        / "cryp_transport_run_once_step_state.json"
    ).resolve()

    step_state = LocalTransportOneShotStepState(
        handoff_request_path=str(resolved_handoff_path),
        correlation_id=correlation_id_from_path,
        attempt_id=attempt_id,
        response_kind_requested=response_kind,
        pickup_step_state="not_started",
        boundary_response_step_state="not_started",
        archive_step_state="not_started",
        final_outcome="failed",
        final_status="failed_before_boundary_response",
        step_state_artifact_path=str(step_state_path),
    )

    try:
        handoff_payload = read_handoff_request(resolved_handoff_path)
        correlation_id_from_payload, _ = validated_transport_fields(handoff_payload)
        if correlation_id_from_payload != correlation_id_from_path:
            raise ValueError("handoff_request_correlation_id_path_mismatch")

        pickup_result = write_local_transport_pickup_receipt(
            handoff_request_path=resolved_handoff_path,
            pickup_operator=pickup_operator,
            picked_up_at_epoch_ns=picked_up_at_epoch_ns,
        )
        step_state.pickup_step_state = "succeeded"
        step_state.pickup_receipt_path = pickup_result.pickup_receipt_path

        boundary_result = write_local_transport_boundary_response(
            handoff_request_path=resolved_handoff_path,
            response_kind=response_kind,
            responded_at_epoch_ns=responded_at_epoch_ns,
            reason_codes=reason_codes,
            validation_error=validation_error,
        )
        step_state.boundary_response_step_state = "succeeded"
        step_state.response_artifact_path = boundary_result.response_artifact_path
        step_state.final_status = boundary_result.status

        archive_result = write_local_transport_archive(handoff_request_path=resolved_handoff_path)
        step_state.archive_step_state = "succeeded"
        step_state.archive_dir = archive_result.archive_dir
        step_state.final_outcome = "succeeded"

        _write_step_state_artifact(state=step_state)
    except ValueError as exc:
        if step_state.pickup_step_state == "not_started":
            step_state.pickup_step_state = "failed"
            step_state.final_status = "failed_before_boundary_response"
        elif step_state.boundary_response_step_state == "not_started":
            step_state.boundary_response_step_state = "failed"
            step_state.final_status = "failed_before_boundary_response"
        else:
            step_state.archive_step_state = "failed"
            step_state.final_status = "failed_after_boundary_response"
        step_state.error_code = str(exc)
        step_state.error_message = str(exc)
        _write_step_state_artifact(state=step_state)
        raise

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
        step_state_artifact_path=str(step_state_path),
    )
