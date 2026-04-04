from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class BreakoutSignalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = "breakout_v1"
    lookback_candles: int = Field(default=3, ge=2)
    min_momentum_return: float = Field(default=0.003, ge=0)
    stop_atr_multiple: float = Field(default=1.0, gt=0)
    take_profit_atr_multiple: float = Field(default=2.0, gt=0)
    min_average_dollar_volume: float = Field(default=5_000_000.0, ge=0)
    max_average_range_bps: float = Field(default=200.0, ge=0)


class MeanReversionSignalConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str = "mean_reversion_v1"
    lookback_candles: int = Field(default=4, ge=3)
    zscore_entry_threshold: float = Field(default=2.0, gt=0)
    stop_atr_multiple: float = Field(default=1.0, gt=0)
    min_average_dollar_volume: float = Field(default=5_000_000.0, ge=0)
    max_realized_volatility: float = Field(default=0.002, ge=0)
    max_atr_pct: float = Field(default=0.002, ge=0)
