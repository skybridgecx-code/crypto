from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.events.envelope import EventEnvelope
from crypto_agent.execution.models import ExecutionReport


class HealthSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    generated_at: datetime
    total_events: int = Field(ge=0)
    rejected_orders: int = Field(ge=0)
    partial_fill_events: int = Field(ge=0)
    filled_quantity: float = Field(ge=0)
    rejected_quantity: float = Field(ge=0)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("generated_at must be timezone-aware")
        return value.astimezone(UTC)


def build_health_snapshot(
    run_id: str,
    events: list[EventEnvelope],
    execution_reports: list[ExecutionReport],
) -> HealthSnapshot:
    rejected_orders = sum(1 for report in execution_reports if report.rejected)
    partial_fill_events = sum(
        1
        for report in execution_reports
        for fill in report.fills
        if fill.status.value == "partially_filled"
    )
    filled_quantity = sum(fill.quantity for report in execution_reports for fill in report.fills)
    rejected_quantity = sum(
        report.intent.quantity for report in execution_reports if report.rejected
    )

    return HealthSnapshot(
        run_id=run_id,
        generated_at=datetime.now(UTC),
        total_events=len(events),
        rejected_orders=rejected_orders,
        partial_fill_events=partial_fill_events,
        filled_quantity=filled_quantity,
        rejected_quantity=rejected_quantity,
    )
