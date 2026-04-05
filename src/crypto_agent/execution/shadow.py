from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from crypto_agent.enums import EventType
from crypto_agent.events.journal import AppendOnlyJournal
from crypto_agent.execution.live_adapter import (
    build_shadow_ack,
    build_shadow_state,
    build_venue_order_request,
)
from crypto_agent.execution.models import (
    ExecutionRequestArtifact,
    ExecutionResultArtifact,
    ExecutionStatusArtifact,
    VenueOrderRequest,
)
from crypto_agent.market_data.live_models import LiveMarketState
from crypto_agent.market_data.venue_constraints import VenueConstraintRegistry
from crypto_agent.types import OrderIntent


def _load_market_state(path: str | Path) -> LiveMarketState:
    return LiveMarketState.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def _load_constraint_registry(path: str | Path) -> VenueConstraintRegistry:
    return VenueConstraintRegistry.model_validate(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )


def _load_order_intents(journal_path: str | Path) -> list[OrderIntent]:
    journal = AppendOnlyJournal(journal_path)
    return [
        OrderIntent.model_validate(event.payload)
        for event in journal.read_all()
        if event.event_type is EventType.ORDER_INTENT_CREATED
    ]


def _dedupe_requests(requests: list[VenueOrderRequest]) -> list[VenueOrderRequest]:
    deduped: dict[str, VenueOrderRequest] = {}
    for request in requests:
        deduped[request.client_order_id] = request
    return list(deduped.values())


def build_shadow_execution_artifacts(
    *,
    session_id: str,
    run_id: str,
    journal_path: str | Path,
    market_state_path: str | Path,
    venue_constraints_path: str | Path,
    observed_at: datetime,
) -> tuple[ExecutionRequestArtifact, ExecutionResultArtifact, ExecutionStatusArtifact]:
    market_state = _load_market_state(market_state_path)
    registry = _load_constraint_registry(venue_constraints_path)
    requests = _dedupe_requests(
        [
            build_venue_order_request(
                intent=intent,
                constraints=registry.get(intent.symbol),
                market_state=market_state,
                execution_mode="shadow",
            )
            for intent in _load_order_intents(journal_path)
        ]
    )
    results = [build_shadow_ack(request, observed_at=observed_at) for request in requests]
    statuses = [build_shadow_state(request, updated_at=observed_at) for request in requests]

    return (
        ExecutionRequestArtifact(
            run_id=run_id,
            session_id=session_id,
            execution_mode="shadow",
            request_count=len(requests),
            rejected_request_count=sum(
                1 for request in requests if request.normalization_status == "rejected"
            ),
            requests=requests,
        ),
        ExecutionResultArtifact(
            run_id=run_id,
            session_id=session_id,
            execution_mode="shadow",
            result_count=len(results),
            results=results,
        ),
        ExecutionStatusArtifact(
            run_id=run_id,
            session_id=session_id,
            execution_mode="shadow",
            status_count=len(statuses),
            terminal_status_count=len(statuses),
            statuses=statuses,
        ),
    )
