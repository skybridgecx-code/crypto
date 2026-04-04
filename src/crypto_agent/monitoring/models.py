from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.types import ScalarValue


class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    severity: AlertSeverity
    message: str
    observed_at: datetime
    symbol: str | None = None
    details: dict[str, ScalarValue] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("observed_at must be timezone-aware")
        return value.astimezone(UTC)
