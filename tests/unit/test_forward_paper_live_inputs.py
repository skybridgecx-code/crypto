from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.market_data.live_adapter import (
    BinanceSpotLiveMarketDataAdapter,
    CoinbaseSpotLiveMarketDataAdapter,
)
from crypto_agent.policy.live_controls import default_live_control_config
from crypto_agent.runtime.history import read_forward_paper_history
from crypto_agent.runtime.loop import run_forward_paper_runtime
from crypto_agent.runtime.models import ForwardPaperRuntimeStatus

FIXTURES_DIR = Path("tests/fixtures")


def _paper_settings_for(tmp_path: Path):
    settings = load_settings(Path("config/paper.yaml"))
    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "runs_dir": tmp_path / "runs",
                    "journals_dir": tmp_path / "journals",
                }
            )
        }
    )


def _ts(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _millis(year: int, month: int, day: int, hour: int, minute: int) -> int:
    return int(_ts(year, month, day, hour, minute).timestamp() * 1000)


def _exchange_info() -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
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

    def __call__(
        self,
        endpoint: str,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> object:
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class _FakeClock:
    def __init__(self, initial: datetime) -> None:
        self.current = initial

    def now(self) -> datetime:
        return self.current

    def sleep(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class _DynamicBinanceUSFetcher:
    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock

    def __call__(self, endpoint: str, params: dict[str, str]) -> object:
        if endpoint == "/api/v3/exchangeInfo":
            return _exchange_info()
        if endpoint == "/api/v3/ticker/bookTicker":
            return {
                "symbol": str(params.get("symbol", "BTCUSDT")),
                "bidPrice": "101.70",
                "bidQty": "1.0",
                "askPrice": "101.80",
                "askQty": "1.2",
            }
        if endpoint == "/api/v3/klines":
            limit = int(params.get("limit", "9"))
            now = self._clock.now()
            minute_start = now.replace(second=0, microsecond=0)
            candles: list[list[object]] = []
            for index in range(limit):
                open_time = minute_start - timedelta(minutes=limit - 1 - index)
                close_time = open_time + timedelta(minutes=1) - timedelta(milliseconds=1)
                candles.append(
                    _kline(
                        open_time_ms=int(open_time.timestamp() * 1000),
                        close_time_ms=int(close_time.timestamp() * 1000),
                        open_price="100.0",
                        high_price="101.0",
                        low_price="99.5",
                        close_price="100.5",
                        volume="1000",
                    )
                )
            return candles
        raise AssertionError(f"unexpected endpoint {endpoint}")


def test_forward_paper_runtime_live_mode_executes_healthy_session(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher(
        [
            _exchange_info(),
            [
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 13, 55),
                    close_time_ms=_millis(2026, 4, 5, 13, 56),
                    open_price="100.0",
                    high_price="101.0",
                    low_price="99.5",
                    close_price="100.5",
                    volume="1000",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 13, 56),
                    close_time_ms=_millis(2026, 4, 5, 13, 57),
                    open_price="100.5",
                    high_price="101.5",
                    low_price="100.0",
                    close_price="101.0",
                    volume="1001",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 13, 57),
                    close_time_ms=_millis(2026, 4, 5, 13, 58),
                    open_price="101.0",
                    high_price="102.0",
                    low_price="100.7",
                    close_price="101.5",
                    volume="1002",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 13, 58),
                    close_time_ms=_millis(2026, 4, 5, 13, 59),
                    open_price="101.5",
                    high_price="102.3",
                    low_price="101.2",
                    close_price="102.1",
                    volume="1003",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 13, 59),
                    close_time_ms=_millis(2026, 4, 5, 14, 0),
                    open_price="102.1",
                    high_price="103.2",
                    low_price="101.9",
                    close_price="103.0",
                    volume="1004",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 14, 0),
                    close_time_ms=_millis(2026, 4, 5, 14, 1),
                    open_price="103.0",
                    high_price="104.0",
                    low_price="102.8",
                    close_price="103.8",
                    volume="1005",
                ),
            ],
            {
                "symbol": "BTCUSDT",
                "bidPrice": "103.70",
                "bidQty": "1.5",
                "askPrice": "103.80",
                "askQty": "1.4",
            },
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-live-demo",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 14, 1)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=5,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
    )

    session = result.session_summaries[0]
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    run_summary = json.loads(Path(str(session.summary_path)).read_text(encoding="utf-8"))

    assert result.live_market_status_path is not None
    assert result.venue_constraints_path is not None
    assert Path(str(result.live_market_status_path)).exists()
    assert Path(str(result.venue_constraints_path)).exists()
    assert session.market_source == "binance_spot"
    assert session.live_symbol == "BTCUSDT"
    assert session.session_outcome == "executed"
    assert session.market_input_path is not None
    assert Path(str(session.market_input_path)).exists()
    assert session.market_state_path is not None
    assert Path(str(session.market_state_path)).exists()
    assert run_summary["replay_path"] == str(session.market_input_path)
    assert session.run_id == "forward-live-demo-session-0001"
    assert status.venue_constraints_ready is True
    assert status.feed_health is not None
    assert status.feed_health.status == "healthy"


def test_forward_paper_runtime_live_mode_skips_stale_feed_and_preserves_history(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher(
        [
            _exchange_info(),
            [
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 14, 55),
                    close_time_ms=_millis(2026, 4, 5, 14, 56),
                    open_price="100.0",
                    high_price="101.0",
                    low_price="99.0",
                    close_price="100.5",
                    volume="1000",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 14, 56),
                    close_time_ms=_millis(2026, 4, 5, 14, 57),
                    open_price="100.5",
                    high_price="101.5",
                    low_price="100.0",
                    close_price="101.0",
                    volume="1001",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 14, 57),
                    close_time_ms=_millis(2026, 4, 5, 14, 58),
                    open_price="101.0",
                    high_price="102.0",
                    low_price="100.5",
                    close_price="101.6",
                    volume="1002",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 14, 58),
                    close_time_ms=_millis(2026, 4, 5, 14, 59),
                    open_price="101.6",
                    high_price="102.4",
                    low_price="101.0",
                    close_price="102.0",
                    volume="1003",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 14, 59),
                    close_time_ms=_millis(2026, 4, 5, 15, 0),
                    open_price="102.0",
                    high_price="103.0",
                    low_price="101.8",
                    close_price="102.8",
                    volume="1004",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 15, 0),
                    close_time_ms=_millis(2026, 4, 5, 15, 1),
                    open_price="102.8",
                    high_price="103.8",
                    low_price="102.5",
                    close_price="103.6",
                    volume="1005",
                ),
            ],
            {
                "symbol": "BTCUSDT",
                "bidPrice": "103.50",
                "bidQty": "1.3",
                "askPrice": "103.60",
                "askQty": "1.1",
            },
            _exchange_info(),
            RuntimeError("temporary venue outage"),
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-live-stale-demo",
        session_interval_seconds=60,
        max_sessions=2,
        tick_times=[
            _ts(2026, 4, 5, 15, 1),
            _ts(2026, 4, 5, 15, 4),
        ],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=5,
        feed_stale_after_seconds=60,
        live_adapter=adapter,
    )

    history = read_forward_paper_history(result.history_path)
    first_session, second_session = result.session_summaries

    assert first_session.session_outcome == "executed"
    assert first_session.run_id == "forward-live-stale-demo-session-0001"
    assert second_session.session_outcome == "skipped_stale_feed"
    assert second_session.run_id is None
    assert second_session.feed_health is not None
    assert second_session.feed_health.status == "stale"
    assert second_session.market_input_path is not None
    assert Path(str(second_session.market_input_path)).exists()
    assert [event.message for event in history if event.event_type == "session.completed"] == [
        "executed",
        "skipped_stale_feed",
    ]


def test_binance_adapter_uses_overridden_base_url() -> None:
    adapter_default = BinanceSpotLiveMarketDataAdapter()
    assert adapter_default.base_url == "https://api.binance.com"

    adapter_override = BinanceSpotLiveMarketDataAdapter(base_url="https://api.binance.us")
    assert adapter_override.base_url == "https://api.binance.us"


def test_forward_paper_runtime_persists_binance_base_url_in_status(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher(
        [
            _exchange_info(),
            [
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 13, 55),
                    close_time_ms=_millis(2026, 4, 5, 13, 56),
                    open_price="100.0",
                    high_price="101.0",
                    low_price="99.5",
                    close_price="100.5",
                    volume="1000",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 13, 56),
                    close_time_ms=_millis(2026, 4, 5, 13, 57),
                    open_price="100.5",
                    high_price="101.5",
                    low_price="100.0",
                    close_price="101.0",
                    volume="1001",
                ),
                _kline(
                    open_time_ms=_millis(2026, 4, 5, 13, 57),
                    close_time_ms=_millis(2026, 4, 5, 13, 58),
                    open_price="101.0",
                    high_price="102.0",
                    low_price="100.7",
                    close_price="101.5",
                    volume="1002",
                ),
            ],
            {
                "symbol": "BTCUSDT",
                "bidPrice": "101.40",
                "bidQty": "1.0",
                "askPrice": "101.50",
                "askQty": "1.0",
            },
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="live-base-url-test",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 13, 58)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        binance_base_url="https://api.binance.us",
    )

    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    assert status.binance_base_url == "https://api.binance.us"


def test_forward_paper_runtime_unavailable_feed_451_enriches_message(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher([RuntimeError("HTTP Error 451: ")])

    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="live-451-test",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 14, 0)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        binance_base_url="https://api.binance.us",
        live_market_poll_retry_count=0,
    )

    session = result.session_summaries[0]
    assert session.session_outcome == "skipped_unavailable_feed"

    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    assert status.feed_health is not None
    assert status.feed_health.status == "degraded"
    assert status.feed_health.message is not None
    assert "451" in status.feed_health.message
    assert "legal/geo/IP restriction" in status.feed_health.message
    assert "https://api.binance.us" in status.feed_health.message


def test_forward_paper_runtime_unavailable_feed_non_451_enriches_message(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher([RuntimeError("connection refused")])

    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="live-unavail-test",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 14, 0)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        live_market_poll_retry_count=0,
    )

    session = result.session_summaries[0]
    assert session.session_outcome == "skipped_unavailable_feed"

    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    assert status.feed_health is not None
    assert status.feed_health.status == "degraded"
    assert status.feed_health.message is not None
    assert "https://api.binance.com" in status.feed_health.message
    assert "--binance-base-url" in status.feed_health.message


def test_forward_paper_runtime_coinbase_unavailable_feed_uses_coinbase_context(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher([RuntimeError("HTTP Error 401: Unauthorized")])
    adapter = CoinbaseSpotLiveMarketDataAdapter(
        fetch_json=fetcher,
        jwt_token_factory=lambda _method, _endpoint, _now: "test-token",
    )

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="live-coinbase-unavail-test",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 14, 0)],
        market_source="coinbase_spot",
        live_symbol="BTC-USD",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        live_market_poll_retry_count=0,
    )

    session = result.session_summaries[0]
    assert session.session_outcome == "skipped_unavailable_feed"

    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    assert status.feed_health is not None
    assert status.feed_health.status == "degraded"
    assert status.feed_health.message is not None
    assert "https://api.coinbase.com" in status.feed_health.message
    assert "api.binance.com" not in status.feed_health.message
    assert "--binance-base-url" not in status.feed_health.message


def _healthy_klines_and_book(
    tick: datetime,
) -> list[object]:
    """Return exchangeInfo + 3 closed klines + bookTicker for a healthy poll at tick."""
    base_ms = int((tick.timestamp() - 180) * 1000)
    minute_ms = 60_000
    return [
        _exchange_info(),
        [
            _kline(
                open_time_ms=base_ms,
                close_time_ms=base_ms + minute_ms - 1,
                open_price="100.0",
                high_price="101.0",
                low_price="99.5",
                close_price="100.5",
                volume="1000",
            ),
            _kline(
                open_time_ms=base_ms + minute_ms,
                close_time_ms=base_ms + 2 * minute_ms - 1,
                open_price="100.5",
                high_price="101.5",
                low_price="100.0",
                close_price="101.0",
                volume="1001",
            ),
            _kline(
                open_time_ms=base_ms + 2 * minute_ms,
                close_time_ms=base_ms + 3 * minute_ms - 1,
                open_price="101.0",
                high_price="102.0",
                low_price="100.7",
                close_price="101.5",
                volume="1002",
            ),
        ],
        {
            "symbol": "BTCUSDT",
            "bidPrice": "101.40",
            "bidQty": "1.0",
            "askPrice": "101.50",
            "askQty": "1.0",
        },
    ]


def test_forward_paper_runtime_retry_recovers_on_second_attempt(
    tmp_path: Path,
) -> None:
    """Feed fails on attempt 1, succeeds on attempt 2; session executes with retry_recovery note."""
    settings = _paper_settings_for(tmp_path)
    tick = _ts(2026, 4, 5, 15, 3)
    fetcher = ScriptedFetcher([RuntimeError("timeout"), *_healthy_klines_and_book(tick)])
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    sleep_calls: list[float] = []

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="retry-recover-attempt-2",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[tick],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        live_market_poll_retry_count=2,
        live_market_poll_retry_delay_seconds=0.1,
        sleep_fn=lambda d: sleep_calls.append(d),
    )

    session = result.session_summaries[0]
    assert session.session_outcome == "executed"
    assert session.feed_health is not None
    assert session.feed_health.recovered is True
    assert session.feed_health.message is not None
    assert "retry_recovery" in session.feed_health.message
    assert "attempt 2 of 3" in session.feed_health.message
    # sleep was called exactly once (between attempt 1 and attempt 2)
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == 0.1


def test_forward_paper_runtime_retry_recovers_on_third_attempt(
    tmp_path: Path,
) -> None:
    """Feed fails on attempts 1 and 2, succeeds on attempt 3."""
    settings = _paper_settings_for(tmp_path)
    tick = _ts(2026, 4, 5, 15, 6)
    fetcher = ScriptedFetcher(
        [
            RuntimeError("timeout"),
            RuntimeError("timeout"),
            *_healthy_klines_and_book(tick),
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    sleep_calls: list[float] = []

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="retry-recover-attempt-3",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[tick],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        live_market_poll_retry_count=2,
        live_market_poll_retry_delay_seconds=0.1,
        sleep_fn=lambda d: sleep_calls.append(d),
    )

    session = result.session_summaries[0]
    assert session.session_outcome == "executed"
    assert session.feed_health is not None
    assert session.feed_health.recovered is True
    assert session.feed_health.message is not None
    assert "retry_recovery" in session.feed_health.message
    assert "attempt 3 of 3" in session.feed_health.message
    # sleep was called twice (before attempt 2 and before attempt 3)
    assert len(sleep_calls) == 2


def test_forward_paper_runtime_retry_exhausted_skips_session_with_retries_note(
    tmp_path: Path,
) -> None:
    """All retry attempts fail — session is skipped and message records retries_exhausted."""
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher(
        [
            RuntimeError("HTTP Error 451: "),
            RuntimeError("HTTP Error 451: "),
            RuntimeError("HTTP Error 451: "),
        ]
    )
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="retry-exhausted-test",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 15, 9)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        live_market_poll_retry_count=2,
        live_market_poll_retry_delay_seconds=0.1,
        sleep_fn=lambda _: None,
    )

    session = result.session_summaries[0]
    assert session.session_outcome == "skipped_unavailable_feed"

    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    assert status.feed_health is not None
    assert status.feed_health.status == "degraded"
    assert status.feed_health.message is not None
    assert "retries_exhausted" in status.feed_health.message
    assert "failed after 3 attempts" in status.feed_health.message
    assert "451" in status.feed_health.message


def test_forward_paper_runtime_fresh_live_run_accepts_first_call_with_closed_candles(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    clock = _FakeClock(_ts(2026, 4, 5, 15, 0))
    # Match operator-path semantics where polling happens mid-minute.
    clock.current = clock.current + timedelta(seconds=15)
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=_DynamicBinanceUSFetcher(clock))

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="live-fresh-first-call-ready",
        session_interval_seconds=60,
        max_sessions=3,
        now_fn=clock.now,
        sleep_fn=clock.sleep,
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=8,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        binance_base_url="https://api.binance.us",
        live_market_poll_retry_count=5,
    )

    assert all(session.session_outcome == "executed" for session in result.session_summaries)


def test_forward_paper_runtime_clamps_overdue_schedule_for_live_polling(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "live-overdue-schedule-clamp"

    first_tick = _ts(2026, 4, 5, 14, 1)
    first_fetcher = ScriptedFetcher(_healthy_klines_and_book(first_tick))
    first_adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=first_fetcher)

    first_result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[first_tick],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=first_adapter,
    )
    assert first_result.session_summaries[0].session_outcome == "executed"

    resumed_now = _ts(2026, 4, 5, 14, 10)
    second_fetcher = ScriptedFetcher(_healthy_klines_and_book(resumed_now))
    second_adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=second_fetcher)

    second_result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        now_fn=lambda: resumed_now,
        sleep_fn=lambda _: None,
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=second_adapter,
    )

    resumed_session = second_result.session_summaries[0]
    assert resumed_session.session_outcome == "executed"
    assert resumed_session.scheduled_at == resumed_now


def test_forward_paper_runtime_coinbase_live_mode_executes_healthy_session(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher(
        [
            _coinbase_product(),
            {
                "candles": [
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 55),
                        open_price="100.0",
                        high_price="101.0",
                        low_price="99.5",
                        close_price="100.5",
                        volume="1000",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 56),
                        open_price="100.5",
                        high_price="101.5",
                        low_price="100.0",
                        close_price="101.0",
                        volume="1001",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 57),
                        open_price="101.0",
                        high_price="102.0",
                        low_price="100.7",
                        close_price="101.5",
                        volume="1002",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 58),
                        open_price="101.5",
                        high_price="102.3",
                        low_price="101.2",
                        close_price="102.1",
                        volume="1003",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 59),
                        open_price="102.1",
                        high_price="103.2",
                        low_price="101.9",
                        close_price="103.0",
                        volume="1004",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 14, 0),
                        open_price="103.0",
                        high_price="104.0",
                        low_price="102.8",
                        close_price="103.8",
                        volume="1005",
                    ),
                ]
            },
            {
                "pricebook": {
                    "bids": [{"price": "103.70"}],
                    "asks": [{"price": "103.80"}],
                }
            },
        ]
    )
    adapter = CoinbaseSpotLiveMarketDataAdapter(
        fetch_json=fetcher,
        jwt_token_factory=lambda _method, _endpoint, _now: "test-token",
    )
    controls = default_live_control_config(
        runtime_id="forward-live-coinbase-demo",
        settings=settings,
        updated_at=_ts(2026, 4, 5, 14, 1),
    ).model_copy(update={"symbol_allowlist": ["BTCUSD"]})

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-live-coinbase-demo",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 14, 1)],
        market_source="coinbase_spot",
        live_symbol="BTC-USD",
        live_interval="1m",
        live_lookback_candles=5,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        live_control_config=controls,
    )

    session = result.session_summaries[0]
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    market_state = json.loads(Path(str(session.market_state_path)).read_text(encoding="utf-8"))

    assert session.market_source == "coinbase_spot"
    assert session.live_symbol == "BTC-USD"
    assert session.session_outcome == "executed"
    assert session.market_input_path is not None
    assert Path(str(session.market_input_path)).exists()
    assert session.market_state_path is not None
    assert Path(str(session.market_state_path)).exists()
    assert session.summary_path is not None
    assert Path(str(session.summary_path)).exists()
    assert market_state["venue"] == "coinbase_spot"
    assert market_state["symbol"] == "BTCUSD"
    assert status.venue_constraints_ready is True


def test_forward_paper_runtime_coinbase_symbol_allowlist_accepts_product_notation(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher(
        [
            _coinbase_product(),
            {
                "candles": [
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 55),
                        open_price="100.0",
                        high_price="101.0",
                        low_price="99.5",
                        close_price="100.5",
                        volume="1000",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 56),
                        open_price="100.5",
                        high_price="101.5",
                        low_price="100.0",
                        close_price="101.0",
                        volume="1001",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 57),
                        open_price="101.0",
                        high_price="102.0",
                        low_price="100.7",
                        close_price="101.5",
                        volume="1002",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 58),
                        open_price="101.5",
                        high_price="102.3",
                        low_price="101.2",
                        close_price="102.1",
                        volume="1003",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 13, 59),
                        open_price="102.1",
                        high_price="103.2",
                        low_price="101.9",
                        close_price="103.0",
                        volume="1004",
                    ),
                    _coinbase_candle(
                        open_time_ms=_millis(2026, 4, 5, 14, 0),
                        open_price="103.0",
                        high_price="104.0",
                        low_price="102.8",
                        close_price="103.8",
                        volume="1005",
                    ),
                ]
            },
            {
                "pricebook": {
                    "bids": [{"price": "103.70"}],
                    "asks": [{"price": "103.80"}],
                }
            },
        ]
    )
    adapter = CoinbaseSpotLiveMarketDataAdapter(
        fetch_json=fetcher,
        jwt_token_factory=lambda _method, _endpoint, _now: "test-token",
    )
    controls = default_live_control_config(
        runtime_id="forward-live-coinbase-symbol-allowlist",
        settings=settings,
        updated_at=_ts(2026, 4, 5, 14, 1),
    ).model_copy(update={"symbol_allowlist": ["BTC-USD"]})

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-live-coinbase-symbol-allowlist",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 14, 1)],
        market_source="coinbase_spot",
        live_symbol="BTC-USD",
        live_interval="1m",
        live_lookback_candles=5,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        live_control_config=controls,
    )

    session = result.session_summaries[0]
    assert session.session_outcome == "executed"
    assert session.control_action == "go"
