from __future__ import annotations

from math import sqrt

from crypto_agent.enums import Side
from crypto_agent.features.models import FeatureSnapshot
from crypto_agent.market_data.models import Candle
from crypto_agent.regime.base import RegimeAssessment, RegimeLabel
from crypto_agent.signals.base import MeanReversionSignalConfig
from crypto_agent.types import ExecutionConstraints, TradeProposal


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stddev(values: list[float]) -> float:
    mean_value = _mean(values)
    variance = sum((value - mean_value) ** 2 for value in values) / len(values)
    return sqrt(variance)


def generate_mean_reversion_proposal(
    candles: list[Candle],
    features: FeatureSnapshot,
    regime: RegimeAssessment,
    config: MeanReversionSignalConfig | None = None,
) -> TradeProposal | None:
    thresholds = config or MeanReversionSignalConfig()

    if len(candles) < thresholds.lookback_candles + 1:
        raise ValueError("Not enough candles to evaluate mean reversion signal.")
    if regime.label is not RegimeLabel.RANGE:
        return None
    if features.average_dollar_volume < thresholds.min_average_dollar_volume:
        return None
    if features.realized_volatility > thresholds.max_realized_volatility:
        return None
    if features.atr_pct > thresholds.max_atr_pct:
        return None

    trigger_candle = candles[-1]
    reference_window = candles[-(thresholds.lookback_candles + 1) : -1]
    reference_closes = [candle.close for candle in reference_window]
    mean_close = _mean(reference_closes)
    stddev_close = _stddev(reference_closes)
    if stddev_close == 0:
        return None

    zscore = (trigger_candle.close - mean_close) / stddev_close
    atr = features.atr

    if zscore >= thresholds.zscore_entry_threshold:
        entry_reference = trigger_candle.close
        return TradeProposal(
            strategy_id=thresholds.strategy_id,
            symbol=features.symbol,
            side=Side.SELL,
            confidence=min(1.0, regime.confidence + 0.1),
            thesis="Price stretched materially above the recent range mean in a range regime.",
            entry_reference=entry_reference,
            stop_price=entry_reference + (atr * thresholds.stop_atr_multiple),
            take_profit_price=mean_close,
            expected_holding_period="2h",
            invalidation_reason=(
                "Price continues extending above the stretch zone or regime shifts."
            ),
            supporting_features={
                "zscore": zscore,
                "average_dollar_volume": features.average_dollar_volume,
                "realized_volatility": features.realized_volatility,
                "atr_pct": features.atr_pct,
                "reference_mean_close": mean_close,
                "reference_stddev_close": stddev_close,
                "reference_window_size": len(reference_window),
            },
            regime_context={
                "label": regime.label.value,
                "confidence": regime.confidence,
            },
            execution_constraints=ExecutionConstraints(
                max_slippage_bps=10.0,
                max_spread_bps=8.0,
            ),
        )

    if zscore <= -thresholds.zscore_entry_threshold:
        entry_reference = trigger_candle.close
        return TradeProposal(
            strategy_id=thresholds.strategy_id,
            symbol=features.symbol,
            side=Side.BUY,
            confidence=min(1.0, regime.confidence + 0.1),
            thesis="Price stretched materially below the recent range mean in a range regime.",
            entry_reference=entry_reference,
            stop_price=entry_reference - (atr * thresholds.stop_atr_multiple),
            take_profit_price=mean_close,
            expected_holding_period="2h",
            invalidation_reason=(
                "Price continues extending below the stretch zone or regime shifts."
            ),
            supporting_features={
                "zscore": zscore,
                "average_dollar_volume": features.average_dollar_volume,
                "realized_volatility": features.realized_volatility,
                "atr_pct": features.atr_pct,
                "reference_mean_close": mean_close,
                "reference_stddev_close": stddev_close,
                "reference_window_size": len(reference_window),
            },
            regime_context={
                "label": regime.label.value,
                "confidence": regime.confidence,
            },
            execution_constraints=ExecutionConstraints(
                max_slippage_bps=10.0,
                max_spread_bps=8.0,
            ),
        )

    return None
