from __future__ import annotations

from crypto_agent.market_data.models import Candle


def compute_average_volume(candles: list[Candle]) -> float:
    if not candles:
        raise ValueError("At least one candle is required to compute average volume.")
    return sum(candle.volume for candle in candles) / len(candles)


def compute_average_dollar_volume(candles: list[Candle]) -> float:
    if not candles:
        raise ValueError("At least one candle is required to compute average dollar volume.")
    total = 0.0
    for candle in candles:
        typical_price = (candle.high + candle.low + candle.close) / 3
        total += typical_price * candle.volume
    return total / len(candles)


def compute_average_range_bps(candles: list[Candle]) -> float:
    if not candles:
        raise ValueError("At least one candle is required to compute range in basis points.")

    total_bps = 0.0
    for candle in candles:
        mid_price = (candle.high + candle.low) / 2
        total_bps += ((candle.high - candle.low) / mid_price) * 10_000
    return total_bps / len(candles)
