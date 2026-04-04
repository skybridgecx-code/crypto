from pathlib import Path

from crypto_agent.market_data.adapters.paper_feed import PaperFeedAdapter
from crypto_agent.market_data.router import MarketDataRouter

FIXTURES_DIR = Path("tests/fixtures")


def test_paper_feed_adapter_loads_candles_and_quality_report() -> None:
    adapter = PaperFeedAdapter()

    batch = adapter.load_candles(FIXTURES_DIR / "paper_candles_valid.jsonl", 60)

    assert len(batch.candles) == 3
    assert batch.quality_issues == []


def test_market_data_router_returns_registered_adapter() -> None:
    router = MarketDataRouter()
    adapter = PaperFeedAdapter()

    router.register(adapter)

    assert router.get("paper") is adapter
