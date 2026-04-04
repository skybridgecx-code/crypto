from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from crypto_agent.enums import EventType
from crypto_agent.events.envelope import EventEnvelope
from crypto_agent.execution.models import ExecutionReport
from crypto_agent.risk.checks import RiskCheckResult
from crypto_agent.types import TradeProposal


class AppendOnlyJournal:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, event: EventEnvelope) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n")

    def append_many(self, events: list[EventEnvelope]) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n")

    def read_all(self) -> list[EventEnvelope]:
        if not self.path.exists():
            return []

        events: list[EventEnvelope] = []
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                content = line.strip()
                if not content:
                    continue
                events.append(EventEnvelope.model_validate(json.loads(content)))
        return events


def _event_timestamp_for_report(report: ExecutionReport) -> datetime:
    if report.fills:
        return report.fills[-1].timestamp
    return datetime.now(UTC)


def _serializable_payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    return dict(payload)


def build_execution_events(
    run_id: str,
    proposal: TradeProposal,
    risk_result: RiskCheckResult,
    report: ExecutionReport | None = None,
) -> list[EventEnvelope]:
    events: list[EventEnvelope] = [
        EventEnvelope(
            event_type=EventType.TRADE_PROPOSAL_CREATED,
            source="signal_engine",
            run_id=run_id,
            strategy_id=proposal.strategy_id,
            symbol=proposal.symbol,
            mode=risk_result.decision.mode,
            payload=_serializable_payload(proposal),
        ),
        EventEnvelope(
            event_type=EventType.RISK_CHECK_COMPLETED,
            source="risk_engine",
            run_id=run_id,
            strategy_id=proposal.strategy_id,
            symbol=proposal.symbol,
            mode=risk_result.decision.mode,
            payload={
                "decision": _serializable_payload(risk_result.decision),
                "sizing": _serializable_payload(risk_result.sizing)
                if risk_result.sizing is not None
                else None,
                "rejection_reasons": risk_result.rejection_reasons,
            },
        ),
        EventEnvelope(
            event_type=EventType.POLICY_DECISION_MADE,
            source="policy_guardrails",
            run_id=run_id,
            strategy_id=proposal.strategy_id,
            symbol=proposal.symbol,
            mode=risk_result.decision.mode,
            payload=_serializable_payload(risk_result.decision),
        ),
    ]

    if report is None:
        return events

    events.append(
        EventEnvelope(
            event_type=EventType.ORDER_INTENT_CREATED,
            source="execution_engine",
            run_id=run_id,
            strategy_id=proposal.strategy_id,
            symbol=proposal.symbol,
            mode=report.intent.mode,
            payload=_serializable_payload(report.intent),
        )
    )
    events.append(
        EventEnvelope(
            event_type=EventType.ORDER_SUBMITTED,
            source="execution_engine",
            run_id=run_id,
            strategy_id=proposal.strategy_id,
            symbol=proposal.symbol,
            mode=report.intent.mode,
            timestamp=_event_timestamp_for_report(report),
            payload={
                "intent": _serializable_payload(report.intent),
                "estimated_slippage_bps": report.estimated_slippage_bps,
            },
        )
    )

    if report.rejected:
        events.append(
            EventEnvelope(
                event_type=EventType.ORDER_REJECTED,
                source="execution_engine",
                run_id=run_id,
                strategy_id=proposal.strategy_id,
                symbol=proposal.symbol,
                mode=report.intent.mode,
                timestamp=_event_timestamp_for_report(report),
                payload={
                    "intent": _serializable_payload(report.intent),
                    "reject_reason": report.reject_reason,
                    "estimated_slippage_bps": report.estimated_slippage_bps,
                },
            )
        )
        return events

    for fill in report.fills:
        events.append(
            EventEnvelope(
                event_type=EventType.ORDER_FILLED,
                source="execution_engine",
                run_id=run_id,
                strategy_id=proposal.strategy_id,
                symbol=proposal.symbol,
                mode=report.intent.mode,
                timestamp=fill.timestamp,
                payload=_serializable_payload(fill),
            )
        )

    return events


def build_review_packet(events: list[EventEnvelope]) -> dict[str, Any]:
    return {
        "event_count": len(events),
        "event_types": [event.event_type.value for event in events],
        "filled_event_count": sum(
            1 for event in events if event.event_type is EventType.ORDER_FILLED
        ),
        "rejected_event_count": sum(
            1 for event in events if event.event_type is EventType.ORDER_REJECTED
        ),
    }
