from datetime import UTC, datetime

import pytest
from crypto_agent.market_data.models import BookLevel, Candle, OrderBookSnapshot


def test_candle_normalizes_symbol_and_timestamps() -> None:
    candle = Candle(
        symbol=" btcusdt ",
        interval="1m",
        open_time=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
        close_time=datetime(2026, 4, 3, 12, 1, tzinfo=UTC),
        open=68_000.0,
        high=68_050.0,
        low=67_980.0,
        close=68_040.0,
        volume=125.0,
    )

    assert candle.symbol == "BTCUSDT"
    assert candle.open_time == datetime(2026, 4, 3, 12, 0, tzinfo=UTC)


def test_order_book_snapshot_rejects_crossed_book() -> None:
    with pytest.raises(ValueError, match="best bid must be lower than best ask"):
        OrderBookSnapshot(
            symbol="BTCUSDT",
            timestamp=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
            bids=[BookLevel(price=68_100.0, quantity=1.0)],
            asks=[BookLevel(price=68_090.0, quantity=1.0)],
        )
