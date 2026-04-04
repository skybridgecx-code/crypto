from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.enums import EventType, Mode
from crypto_agent.ids import new_id


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(default_factory=new_id)
    event_type: EventType
    timestamp: datetime = Field(default_factory=_utc_now)
    source: str
    run_id: str
    strategy_id: str | None = None
    symbol: str | None = None
    mode: Mode
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
