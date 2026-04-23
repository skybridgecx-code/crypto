from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from crypto_agent.market_data.live_adapter import (
    BinanceSpotLiveMarketDataAdapter,
    CoinbaseSpotLiveMarketDataAdapter,
    LiveMarketDataUnavailableError,
)


def _ts(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _millis(year: int, month: int, day: int, hour: int, minute: int) -> int:
    return int(_ts(year, month, day, hour, minute).timestamp() * 1000)


def _exchange_info(symbol: str = "BTCUSDT") -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": symbol,
                "status": "TRADING",
                "baseAsset": symbol[:-4],
                "quoteAsset": symbol[-4:],
                "filters": [
                    {
                        "filterType": "PRICE_FILTER",
                        "tickSize": "0.10",
                    },
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.001",
                        "stepSize": "0.001",
                    },
                    {
                        "filterType": "MIN_NOTIONAL",
                        "minNotional": "10.00",
                    },
                ],
            }
        ]
    }


def _kline(
    *,
    open_time_ms: int,
    close_time_ms: int,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
    volume: str,
) -> list[object]:
    return [
        open_time_ms,
        open_price,
        high_price,
        low_price,
        close_price,
        volume,
        close_time_ms,
        "0",
        0,
        "0",
        "0",
        "0",
    ]


def _coinbase_product(product_id: str = "BTC-USD") -> dict[str, object]:
    return {
        "product_id": product_id,
        "base_currency_id": "BTC",
        "quote_currency_id": "USD",
        "base_increment": "0.00000001",
        "quote_increment": "0.01",
        "base_min_size": "0.0001",
        "quote_min_size": "1",
        "trading_disabled": False,
    }


def _coinbase_candle(
    *,
    open_time_ms: int,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
    volume: str,
) -> dict[str, str]:
    return {
        "start": str(open_time_ms),
        "open": open_price,
        "high": high_price,
        "low": low_price,
        "close": close_price,
        "volume": volume,
    }


class ScriptedFetcher:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, endpoint: str, params: dict[str, str]) -> object:
        self.calls.append((endpoint, params))
        if not self._responses:
            raise AssertionError("No scripted responses left")
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_binance_spot_live_adapter_returns_normalized_market_state() -> None:
    fetcher = ScriptedFetcher(
        [
            _exchange_info(),
            [
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 0),
                    close_time_ms=_millis(2026, 4, 5, 12, 1),
                    open_price="100.0",
                    high_price="101.0",
                    low_price="99.5",
                    close_price="100.5",
                    volume="1000",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 1),
                    close_time_ms=_millis(2026, 4, 5, 12, 2),
                    open_price="100.5",
                    high_price="101.5",
                    low_price="100.0",
                    close_price="101.0",
                    volume="1001",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 2),
                    close_time_ms=_millis(2026, 4, 5, 12, 3),
                    open_price="101.0",
                    high_price="102.0",
                    low_price="100.8",
                    close_price="101.8",
                    volume="1002",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 3),
                    close_time_ms=_millis(2026, 4, 5, 12, 4),
                    open_price="101.8",
                    high_price="102.5",
                    low_price="101.5",
                    close_price="102.2",
                    volume="1003",
                ),
            ],
            {
                "symbol": "BTCUSDT",
                "bidPrice": "102.10",
                "bidQty": "2.0",
                "askPrice": "102.20",
                "askQty": "1.5",
            },
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    state = adapter.poll_market_state(
        symbol="BTCUSDT",
        interval="1m",
        lookback_candles=3,
        stale_after_seconds=120,
        now=_ts(2026, 4, 5, 12, 4),
    )

    assert state.venue == "binance_spot"
    assert state.symbol == "BTCUSDT"
    assert len(state.candles) == 3
    assert state.constraints.tick_size == 0.1
    assert state.constraints.step_size == 0.001
    assert state.constraints.min_notional == 10.0
    assert state.order_book.bids[0].price == 102.10
    assert state.feed_health.status == "healthy"
    assert state.feed_health.last_candle_close_time == _ts(2026, 4, 5, 12, 4)


def test_binance_spot_live_adapter_detects_stale_cached_state_and_recovers() -> None:
    fetcher = ScriptedFetcher(
        [
            _exchange_info(),
            [
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 0),
                    close_time_ms=_millis(2026, 4, 5, 12, 1),
                    open_price="100.0",
                    high_price="101.0",
                    low_price="99.0",
                    close_price="100.5",
                    volume="1000",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 1),
                    close_time_ms=_millis(2026, 4, 5, 12, 2),
                    open_price="100.5",
                    high_price="101.5",
                    low_price="100.0",
                    close_price="101.0",
                    volume="1001",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 2),
                    close_time_ms=_millis(2026, 4, 5, 12, 3),
                    open_price="101.0",
                    high_price="102.0",
                    low_price="100.8",
                    close_price="101.7",
                    volume="1002",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 3),
                    close_time_ms=_millis(2026, 4, 5, 12, 4),
                    open_price="101.7",
                    high_price="102.3",
                    low_price="101.2",
                    close_price="102.0",
                    volume="1003",
                ),
            ],
            {
                "symbol": "BTCUSDT",
                "bidPrice": "102.00",
                "bidQty": "2.0",
                "askPrice": "102.10",
                "askQty": "1.0",
            },
            _exchange_info(),
            RuntimeError("temporary venue outage"),
            _exchange_info(),
            [
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 1),
                    close_time_ms=_millis(2026, 4, 5, 12, 2),
                    open_price="100.5",
                    high_price="101.5",
                    low_price="100.0",
                    close_price="101.0",
                    volume="1001",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 2),
                    close_time_ms=_millis(2026, 4, 5, 12, 3),
                    open_price="101.0",
                    high_price="102.0",
                    low_price="100.8",
                    close_price="101.7",
                    volume="1002",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 3),
                    close_time_ms=_millis(2026, 4, 5, 12, 4),
                    open_price="101.7",
                    high_price="102.3",
                    low_price="101.2",
                    close_price="102.0",
                    volume="1003",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 4),
                    close_time_ms=_millis(2026, 4, 5, 12, 5),
                    open_price="102.0",
                    high_price="102.8",
                    low_price="101.9",
                    close_price="102.6",
                    volume="1004",
                ),
            ],
            {
                "symbol": "BTCUSDT",
                "bidPrice": "102.50",
                "bidQty": "1.9",
                "askPrice": "102.60",
                "askQty": "1.4",
            },
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    initial = adapter.poll_market_state(
        symbol="BTCUSDT",
        interval="1m",
        lookback_candles=3,
        stale_after_seconds=60,
        now=_ts(2026, 4, 5, 12, 4),
    )
    stale = adapter.poll_market_state(
        symbol="BTCUSDT",
        interval="1m",
        lookback_candles=3,
        stale_after_seconds=60,
        now=_ts(2026, 4, 5, 12, 7),
    )
    recovered = adapter.poll_market_state(
        symbol="BTCUSDT",
        interval="1m",
        lookback_candles=3,
        stale_after_seconds=60,
        now=_ts(2026, 4, 5, 12, 5),
    )

    assert initial.feed_health.status == "healthy"
    assert stale.feed_health.status == "stale"
    assert stale.feed_health.consecutive_failure_count == 1
    assert "temporary venue outage" in str(stale.feed_health.message)
    assert recovered.feed_health.status == "healthy"
    assert recovered.feed_health.recovered is True
    assert recovered.feed_health.message == "recovered_after_failure"


def test_binance_spot_live_adapter_raises_when_no_cached_state_exists() -> None:
    fetcher = ScriptedFetcher([RuntimeError("exchange unavailable")])
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    with pytest.raises(LiveMarketDataUnavailableError):
        adapter.poll_market_state(
            symbol="BTCUSDT",
            interval="1m",
            lookback_candles=3,
            stale_after_seconds=60,
            now=_ts(2026, 4, 5, 12, 0),
        )


def test_binance_spot_live_adapter_excludes_open_1m_candle_and_accepts_closed_set() -> None:
    fetcher = ScriptedFetcher(
        [
            _exchange_info(),
            [
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 0),
                    close_time_ms=_millis(2026, 4, 5, 12, 1) - 1,
                    open_price="100.0",
                    high_price="101.0",
                    low_price="99.5",
                    close_price="100.4",
                    volume="1000",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 1),
                    close_time_ms=_millis(2026, 4, 5, 12, 2) - 1,
                    open_price="100.4",
                    high_price="101.2",
                    low_price="100.1",
                    close_price="100.9",
                    volume="1001",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 2),
                    close_time_ms=_millis(2026, 4, 5, 12, 3) - 1,
                    open_price="100.9",
                    high_price="101.8",
                    low_price="100.8",
                    close_price="101.5",
                    volume="1002",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 3),
                    close_time_ms=_millis(2026, 4, 5, 12, 4) - 1,
                    open_price="101.5",
                    high_price="102.0",
                    low_price="101.4",
                    close_price="101.8",
                    volume="1003",
                ),
            ],
            {
                "symbol": "BTCUSDT",
                "bidPrice": "101.70",
                "bidQty": "1.0",
                "askPrice": "101.80",
                "askQty": "1.2",
            },
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    state = adapter.poll_market_state(
        symbol="BTCUSDT",
        interval="1m",
        lookback_candles=3,
        stale_after_seconds=120,
        now=_ts(2026, 4, 5, 12, 3),
    )

    assert len(state.candles) == 3
    assert state.candles[0].open_time == _ts(2026, 4, 5, 12, 0)
    assert state.candles[-1].close_time == _ts(2026, 4, 5, 12, 3) - timedelta(milliseconds=1)
    assert state.feed_health.status == "healthy"


def test_binance_spot_live_adapter_raises_when_not_enough_closed_1m_candles() -> None:
    fetcher = ScriptedFetcher(
        [
            _exchange_info(),
            [
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 0),
                    close_time_ms=_millis(2026, 4, 5, 12, 1) - 1,
                    open_price="100.0",
                    high_price="101.0",
                    low_price="99.5",
                    close_price="100.4",
                    volume="1000",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 1),
                    close_time_ms=_millis(2026, 4, 5, 12, 2) - 1,
                    open_price="100.4",
                    high_price="101.2",
                    low_price="100.1",
                    close_price="100.9",
                    volume="1001",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 2),
                    close_time_ms=_millis(2026, 4, 5, 12, 3) - 1,
                    open_price="100.9",
                    high_price="101.8",
                    low_price="100.8",
                    close_price="101.5",
                    volume="1002",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 12, 3),
                    close_time_ms=_millis(2026, 4, 5, 12, 4) - 1,
                    open_price="101.5",
                    high_price="102.0",
                    low_price="101.4",
                    close_price="101.8",
                    volume="1003",
                ),
            ],
            {
                "symbol": "BTCUSDT",
                "bidPrice": "101.70",
                "bidQty": "1.0",
                "askPrice": "101.80",
                "askQty": "1.2",
            },
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    with pytest.raises(
        LiveMarketDataUnavailableError,
        match="Not enough closed venue candles available",
    ):
        adapter.poll_market_state(
            symbol="BTCUSDT",
            interval="1m",
            lookback_candles=4,
            stale_after_seconds=120,
            now=_ts(2026, 4, 5, 12, 3),
        )


def test_coinbase_spot_live_adapter_returns_normalized_market_state() -> None:
    fetcher = ScriptedFetcher(
        [
            _coinbase_product(),
            {
                "candles": [
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 12, 0),
                        open_price="100.0",
                        high_price="101.0",
                        low_price="99.5",
                        close_price="100.5",
                        volume="1000",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 12, 1),
                        open_price="100.5",
                        high_price="101.5",
                        low_price="100.2",
                        close_price="101.0",
                        volume="1001",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 12, 2),
                        open_price="101.0",
                        high_price="101.8",
                        low_price="100.8",
                        close_price="101.5",
                        volume="1002",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 12, 3),
                        open_price="101.5",
                        high_price="102.0",
                        low_price="101.2",
                        close_price="101.9",
                        volume="1003",
                    ),
                ]
            },
            {
                "pricebook": {
                    "bids": [{"price": "101.80"}],
                    "asks": [{"price": "101.90"}],
                }
            },
        ]
    )
    adapter = CoinbaseSpotLiveMarketDataAdapter(fetch_json=fetcher)

    state = adapter.poll_market_state(
        symbol="BTC-USD",
        interval="1m",
        lookback_candles=3,
        stale_after_seconds=120,
        now=_ts(2026, 4, 5, 12, 4),
    )

    assert state.venue == "coinbase_spot"
    assert state.symbol == "BTCUSD"
    assert len(state.candles) == 3
    assert state.constraints.tick_size == 0.01
    assert state.constraints.step_size == 0.00000001
    assert state.constraints.min_notional == 1.0
    assert state.order_book.bids[0].price == 101.80
    assert state.order_book.asks[0].price == 101.90
    assert state.feed_health.status == "healthy"
    assert state.feed_health.last_candle_close_time == _ts(2026, 4, 5, 12, 4)


def test_coinbase_spot_live_adapter_accepts_pair_symbol_and_px_book_shape() -> None:
    fetcher = ScriptedFetcher(
        [
            _coinbase_product(),
            {
                "candles": [
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 12, 0),
                        open_price="100.0",
                        high_price="101.0",
                        low_price="99.5",
                        close_price="100.5",
                        volume="1000",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 12, 1),
                        open_price="100.5",
                        high_price="101.5",
                        low_price="100.2",
                        close_price="101.0",
                        volume="1001",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 12, 2),
                        open_price="101.0",
                        high_price="101.8",
                        low_price="100.8",
                        close_price="101.5",
                        volume="1002",
                    ),
                ]
            },
            {
                "bids": [{"px": "101.45"}],
                "asks": [{"px": "101.55"}],
            },
        ]
    )
    adapter = CoinbaseSpotLiveMarketDataAdapter(fetch_json=fetcher)

    state = adapter.poll_market_state(
        symbol="BTCUSD",
        interval="1m",
        lookback_candles=2,
        stale_after_seconds=120,
        now=_ts(2026, 4, 5, 12, 3),
    )

    assert state.symbol == "BTCUSD"
    assert state.order_book.bids[0].price == 101.45
    assert state.order_book.asks[0].price == 101.55
