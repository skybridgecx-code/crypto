from pathlib import Path

import pytest

from crypto_agent.market_data.replay import assess_candle_quality, load_candle_replay, load_jsonl

FIXTURES_DIR = Path("tests/fixtures")


def test_load_candle_replay_reads_valid_fixture() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_valid.jsonl")

    assert len(candles) == 3
    assert candles[0].symbol == "BTCUSDT"


def test_assess_candle_quality_detects_gap() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_gap.jsonl")

    issues = assess_candle_quality(candles, expected_interval_seconds=60)

    assert len(issues) == 1
    assert issues[0].code == "gap_detected"


def test_assess_candle_quality_detects_non_monotonic_timestamps() -> None:
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_non_monotonic.jsonl")

    issues = assess_candle_quality(candles, expected_interval_seconds=60)

    assert len(issues) == 1
    assert issues[0].code == "non_monotonic_timestamp"


def test_load_jsonl_rejects_invalid_json(tmp_path: Path) -> None:
    replay_file = tmp_path / "invalid.jsonl"
    replay_file.write_text("{not-json}\n", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid JSON on line 1"):
        load_jsonl(replay_file, model=object)  # type: ignore[arg-type]
