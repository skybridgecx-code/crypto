from __future__ import annotations

from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp fields must be timezone-aware")
    return value.astimezone(UTC)


def _quantize_down(value: float, step: float) -> float:
    if step <= 0:
        raise ValueError("step must be positive")
    value_decimal = Decimal(str(value))
    step_decimal = Decimal(str(step))
    normalized = (value_decimal / step_decimal).to_integral_value(rounding=ROUND_DOWN)
    return float(normalized * step_decimal)


class VenueSymbolConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str
    symbol: str
    status: str
    base_asset: str
    quote_asset: str
    tick_size: float = Field(gt=0)
    step_size: float = Field(gt=0)
    min_quantity: float = Field(ge=0)
    min_notional: float = Field(ge=0)
    raw_filters: dict[str, dict[str, str]] = Field(default_factory=dict)

    @field_validator("symbol", "base_asset", "quote_asset")
    @classmethod
    def normalize_symbol_fields(cls, value: str) -> str:
        return value.strip().upper()

    def normalize_price(self, price: float) -> float:
        if price <= 0:
            raise ValueError("price must be positive")
        return _quantize_down(price, self.tick_size)

    def normalize_quantity(self, quantity: float) -> float:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        return _quantize_down(quantity, self.step_size)

    def satisfies_min_notional(self, *, price: float, quantity: float) -> bool:
        return (price * quantity) >= self.min_notional


class VenueConstraintRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str
    updated_at: datetime
    symbol_constraints: list[VenueSymbolConstraints] = Field(default_factory=list)

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_timestamp(value)

    def get(self, symbol: str) -> VenueSymbolConstraints:
        normalized = symbol.strip().upper()
        for constraints in self.symbol_constraints:
            if constraints.symbol == normalized:
                return constraints
        raise KeyError(f"No venue constraints found for symbol '{normalized}'")
