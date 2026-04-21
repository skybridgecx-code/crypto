from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.market_data.live_adapter import BinanceSpotLiveMarketDataAdapter
from crypto_agent.policy.readiness import LiveReadinessStatus
from crypto_agent.runtime.loop import run_forward_paper_runtime

FIXTURES_DIR = Path("tests/fixtures")
_FORWARD_RUNTIME_STATUS_CLI_SHARED_FIELDS: tuple[str, ...] = (
    "runtime_id",
    "registry_path",
    "status_path",
    "history_path",
    "sessions_dir",
    "live_market_status_path",
    "venue_constraints_path",
    "account_state_path",
    "reconciliation_report_path",
    "recovery_status_path",
    "execution_state_dir",
    "live_control_config_path",
    "live_control_status_path",
    "readiness_status_path",
    "manual_control_state_path",
    "shadow_canary_evaluation_path",
    "live_market_preflight_path",
    "soak_evaluation_path",
    "shadow_evaluation_path",
    "live_gate_decision_path",
    "live_gate_threshold_summary_path",
    "live_gate_report_path",
    "live_launch_verdict_path",
)


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
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"},
                ],
            }
        ]
    }


class ScriptedFetcher:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(self, endpoint: str, params: dict[str, str]) -> object:
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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


def _live_adapter(session_count: int) -> BinanceSpotLiveMarketDataAdapter:
    fixture_klines = [
        [
            int(datetime.fromisoformat(row["open_time"].replace("Z", "+00:00")).timestamp() * 1000),
            str(row["open"]),
            str(row["high"]),
            str(row["low"]),
            str(row["close"]),
            str(row["volume"]),
            int(
                datetime.fromisoformat(row["close_time"].replace("Z", "+00:00")).timestamp() * 1000
            ),
            "0",
            0,
            "0",
            "0",
            "0",
        ]
        for row in (
            json.loads(line)
            for line in (FIXTURES_DIR / "paper_candles_breakout_long.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    ]
    responses: list[object] = []
    for _ in range(session_count):
        responses.extend(
            [
                _exchange_info(),
                fixture_klines,
                {
                    "symbol": "BTCUSDT",
                    "bidPrice": "103.70",
                    "bidQty": "1.5",
                    "askPrice": "103.80",
                    "askQty": "1.4",
                },
            ]
        )
    return BinanceSpotLiveMarketDataAdapter(fetch_json=ScriptedFetcher(responses))


def _unavailable_live_adapter() -> BinanceSpotLiveMarketDataAdapter:
    return BinanceSpotLiveMarketDataAdapter(
        fetch_json=ScriptedFetcher([RuntimeError("exchange unavailable")])
    )


def _healthy_live_adapter() -> BinanceSpotLiveMarketDataAdapter:
    return BinanceSpotLiveMarketDataAdapter(
        fetch_json=ScriptedFetcher(
            [
                _exchange_info(),
                [
                    _kline(
                        open_time_ms=_millis(2026, 4, 5, 11, 55),
                        close_time_ms=_millis(2026, 4, 5, 11, 56),
                        open_price="100.0",
                        high_price="101.0",
                        low_price="99.5",
                        close_price="100.5",
                        volume="1000",
                    ),
                    _kline(
                        open_time_ms=_millis(2026, 4, 5, 11, 56),
                        close_time_ms=_millis(2026, 4, 5, 11, 57),
                        open_price="100.5",
                        high_price="101.5",
                        low_price="100.0",
                        close_price="101.0",
                        volume="1001",
                    ),
                    _kline(
                        open_time_ms=_millis(2026, 4, 5, 11, 57),
                        close_time_ms=_millis(2026, 4, 5, 11, 58),
                        open_price="101.0",
                        high_price="102.0",
                        low_price="100.7",
                        close_price="101.5",
                        volume="1002",
                    ),
                    _kline(
                        open_time_ms=_millis(2026, 4, 5, 11, 58),
                        close_time_ms=_millis(2026, 4, 5, 11, 59),
                        open_price="101.5",
                        high_price="102.3",
                        low_price="101.2",
                        close_price="102.1",
                        volume="1003",
                    ),
                    _kline(
                        open_time_ms=_millis(2026, 4, 5, 11, 59),
                        close_time_ms=_millis(2026, 4, 5, 12, 0),
                        open_price="102.1",
                        high_price="103.2",
                        low_price="101.9",
                        close_price="103.0",
                        volume="1004",
                    ),
                    _kline(
                        open_time_ms=_millis(2026, 4, 5, 12, 0),
                        close_time_ms=_millis(2026, 4, 5, 12, 1),
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
    )


def test_fresh_runtime_materializes_live_gate_artifacts_without_existing_control_status(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-gate-fresh",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 11, 0)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_unavailable_live_adapter(),
        live_market_poll_retry_count=0,
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-gate-fresh",
            updated_at=_ts(2026, 4, 5, 10, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    session = result.session_summaries[0]
    control_status = json.loads(result.live_control_status_path.read_text(encoding="utf-8"))
    gate = json.loads(result.live_gate_decision_path.read_text(encoding="utf-8"))
    thresholds = json.loads(result.live_gate_threshold_summary_path.read_text(encoding="utf-8"))

    assert session.session_outcome == "skipped_unavailable_feed"
    assert result.live_control_status_path.exists()
    assert result.live_gate_decision_path.exists()
    assert result.live_gate_threshold_summary_path.exists()
    assert result.live_gate_report_path.exists()
    assert result.live_launch_verdict_path.exists()
    assert control_status["latest_decision_path"] is None
    assert control_status["go_no_go_action"] == "go"
    assert gate["state"] == "not_ready"
    assert "insufficient_completed_sessions" in gate["reason_codes"]
    assert thresholds["blocking_passed"] is True


def test_persisted_runtime_keeps_live_control_status_behavior_on_second_start(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    first_result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-gate-persisted",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 11, 5)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_unavailable_live_adapter(),
        live_market_poll_retry_count=0,
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-gate-persisted",
            updated_at=_ts(2026, 4, 5, 11, 4),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )
    first_control_status = json.loads(
        first_result.live_control_status_path.read_text(encoding="utf-8")
    )

    second_result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-gate-persisted",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 12, 1)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_healthy_live_adapter(),
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-gate-persisted",
            updated_at=_ts(2026, 4, 5, 12, 1),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    second_control_status = json.loads(
        second_result.live_control_status_path.read_text(encoding="utf-8")
    )

    assert first_result.session_summaries[0].session_outcome == "skipped_unavailable_feed"
    assert first_control_status["latest_decision_path"] is None
    assert second_result.session_summaries[0].session_outcome == "executed"
    assert second_result.live_control_status_path.exists()
    assert second_result.live_gate_decision_path.exists()
    assert second_control_status["latest_decision_path"] is not None
    assert (
        second_control_status["go_no_go_action"]
        == second_result.session_summaries[0].control_action
    )


def test_live_gate_is_blocked_when_operator_readiness_is_not_ready(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-gate-blocked",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 12, 0)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(1),
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-gate-blocked",
            updated_at=_ts(2026, 4, 5, 11, 59),
            status="not_ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    gate = json.loads(result.live_gate_decision_path.read_text(encoding="utf-8"))
    thresholds = json.loads(result.live_gate_threshold_summary_path.read_text(encoding="utf-8"))

    assert gate["state"] == "blocked"
    assert "operator_not_ready_status" in gate["reason_codes"]
    assert thresholds["blocking_passed"] is False
    assert any(
        check["check_id"] == "operator_ready" and check["passed"] is False
        for check in thresholds["checks"]
    )


def test_live_gate_is_not_ready_when_shadow_evidence_is_missing(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id="forward-gate-not-ready",
        session_interval_seconds=60,
        max_sessions=3,
        tick_times=[
            _ts(2026, 4, 5, 13, 0),
            _ts(2026, 4, 5, 13, 1),
            _ts(2026, 4, 5, 13, 2),
        ],
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-gate-not-ready",
            updated_at=_ts(2026, 4, 5, 12, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    gate = json.loads(result.live_gate_decision_path.read_text(encoding="utf-8"))

    assert gate["state"] == "not_ready"
    assert "insufficient_shadow_sessions" in gate["reason_codes"]
    assert "insufficient_shadow_requests" in gate["reason_codes"]


def test_cli_forward_runtime_prints_live_gate_paths(tmp_path: Path, capsys) -> None:
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

    from crypto_agent.cli.forward_paper import main

    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_breakout_long.jsonl"),
            "--config",
            str(config_path),
            "--runtime-id",
            "forward-gate-cli",
            "--max-sessions",
            "1",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    status_payload = json.loads(Path(output["status_path"]).read_text(encoding="utf-8"))

    assert exit_code == 0
    assert Path(output["shadow_canary_evaluation_path"]).exists()
    assert Path(output["soak_evaluation_path"]).exists()
    assert Path(output["shadow_evaluation_path"]).exists()
    assert Path(output["live_gate_decision_path"]).exists()
    assert Path(output["live_gate_threshold_summary_path"]).exists()
    assert Path(output["live_gate_report_path"]).exists()
    assert Path(output["live_launch_verdict_path"]).exists()
    for field in _FORWARD_RUNTIME_STATUS_CLI_SHARED_FIELDS:
        assert output[field] == status_payload[field]
