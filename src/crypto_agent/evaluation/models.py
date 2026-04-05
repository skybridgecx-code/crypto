from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.events.envelope import EventEnvelope


class EvaluationScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    event_count: int = Field(ge=0)
    proposal_count: int = Field(default=0, ge=0)
    approval_count: int = Field(default=0, ge=0)
    denial_count: int = Field(default=0, ge=0)
    halt_count: int = Field(default=0, ge=0)
    order_intent_count: int = Field(default=0, ge=0)
    orders_submitted_count: int = Field(default=0, ge=0)
    order_reject_count: int = Field(default=0, ge=0)
    fill_event_count: int = Field(default=0, ge=0)
    filled_intent_count: int = Field(default=0, ge=0)
    partial_fill_intent_count: int = Field(default=0, ge=0)
    complete_execution_count: int = Field(default=0, ge=0)
    incomplete_execution_count: int = Field(default=0, ge=0)
    average_slippage_bps: float = Field(default=0.0, ge=0)
    max_slippage_bps: float = Field(default=0.0, ge=0)
    total_fill_notional_usd: float = Field(default=0.0, ge=0)
    total_fee_usd: float = Field(default=0.0, ge=0)


class ReplayPnLSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_equity_usd: float = Field(gt=0)
    gross_realized_pnl_usd: float = 0.0
    total_fee_usd: float = Field(default=0.0, ge=0)
    net_realized_pnl_usd: float = 0.0
    ending_unrealized_pnl_usd: float = 0.0
    ending_equity_usd: float
    return_fraction: float = 0.0


class ReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventEnvelope]
    scorecard: EvaluationScorecard
    pnl: ReplayPnLSummary | None = None
