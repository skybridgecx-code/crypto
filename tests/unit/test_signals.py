from pathlib import Path

from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.regime.base import RegimeAssessment, RegimeLabel
from crypto_agent.regime.rules import classify_regime
from crypto_agent.signals.breakout import generate_breakout_proposal
from crypto_agent.signals.mean_reversion import generate_mean_reversion_proposal

FIXTURES_DIR = Path("tests/fixtures")


def test_breakout_signal_generates_long_proposal_from_breakout_fixture() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_breakout_long.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)
    regime = classify_regime(features)

    proposal = generate_breakout_proposal(candles, features, regime)

    assert proposal is not None
    assert proposal.strategy_id == "breakout_v1"
    assert proposal.side.value == "buy"
    assert proposal.entry_reference == candles[-1].close


def test_breakout_signal_reference_window_excludes_trigger_candle() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_breakout_long.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)
    regime = classify_regime(features)

    proposal = generate_breakout_proposal(candles, features, regime)

    assert proposal is not None
    expected_reference_high = max(candle.high for candle in candles[:-1])
    assert proposal.supporting_features["breakout_reference_high"] == expected_reference_high
    assert proposal.supporting_features["breakout_reference_high"] != candles[-1].high


def test_mean_reversion_signal_generates_short_proposal_in_range_regime() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_mean_reversion_short.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=5)
    regime = classify_regime(features)

    proposal = generate_mean_reversion_proposal(candles, features, regime)

    assert regime.label is RegimeLabel.RANGE
    assert proposal is not None
    assert proposal.strategy_id == "mean_reversion_v1"
    assert proposal.side.value == "sell"
    assert proposal.take_profit_price is not None
    assert proposal.take_profit_price < proposal.entry_reference


def test_mean_reversion_signal_reference_stats_exclude_trigger_candle() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_mean_reversion_short.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=5)
    regime = classify_regime(features)

    proposal = generate_mean_reversion_proposal(candles, features, regime)

    assert proposal is not None
    reference_closes = [candle.close for candle in candles[:-1]]
    expected_mean = sum(reference_closes) / len(reference_closes)
    assert proposal.supporting_features["reference_mean_close"] == expected_mean
    assert proposal.supporting_features["reference_mean_close"] != candles[-1].close


def test_breakout_signal_returns_none_outside_trend_regime() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_breakout_long.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)
    forced_range = RegimeAssessment(
        symbol=features.symbol,
        as_of=features.as_of,
        label=RegimeLabel.RANGE,
        confidence=0.9,
        reasons=["forced_for_test"],
        supporting_metrics={"momentum_return": features.momentum_return},
        features=features,
    )

    assert generate_breakout_proposal(candles, features, forced_range) is None
