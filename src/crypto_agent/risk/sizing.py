from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.config import Settings
from crypto_agent.portfolio.exposures import gross_exposure_notional, symbol_exposure_notional
from crypto_agent.portfolio.positions import PortfolioState
from crypto_agent.types import TradeProposal


class SizingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    quantity: float = Field(gt=0)
    approved_notional_usd: float = Field(gt=0)
    risk_amount_usd: float = Field(gt=0)
    stop_distance: float = Field(gt=0)


def size_trade_proposal(
    proposal: TradeProposal,
    portfolio: PortfolioState,
    settings: Settings,
    notional_multiplier: float = 1.0,
) -> SizingResult:
    if not 1.0 <= notional_multiplier <= 1.5:
        raise ValueError("Sizing notional multiplier must be between 1.0 and 1.5.")

    stop_distance = abs(proposal.entry_reference - proposal.stop_price)
    if stop_distance <= 0:
        raise ValueError("Proposal stop distance must be positive for sizing.")

    risk_amount_usd = portfolio.equity_usd * settings.risk.risk_per_trade_fraction
    initial_quantity = risk_amount_usd / stop_distance
    initial_notional = initial_quantity * proposal.entry_reference * notional_multiplier

    max_symbol_notional = max(
        0.0,
        (settings.risk.max_symbol_gross_exposure * portfolio.equity_usd)
        - symbol_exposure_notional(portfolio, proposal.symbol),
    )
    max_portfolio_notional = max(
        0.0,
        (settings.risk.max_portfolio_gross_exposure * portfolio.equity_usd)
        - gross_exposure_notional(portfolio),
    )
    max_cash_notional = portfolio.available_cash_usd * settings.risk.max_leverage

    approved_notional_usd = min(
        initial_notional,
        max_symbol_notional,
        max_portfolio_notional,
        max_cash_notional,
    )
    if approved_notional_usd <= 0:
        raise ValueError("No risk capacity available for sizing.")

    quantity = approved_notional_usd / proposal.entry_reference
    return SizingResult(
        quantity=quantity,
        approved_notional_usd=approved_notional_usd,
        risk_amount_usd=risk_amount_usd,
        stop_distance=stop_distance,
    )
