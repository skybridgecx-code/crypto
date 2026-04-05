from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.execution.live_adapter import SandboxExecutionAdapter, build_venue_order_request
from crypto_agent.execution.models import (
    ExecutionRequestArtifact,
    ExecutionResultArtifact,
    ExecutionStatusArtifact,
    VenueExecutionAck,
    VenueOrderRequest,
    VenueOrderState,
)
from crypto_agent.execution.shadow import (
    _load_constraint_registry,
    _load_market_state,
    _load_order_intents,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _load_existing_statuses(path: str | Path) -> dict[str, VenueOrderState]:
    artifact_path = Path(path)
    if not artifact_path.exists():
        return {}
    artifact = ExecutionStatusArtifact.model_validate(
        json.loads(artifact_path.read_text(encoding="utf-8"))
    )
    return {status.client_order_id: status for status in artifact.statuses}


def _duplicate_ack(
    request: VenueOrderRequest,
    *,
    observed_at: datetime,
    existing_status: VenueOrderState,
) -> VenueExecutionAck:
    return VenueExecutionAck(
        request_id=request.request_id,
        client_order_id=request.client_order_id,
        venue=request.venue,
        execution_mode="sandbox",
        sandbox=True,
        intent_id=request.intent_id,
        status="duplicate",
        venue_order_id=existing_status.venue_order_id,
        observed_at=observed_at,
    )


def execute_sandbox_requests(
    *,
    session_id: str,
    run_id: str,
    journal_path: str | Path,
    market_state_path: str | Path,
    venue_constraints_path: str | Path,
    existing_status_path: str | Path,
    adapter: SandboxExecutionAdapter,
    observed_at: datetime,
) -> tuple[ExecutionRequestArtifact, ExecutionResultArtifact, ExecutionStatusArtifact]:
    if not adapter.sandbox:
        raise ValueError("Sandbox execution requires an adapter explicitly marked as sandbox.")

    market_state = _load_market_state(market_state_path)
    registry = _load_constraint_registry(venue_constraints_path)
    existing_statuses = _load_existing_statuses(existing_status_path)

    requests = [
        build_venue_order_request(
            intent=intent,
            constraints=registry.get(intent.symbol),
            market_state=market_state,
            execution_mode="sandbox",
        )
        for intent in _load_order_intents(journal_path)
    ]

    deduped_requests: dict[str, VenueOrderRequest] = {}
    for request in requests:
        deduped_requests[request.client_order_id] = request

    results: list[VenueExecutionAck] = []
    statuses: list[VenueOrderState] = []
    for request in deduped_requests.values():
        if request.normalization_status == "rejected":
            results.append(
                VenueExecutionAck(
                    request_id=request.request_id,
                    client_order_id=request.client_order_id,
                    venue=request.venue,
                    execution_mode="sandbox",
                    sandbox=True,
                    intent_id=request.intent_id,
                    status="rejected",
                    reject_reason=request.normalization_reject_reason,
                    observed_at=observed_at,
                )
            )
            statuses.append(
                VenueOrderState(
                    request_id=request.request_id,
                    client_order_id=request.client_order_id,
                    venue=request.venue,
                    execution_mode="sandbox",
                    sandbox=True,
                    intent_id=request.intent_id,
                    state="rejected",
                    terminal=True,
                    updated_at=observed_at,
                )
            )
            continue

        existing_status = existing_statuses.get(request.client_order_id)
        if existing_status is not None:
            results.append(
                _duplicate_ack(
                    request,
                    observed_at=observed_at,
                    existing_status=existing_status,
                )
            )
            statuses.append(existing_status)
            continue

        ack = adapter.submit_order(request)
        results.append(ack)
        if ack.status == "rejected":
            statuses.append(
                VenueOrderState(
                    request_id=request.request_id,
                    client_order_id=request.client_order_id,
                    venue=request.venue,
                    execution_mode="sandbox",
                    sandbox=True,
                    intent_id=request.intent_id,
                    venue_order_id=ack.venue_order_id,
                    state="rejected",
                    terminal=True,
                    updated_at=ack.observed_at,
                )
            )
            continue

        state = adapter.fetch_order_state(
            client_order_id=request.client_order_id,
            request=request,
        )
        if not state.terminal:
            state = adapter.cancel_order(
                client_order_id=request.client_order_id,
                request=request,
            )
        statuses.append(state)

    return (
        ExecutionRequestArtifact(
            run_id=run_id,
            session_id=session_id,
            execution_mode="sandbox",
            request_count=len(deduped_requests),
            rejected_request_count=sum(
                1
                for request in deduped_requests.values()
                if request.normalization_status == "rejected"
            ),
            requests=list(deduped_requests.values()),
        ),
        ExecutionResultArtifact(
            run_id=run_id,
            session_id=session_id,
            execution_mode="sandbox",
            result_count=len(results),
            results=results,
        ),
        ExecutionStatusArtifact(
            run_id=run_id,
            session_id=session_id,
            execution_mode="sandbox",
            status_count=len(statuses),
            terminal_status_count=sum(1 for status in statuses if status.terminal),
            statuses=statuses,
        ),
    )
