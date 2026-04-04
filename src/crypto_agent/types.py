from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_agent.enums import (
    FillStatus,
    LiquidityRole,
    Mode,
    OrderType,
    PolicyAction,
    Side,
    TimeInForce,
)
from crypto_agent.ids import new_id

ScalarValue = str | int | float | bool


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ExecutionConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.GTC
    min_notional_usd: float | None = Field(default=None, ge=0)
    max_spread_bps: float = Field(default=15.0, ge=0)
    max_slippage_bps: float = Field(default=20.0, ge=0)


class TradeProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(default_factory=new_id)
    strategy_id: str
    symbol: str
    side: Side
    confidence: float = Field(ge=0, le=1)
    thesis: str = Field(min_length=1)
    entry_reference: float = Field(gt=0)
    stop_price: float = Field(gt=0)
    take_profit_price: float | None = Field(default=None, gt=0)
    expected_holding_period: str = Field(min_length=1)
    invalidation_reason: str = Field(min_length=1)
    supporting_features: dict[str, ScalarValue] = Field(default_factory=dict)
    regime_context: dict[str, ScalarValue] = Field(default_factory=dict)
    execution_constraints: ExecutionConstraints = Field(default_factory=ExecutionConstraints)

    @model_validator(mode="after")
    def validate_price_levels(self) -> TradeProposal:
        if self.side is Side.BUY:
            if self.stop_price >= self.entry_reference:
                raise ValueError("buy proposals require stop_price below entry_reference")
            if (
                self.take_profit_price is not None
                and self.take_profit_price <= self.entry_reference
            ):
                raise ValueError("buy proposals require take_profit_price above entry_reference")
        else:
            if self.stop_price <= self.entry_reference:
                raise ValueError("sell proposals require stop_price above entry_reference")
            if (
                self.take_profit_price is not None
                and self.take_profit_price >= self.entry_reference
            ):
                raise ValueError("sell proposals require take_profit_price below entry_reference")
        return self


class PolicyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_id: str = Field(default_factory=new_id)
    proposal_id: str
    action: PolicyAction
    reason_codes: list[str] = Field(min_length=1)
    summary: str = Field(min_length=1)
    mode: Mode
    approved_notional_usd: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_approval_notional(self) -> PolicyDecision:
        if self.action is PolicyAction.ALLOW and self.approved_notional_usd is None:
            raise ValueError("allow decisions require approved_notional_usd")
        if self.action is not PolicyAction.ALLOW and self.approved_notional_usd is not None:
            raise ValueError("non-allow decisions cannot include approved_notional_usd")
        return self


class OrderIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_id: str = Field(default_factory=new_id)
    proposal_id: str
    symbol: str
    side: Side
    order_type: OrderType = OrderType.MARKET
    time_in_force: TimeInForce = TimeInForce.GTC
    quantity: float = Field(gt=0)
    limit_price: float | None = Field(default=None, gt=0)
    max_slippage_bps: float = Field(default=20.0, ge=0)
    reduce_only: bool = False
    mode: Mode

    @model_validator(mode="after")
    def validate_order_shape(self) -> OrderIntent:
        if self.order_type is OrderType.LIMIT and self.limit_price is None:
            raise ValueError("limit orders require limit_price")
        if self.order_type is OrderType.MARKET and self.limit_price is not None:
            raise ValueError("market orders cannot include limit_price")
        return self


class FillEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fill_id: str = Field(default_factory=new_id)
    intent_id: str
    symbol: str
    side: Side
    status: FillStatus = FillStatus.FILLED
    price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    notional_usd: float = Field(gt=0)
    fee_usd: float = Field(default=0.0, ge=0)
    liquidity_role: LiquidityRole = LiquidityRole.TAKER
    timestamp: datetime = Field(default_factory=_utc_now)
    mode: Mode

    @field_validator("timestamp")
    @classmethod
    def validate_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)
