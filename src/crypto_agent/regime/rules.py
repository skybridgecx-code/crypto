from __future__ import annotations

from crypto_agent.features.models import FeatureSnapshot
from crypto_agent.regime.base import RegimeAssessment, RegimeConfig, RegimeLabel


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, value))


def classify_regime(
    features: FeatureSnapshot,
    config: RegimeConfig | None = None,
) -> RegimeAssessment:
    thresholds = config or RegimeConfig()
    reasons: list[str] = []

    if features.average_dollar_volume < thresholds.liquidity_stress_dollar_volume_threshold:
        reasons.append("average_dollar_volume_below_threshold")
        label = RegimeLabel.LIQUIDITY_STRESS
        confidence = _clamp_confidence(
            1
            - (features.average_dollar_volume / thresholds.liquidity_stress_dollar_volume_threshold)
        )
    elif (
        features.realized_volatility >= thresholds.high_volatility_threshold
        or features.atr_pct >= thresholds.high_atr_pct_threshold
    ):
        reasons.append("volatility_above_threshold")
        label = RegimeLabel.HIGH_VOLATILITY
        confidence = _clamp_confidence(
            max(
                features.realized_volatility / thresholds.high_volatility_threshold,
                features.atr_pct / thresholds.high_atr_pct_threshold,
            )
            - 1
        )
    elif (
        abs(features.momentum_return) >= thresholds.trend_return_threshold
        and features.average_range_bps >= thresholds.trend_range_bps_threshold
    ):
        reasons.append("momentum_and_range_support_trend")
        label = RegimeLabel.TREND
        confidence = _clamp_confidence(
            max(
                abs(features.momentum_return) / thresholds.trend_return_threshold,
                features.average_range_bps / thresholds.trend_range_bps_threshold,
            )
            - 1
        )
    else:
        reasons.append("momentum_and_volatility_within_range_thresholds")
        label = RegimeLabel.RANGE
        confidence = _clamp_confidence(
            1
            - max(
                abs(features.momentum_return) / max(thresholds.trend_return_threshold, 1e-9),
                features.realized_volatility / max(thresholds.high_volatility_threshold, 1e-9),
            )
        )

    return RegimeAssessment(
        symbol=features.symbol,
        as_of=features.as_of,
        label=label,
        confidence=confidence,
        reasons=reasons,
        supporting_metrics={
            "momentum_return": features.momentum_return,
            "realized_volatility": features.realized_volatility,
            "atr_pct": features.atr_pct,
            "average_dollar_volume": features.average_dollar_volume,
            "average_range_bps": features.average_range_bps,
        },
        features=features,
    )
