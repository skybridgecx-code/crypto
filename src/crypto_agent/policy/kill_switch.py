from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.config import Settings


class KillSwitchContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    consecutive_order_rejects: int = Field(default=0, ge=0)
    slippage_breach_count: int = Field(default=0, ge=0)
    drawdown_fraction: float = Field(default=0.0, ge=0, le=1)
    missing_market_data_heartbeat: bool = False
    position_mismatch: bool = False
    journal_write_failed: bool = False
    manual_halt: bool = False


class KillSwitchState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool
    reason_codes: list[str] = Field(default_factory=list)


def evaluate_kill_switch(
    context: KillSwitchContext,
    settings: Settings,
) -> KillSwitchState:
    if not settings.policy.kill_switch_enabled:
        return KillSwitchState(active=False)

    reasons: list[str] = []
    if context.manual_halt:
        reasons.append("manual_halt")
    if context.missing_market_data_heartbeat:
        reasons.append("missing_market_data_heartbeat")
    if context.position_mismatch:
        reasons.append("position_mismatch")
    if context.journal_write_failed:
        reasons.append("journal_write_failed")
    if context.consecutive_order_rejects >= settings.policy.max_consecutive_order_rejects:
        reasons.append("repeated_order_rejects")
    if context.slippage_breach_count >= settings.policy.max_slippage_breaches:
        reasons.append("slippage_breaches")
    if context.drawdown_fraction >= settings.policy.max_drawdown_fraction:
        reasons.append("drawdown_breach")

    return KillSwitchState(active=bool(reasons), reason_codes=reasons)
