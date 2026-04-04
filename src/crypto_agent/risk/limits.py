from __future__ import annotations

from crypto_agent.config import Settings
from crypto_agent.portfolio.exposures import (
    gross_exposure_notional,
    open_position_count,
    symbol_exposure_notional,
)
from crypto_agent.portfolio.positions import PortfolioState
from crypto_agent.types import TradeProposal


def collect_limit_breaches(
    proposal: TradeProposal,
    portfolio: PortfolioState,
    settings: Settings,
) -> list[str]:
    reasons: list[str] = []

    if proposal.symbol not in settings.venue.allowed_symbols:
        reasons.append("symbol_not_allowed")

    if proposal.execution_constraints.max_spread_bps > settings.risk.max_spread_bps:
        reasons.append("spread_limit_exceeded")

    if proposal.execution_constraints.max_slippage_bps > settings.risk.max_expected_slippage_bps:
        reasons.append("slippage_limit_exceeded")

    if (
        portfolio.daily_realized_pnl_usd <= 0
        and abs(portfolio.daily_realized_pnl_usd) / portfolio.equity_usd
        >= settings.risk.max_daily_realized_loss
    ):
        reasons.append("daily_loss_limit_breached")

    if proposal.supporting_features.get("average_dollar_volume") is not None:
        average_dollar_volume = float(proposal.supporting_features["average_dollar_volume"])
        if average_dollar_volume < settings.risk.min_average_dollar_volume_usd:
            reasons.append("liquidity_below_threshold")

    existing_symbol_notional = symbol_exposure_notional(portfolio, proposal.symbol)
    symbol_capacity = settings.risk.max_symbol_gross_exposure * portfolio.equity_usd
    if existing_symbol_notional >= symbol_capacity:
        reasons.append("symbol_exposure_limit_reached")

    portfolio_capacity = settings.risk.max_portfolio_gross_exposure * portfolio.equity_usd
    if gross_exposure_notional(portfolio) >= portfolio_capacity:
        reasons.append("portfolio_exposure_limit_reached")

    if open_position_count(portfolio) >= settings.risk.max_open_positions:
        existing_symbols = {position.symbol for position in portfolio.positions}
        if proposal.symbol not in existing_symbols:
            reasons.append("max_open_positions_reached")

    if proposal.execution_constraints.min_notional_usd is not None:
        if proposal.execution_constraints.min_notional_usd > portfolio.available_cash_usd:
            reasons.append("insufficient_cash_for_min_notional")

    return reasons
