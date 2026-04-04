from __future__ import annotations

from crypto_agent.enums import Side
from crypto_agent.features.models import FeatureSnapshot
from crypto_agent.market_data.models import Candle
from crypto_agent.regime.base import RegimeAssessment, RegimeLabel
from crypto_agent.signals.base import BreakoutSignalConfig
from crypto_agent.types import ExecutionConstraints, TradeProposal


def generate_breakout_proposal(
    candles: list[Candle],
    features: FeatureSnapshot,
    regime: RegimeAssessment,
    config: BreakoutSignalConfig | None = None,
) -> TradeProposal | None:
    thresholds = config or BreakoutSignalConfig()

    if len(candles) < thresholds.lookback_candles + 1:
        raise ValueError("Not enough candles to evaluate breakout signal.")
    if regime.label is not RegimeLabel.TREND:
        return None
    if features.average_dollar_volume < thresholds.min_average_dollar_volume:
        return None
    if features.average_range_bps > thresholds.max_average_range_bps:
        return None

    trigger_candle = candles[-1]
    reference_window = candles[-(thresholds.lookback_candles + 1) : -1]
    reference_high = max(candle.high for candle in reference_window)
    reference_low = min(candle.low for candle in reference_window)

    if (
        trigger_candle.close > reference_high
        and features.momentum_return >= thresholds.min_momentum_return
    ):
        entry_reference = trigger_candle.close
        atr = features.atr
        return TradeProposal(
            strategy_id=thresholds.strategy_id,
            symbol=features.symbol,
            side=Side.BUY,
            confidence=min(1.0, regime.confidence + 0.15),
            thesis="Price closed above the prior breakout range with supportive trend regime.",
            entry_reference=entry_reference,
            stop_price=entry_reference - (atr * thresholds.stop_atr_multiple),
            take_profit_price=entry_reference + (atr * thresholds.take_profit_atr_multiple),
            expected_holding_period="4h",
            invalidation_reason="Price closes back below the breakout range or momentum fades.",
            supporting_features={
                "momentum_return": features.momentum_return,
                "atr": features.atr,
                "breakout_reference_high": reference_high,
                "reference_window_size": len(reference_window),
            },
            regime_context={
                "label": regime.label.value,
                "confidence": regime.confidence,
            },
            execution_constraints=ExecutionConstraints(
                max_slippage_bps=15.0,
                max_spread_bps=10.0,
            ),
        )

    if (
        trigger_candle.close < reference_low
        and features.momentum_return <= -thresholds.min_momentum_return
    ):
        entry_reference = trigger_candle.close
        atr = features.atr
        return TradeProposal(
            strategy_id=thresholds.strategy_id,
            symbol=features.symbol,
            side=Side.SELL,
            confidence=min(1.0, regime.confidence + 0.15),
            thesis="Price closed below the prior breakdown range with supportive trend regime.",
            entry_reference=entry_reference,
            stop_price=entry_reference + (atr * thresholds.stop_atr_multiple),
            take_profit_price=entry_reference - (atr * thresholds.take_profit_atr_multiple),
            expected_holding_period="4h",
            invalidation_reason=(
                "Price closes back inside the prior range or downside momentum fades."
            ),
            supporting_features={
                "momentum_return": features.momentum_return,
                "atr": features.atr,
                "breakout_reference_low": reference_low,
                "reference_window_size": len(reference_window),
            },
            regime_context={
                "label": regime.label.value,
                "confidence": regime.confidence,
            },
            execution_constraints=ExecutionConstraints(
                max_slippage_bps=15.0,
                max_spread_bps=10.0,
            ),
        )

    return None
