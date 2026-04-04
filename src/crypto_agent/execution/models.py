from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.types import FillEvent, OrderIntent


class PaperExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_notional_usd: float = Field(default=10.0, ge=0)
    quantity_step: float = Field(default=0.000001, gt=0)
    price_tick: float = Field(default=0.01, gt=0)
    fee_bps: float = Field(default=2.0, ge=0)
    base_slippage_bps: float = Field(default=0.5, ge=0)
    partial_fill_notional_threshold: float = Field(default=10_000.0, gt=0)
    partial_fill_fraction: float = Field(default=0.6, gt=0, lt=1)


class ExecutionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: OrderIntent
    fills: list[FillEvent] = Field(default_factory=list)
    rejected: bool = False
    reject_reason: str | None = None
    estimated_slippage_bps: float = Field(default=0.0, ge=0)
