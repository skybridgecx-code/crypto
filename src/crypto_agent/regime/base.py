from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.features.models import FeatureSnapshot


class RegimeLabel(StrEnum):
    TREND = "trend"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    LIQUIDITY_STRESS = "liquidity_stress"


class RegimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trend_return_threshold: float = Field(default=0.004, ge=0)
    trend_range_bps_threshold: float = Field(default=12.0, ge=0)
    high_volatility_threshold: float = Field(default=0.005, ge=0)
    high_atr_pct_threshold: float = Field(default=0.005, ge=0)
    liquidity_stress_dollar_volume_threshold: float = Field(default=5_000_000.0, ge=0)


class RegimeAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    as_of: datetime
    label: RegimeLabel
    confidence: float = Field(ge=0, le=1)
    reasons: list[str] = Field(default_factory=list)
    supporting_metrics: dict[str, float]
    features: FeatureSnapshot

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
