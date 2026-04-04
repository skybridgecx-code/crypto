from __future__ import annotations

from pathlib import Path

from crypto_agent.market_data.base import MarketDataAdapter
from crypto_agent.market_data.models import ReplayBatch
from crypto_agent.market_data.replay import assess_candle_quality, load_candle_replay


class PaperFeedAdapter(MarketDataAdapter):
    @property
    def name(self) -> str:
        return "paper"

    def load_candles(self, path: str | Path, expected_interval_seconds: int) -> ReplayBatch:
        candles = load_candle_replay(path)
        quality_issues = assess_candle_quality(candles, expected_interval_seconds)
        return ReplayBatch(candles=candles, quality_issues=quality_issues)
