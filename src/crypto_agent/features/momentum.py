from __future__ import annotations

from crypto_agent.market_data.models import Candle


def compute_momentum_return(candles: list[Candle]) -> float:
    if len(candles) < 2:
        raise ValueError("At least two candles are required to compute momentum.")

    start_close = candles[0].close
    end_close = candles[-1].close
    return (end_close - start_close) / start_close
