from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.market_data.live_adapter import BinanceSpotLiveMarketDataAdapter
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


class ScriptedFetcher:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(self, endpoint: str, params: dict[str, str]) -> object:
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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
