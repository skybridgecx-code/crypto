from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.market_data.models import Candle, OrderBookSnapshot
from crypto_agent.market_data.venue_constraints import (
    VenueConstraintRegistry,
    VenueSymbolConstraints,
)


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp fields must be timezone-aware")
    return value.astimezone(UTC)


class LiveFeedHealth(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["healthy", "stale", "degraded"]
    observed_at: datetime
    last_success_at: datetime | None = None
    last_candle_close_time: datetime | None = None
    consecutive_failure_count: int = Field(default=0, ge=0)
    stale_after_seconds: int = Field(gt=0)
    message: str | None = None
    recovered: bool = False

    @field_validator("observed_at", "last_success_at", "last_candle_close_time")
    @classmethod
    def normalize_datetimes(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_timestamp(value)


class LiveMarketState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str
    symbol: str
    interval: str
    polled_at: datetime
    candles: list[Candle] = Field(default_factory=list)
    order_book: OrderBookSnapshot
    constraints: VenueSymbolConstraints
    constraint_registry: VenueConstraintRegistry
    feed_health: LiveFeedHealth

    @field_validator("polled_at")
    @classmethod
    def normalize_polled_at(cls, value: datetime) -> datetime:
        return _normalize_timestamp(value)
