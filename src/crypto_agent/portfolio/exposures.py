from __future__ import annotations

from crypto_agent.portfolio.positions import PortfolioState


def gross_exposure_notional(portfolio: PortfolioState) -> float:
    return sum(position.notional_usd() for position in portfolio.positions)


def gross_exposure_ratio(portfolio: PortfolioState) -> float:
    return gross_exposure_notional(portfolio) / portfolio.equity_usd


def symbol_exposure_notional(portfolio: PortfolioState, symbol: str) -> float:
    normalized_symbol = symbol.strip().upper()
    return sum(
        position.notional_usd()
        for position in portfolio.positions
        if position.symbol == normalized_symbol
    )


def symbol_exposure_ratio(portfolio: PortfolioState, symbol: str) -> float:
    return symbol_exposure_notional(portfolio, symbol) / portfolio.equity_usd


def open_position_count(portfolio: PortfolioState) -> int:
    return len(portfolio.positions)
