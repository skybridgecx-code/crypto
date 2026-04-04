from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Position(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    quantity: float
    entry_price: float = Field(gt=0)
    mark_price: float = Field(gt=0)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    def notional_usd(self) -> float:
        return abs(self.quantity * self.mark_price)


class PortfolioState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    equity_usd: float = Field(gt=0)
    available_cash_usd: float = Field(ge=0)
    daily_realized_pnl_usd: float = 0.0
    positions: list[Position] = Field(default_factory=list)
