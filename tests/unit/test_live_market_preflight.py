from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.market_data.live_adapter import BinanceSpotLiveMarketDataAdapter
from crypto_agent.runtime.loop import run_live_market_preflight_probe
from crypto_agent.runtime.models import LiveMarketPreflightArtifact, LiveMarketPreflightResult


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


def _write_cli_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "paper_test.yaml"
    config_path.write_text(
        "\n".join(
            [
                "mode: paper",
                "paths:",
                f"  runs_dir: {tmp_path / 'runs'}",
                f"  journals_dir: {tmp_path / 'journals'}",
                "venue:",
                "  default_venue: paper",
                "  allowed_symbols:",
                "    - BTCUSDT",
                "risk:",
                "  risk_per_trade_fraction: 0.005",
                "  max_portfolio_gross_exposure: 1.0",
                "  max_symbol_gross_exposure: 0.4",
                "  max_daily_realized_loss: 0.015",
                "  max_open_positions: 2",
                "  max_leverage: 1.0",
                "  max_spread_bps: 12.0",
                "  max_expected_slippage_bps: 15.0",
                "  min_average_dollar_volume_usd: 5000000.0",
                "policy:",
                "  allow_live_orders: false",
                "  require_manual_approval_above_notional_usd: 1000.0",
                "  kill_switch_enabled: true",
                "  max_consecutive_order_rejects: 3",
                "  max_slippage_breaches: 2",
                "  max_drawdown_fraction: 0.03",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


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
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"},
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


def _healthy_klines_and_book(tick: datetime) -> list[object]:
    minute_ms = 60_000
    base_ms = int(tick.timestamp() * 1000) - 3 * minute_ms
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


def test_live_market_preflight_succeeds_immediately(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    tick = _ts(2026, 4, 6, 9, 30)
    adapter = BinanceSpotLiveMarketDataAdapter(
        fetch_json=ScriptedFetcher(_healthy_klines_and_book(tick))
    )

    result = run_live_market_preflight_probe(
        settings=settings,
        runtime_id="preflight-ready",
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        now_fn=lambda: tick,
        sleep_fn=lambda _: None,
    )

    artifact = LiveMarketPreflightArtifact.model_validate(
        json.loads(result.artifact_path.read_text(encoding="utf-8"))
    )

    assert artifact.status == "ready"
    assert artifact.success is True
    assert artifact.attempt_count_used == 1
    assert artifact.feed_health_status == "healthy"
    assert artifact.candle_count == 2
    assert artifact.order_book_present is True
    assert artifact.constraints_present is True
    assert (tmp_path / "runs" / "preflight-ready" / "live_market_status.json").exists()
    assert (tmp_path / "runs" / "preflight-ready" / "venue_constraints.json").exists()


def test_live_market_preflight_recovers_after_retry(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    tick = _ts(2026, 4, 6, 9, 35)
    adapter = BinanceSpotLiveMarketDataAdapter(
        fetch_json=ScriptedFetcher([RuntimeError("timeout"), *_healthy_klines_and_book(tick)])
    )
    sleep_calls: list[float] = []

    result = run_live_market_preflight_probe(
        settings=settings,
        runtime_id="preflight-recovered",
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        now_fn=lambda: tick,
        live_market_poll_retry_count=2,
        live_market_poll_retry_delay_seconds=0.1,
        sleep_fn=lambda delay: sleep_calls.append(delay),
    )

    artifact = result.artifact

    assert artifact.status == "recovered_after_retry"
    assert artifact.success is True
    assert artifact.attempt_count_used == 2
    assert artifact.feed_health_status == "healthy"
    assert artifact.feed_health_message is not None
    assert "retry_recovery" in artifact.feed_health_message
    assert "attempt 2 of 3" in artifact.feed_health_message
    assert sleep_calls == [0.1]


def test_live_market_preflight_fails_when_retries_are_exhausted(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    tick = _ts(2026, 4, 6, 9, 40)
    adapter = BinanceSpotLiveMarketDataAdapter(
        fetch_json=ScriptedFetcher(
            [
                RuntimeError("HTTP Error 451: "),
                RuntimeError("HTTP Error 451: "),
                RuntimeError("HTTP Error 451: "),
            ]
        )
    )

    result = run_live_market_preflight_probe(
        settings=settings,
        runtime_id="preflight-retries-exhausted",
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=2,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        now_fn=lambda: tick,
        live_market_poll_retry_count=2,
        live_market_poll_retry_delay_seconds=0.1,
        sleep_fn=lambda _: None,
    )

    artifact = LiveMarketPreflightArtifact.model_validate(
        json.loads(result.artifact_path.read_text(encoding="utf-8"))
    )

    assert artifact.status == "retries_exhausted"
    assert artifact.success is False
    assert artifact.attempt_count_used == 3
    assert artifact.feed_health_status == "degraded"
    assert artifact.feed_health_message is not None
    assert "retries_exhausted" in artifact.feed_health_message
    assert "failed after 3 attempts" in artifact.feed_health_message
    assert "451" in artifact.feed_health_message
    assert artifact.candle_count == 0
    assert artifact.order_book_present is False
    assert artifact.constraints_present is False


def test_cli_preflight_only_returns_nonzero_for_failed_probe(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
    config_path = _write_cli_config(tmp_path)
    artifact_path = tmp_path / "runs" / "preflight-cli" / "live_market_preflight.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact = LiveMarketPreflightArtifact(
        runtime_id="preflight-cli",
        market_source="binance_spot",
        symbol="BTCUSDT",
        interval="1m",
        configured_base_url="https://api.binance.com",
        retry_count=2,
        retry_delay_seconds=2.0,
        attempt_count_used=3,
        observed_at=_ts(2026, 4, 6, 9, 45),
        status="retries_exhausted",
        success=False,
        feed_health_status="degraded",
        feed_health_message="HTTP Error 451 | retries_exhausted: failed after 3 attempts",
        candle_count=0,
        order_book_present=False,
        constraints_present=False,
    )
    artifact_path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )

    def _fake_probe(**_: object) -> LiveMarketPreflightResult:
        return LiveMarketPreflightResult(
            runtime_id="preflight-cli",
            artifact_path=artifact_path,
            artifact=artifact,
        )

    monkeypatch.setattr(
        "crypto_agent.cli.forward_paper.run_live_market_preflight_probe",
        _fake_probe,
    )

    from crypto_agent.cli.forward_paper import main

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--runtime-id",
            "preflight-cli",
            "--market-source",
            "binance_spot",
            "--live-symbol",
            "BTCUSDT",
            "--preflight-only",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["preflight_path"] == str(artifact_path)
    assert output["status"] == "retries_exhausted"
    assert output["success"] is False
