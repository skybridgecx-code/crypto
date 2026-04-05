from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.market_data.live_adapter import BinanceSpotLiveMarketDataAdapter
from crypto_agent.policy.readiness import LiveReadinessStatus
from crypto_agent.runtime.loop import run_forward_paper_runtime

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

    assert exit_code == 0
    assert Path(output["soak_evaluation_path"]).exists()
    assert Path(output["shadow_evaluation_path"]).exists()
    assert Path(output["live_gate_decision_path"]).exists()
    assert Path(output["live_gate_threshold_summary_path"]).exists()
    assert Path(output["live_gate_report_path"]).exists()
