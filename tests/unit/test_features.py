from pathlib import Path

import pytest
from crypto_agent.features.liquidity import (
    compute_average_dollar_volume,
    compute_average_range_bps,
    compute_average_volume,
)
from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.features.volatility import compute_atr, compute_realized_volatility
from crypto_agent.market_data.replay import load_candle_replay

FIXTURES_DIR = Path("tests/fixtures")


def test_build_feature_snapshot_is_deterministic_for_replay_fixture() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_trend.jsonl")

    first = build_feature_snapshot(candles, lookback_periods=4)
    second = build_feature_snapshot(candles, lookback_periods=4)

    assert first == second
    assert first.momentum_return > 0
    assert first.average_dollar_volume > 0


def test_feature_helpers_reject_insufficient_input() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_valid.jsonl")[:1]

    with pytest.raises(ValueError, match="At least two candles"):
        compute_atr(candles)
    with pytest.raises(ValueError, match="At least two candles"):
        compute_realized_volatility(candles)


def test_liquidity_helpers_compute_positive_metrics() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_range.jsonl")

    assert compute_average_volume(candles) > 0
    assert compute_average_dollar_volume(candles) > 0
    assert compute_average_range_bps(candles) > 0
