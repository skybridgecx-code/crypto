from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class LiveReadinessStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    updated_at: datetime
    status: Literal["ready", "not_ready"] = "ready"
    limited_live_gate_status: Literal["not_ready", "ready_for_review"] = "not_ready"
    note: str | None = None
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


def default_live_readiness_status(
    *,
    runtime_id: str,
    updated_at: datetime,
) -> LiveReadinessStatus:
    return LiveReadinessStatus(runtime_id=runtime_id, updated_at=updated_at)
