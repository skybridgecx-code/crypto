from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FeatureSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    interval: str
    as_of: datetime
    lookback_periods: int = Field(ge=2)
    momentum_return: float
    realized_volatility: float = Field(ge=0)
    atr: float = Field(ge=0)
    atr_pct: float = Field(ge=0)
    average_volume: float = Field(ge=0)
    average_dollar_volume: float = Field(ge=0)
    average_range_bps: float = Field(ge=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("as_of")
    @classmethod
    def normalize_as_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("as_of must be timezone-aware")
        return value.astimezone(UTC)
