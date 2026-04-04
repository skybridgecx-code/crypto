from pathlib import Path

from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.regime.base import RegimeConfig, RegimeLabel
from crypto_agent.regime.rules import classify_regime

FIXTURES_DIR = Path("tests/fixtures")


def test_classify_regime_detects_trend_from_replay_fixture() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_trend.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)

    assessment = classify_regime(features)

    assert assessment.label is RegimeLabel.TREND
    assert "momentum_and_range_support_trend" in assessment.reasons


def test_classify_regime_detects_range_from_replay_fixture() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_range.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)

    assessment = classify_regime(features)

    assert assessment.label is RegimeLabel.RANGE


def test_classify_regime_detects_high_volatility_from_replay_fixture() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_high_volatility.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)

    assessment = classify_regime(features)

    assert assessment.label is RegimeLabel.HIGH_VOLATILITY


def test_classify_regime_detects_liquidity_stress_from_replay_fixture() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_liquidity_stress.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)

    assessment = classify_regime(
        features,
        config=RegimeConfig(liquidity_stress_dollar_volume_threshold=1_000_000.0),
    )

    assert assessment.label is RegimeLabel.LIQUIDITY_STRESS
