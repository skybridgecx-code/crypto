from __future__ import annotations

from math import sqrt

from crypto_agent.market_data.models import Candle


def compute_true_ranges(candles: list[Candle]) -> list[float]:
    if len(candles) < 2:
        raise ValueError("At least two candles are required to compute true range.")

    true_ranges: list[float] = []
    previous_close = candles[0].close
    for candle in candles:
        true_range = max(
            candle.high - candle.low,
            abs(candle.high - previous_close),
            abs(candle.low - previous_close),
        )
        true_ranges.append(true_range)
        previous_close = candle.close

    return true_ranges


def compute_atr(candles: list[Candle]) -> float:
    true_ranges = compute_true_ranges(candles)
    return sum(true_ranges) / len(true_ranges)


def compute_realized_volatility(candles: list[Candle]) -> float:
    if len(candles) < 2:
        raise ValueError("At least two candles are required to compute realized volatility.")

    returns: list[float] = []
    previous_close = candles[0].close
    for candle in candles[1:]:
        returns.append((candle.close - previous_close) / previous_close)
        previous_close = candle.close

    mean_return = sum(returns) / len(returns)
    variance = sum((value - mean_return) ** 2 for value in returns) / len(returns)
    return sqrt(variance)
