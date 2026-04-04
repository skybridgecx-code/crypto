from __future__ import annotations

from crypto_agent.features.liquidity import (
    compute_average_dollar_volume,
    compute_average_range_bps,
    compute_average_volume,
)
from crypto_agent.features.models import FeatureSnapshot
from crypto_agent.features.momentum import compute_momentum_return
from crypto_agent.features.volatility import compute_atr, compute_realized_volatility
from crypto_agent.market_data.models import Candle


def build_feature_snapshot(
    candles: list[Candle],
    lookback_periods: int,
) -> FeatureSnapshot:
    if lookback_periods < 2:
        raise ValueError("lookback_periods must be at least 2")
    if len(candles) < lookback_periods:
        raise ValueError("Not enough candles for requested lookback_periods")

    window = candles[-lookback_periods:]
    atr = compute_atr(window)
    last_close = window[-1].close

    return FeatureSnapshot(
        symbol=window[-1].symbol,
        interval=window[-1].interval,
        as_of=window[-1].close_time,
        lookback_periods=lookback_periods,
        momentum_return=compute_momentum_return(window),
        realized_volatility=compute_realized_volatility(window),
        atr=atr,
        atr_pct=atr / last_close,
        average_volume=compute_average_volume(window),
        average_dollar_volume=compute_average_dollar_volume(window),
        average_range_bps=compute_average_range_bps(window),
    )
