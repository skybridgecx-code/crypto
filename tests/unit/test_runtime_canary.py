from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from crypto_agent.config import load_settings
from crypto_agent.market_data.live_adapter import BinanceSpotLiveMarketDataAdapter
from crypto_agent.policy.readiness import LiveReadinessStatus
from crypto_agent.runtime.loop import run_forward_paper_runtime
from crypto_agent.runtime.models import ForwardPaperRuntimeResult

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


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


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    return json.loads((SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8"))


def test_shadow_canary_passes_for_repeated_executed_shadow_sessions(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="shadow-canary-pass",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=2,
        tick_times=[
            _ts(2026, 4, 3, 16, 4),
            _ts(2026, 4, 3, 16, 5),
        ],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(2),
        readiness_status=LiveReadinessStatus(
            runtime_id="shadow-canary-pass",
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    canary = json.loads(result.shadow_canary_evaluation_path.read_text(encoding="utf-8"))

    assert result.shadow_canary_evaluation_path.exists()
    assert canary["applicable"] is True
    assert canary["state"] == "pass"
    assert canary["session_count"] == 2
    assert canary["executed_session_count"] == 2
    assert canary["skipped_unavailable_feed_session_count"] == 0
    assert canary["all_expected_evidence_present"] is True
    assert all(row["all_expected_evidence_present"] is True for row in canary["rows"])


def test_shadow_canary_fails_when_fresh_followup_runtime_skips_unavailable_feed(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "shadow-canary-fail"

    run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(1),
        readiness_status=LiveReadinessStatus(
            runtime_id=runtime_id,
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 5)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=BinanceSpotLiveMarketDataAdapter(
            fetch_json=ScriptedFetcher([RuntimeError("HTTP Error 451: ")])
        ),
        live_market_poll_retry_count=0,
        readiness_status=LiveReadinessStatus(
            runtime_id=runtime_id,
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    canary = json.loads(result.shadow_canary_evaluation_path.read_text(encoding="utf-8"))

    assert canary["applicable"] is True
    assert canary["state"] == "fail"
    assert canary["session_count"] == 2
    assert canary["executed_session_count"] == 1
    assert canary["skipped_unavailable_feed_session_count"] == 1
    assert "unavailable_feed_sessions_present" in canary["reason_codes"]
    assert "not_all_sessions_executed" in canary["reason_codes"]


def test_cli_canary_only_returns_nonzero_for_failed_canary(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
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
    canary_path = tmp_path / "runs" / "shadow-canary-cli" / "shadow_canary_evaluation.json"
    canary_path.parent.mkdir(parents=True, exist_ok=True)
    canary_path.write_text(
        json.dumps(
            {
                "runtime_id": "shadow-canary-cli",
                "generated_at": _ts(2026, 4, 7, 10, 0).isoformat(),
                "execution_mode": "shadow",
                "market_source": "binance_spot",
                "applicable": True,
                "state": "fail",
                "summary": "Shadow canary failed.",
                "reason_codes": ["unavailable_feed_sessions_present"],
                "session_count": 1,
                "completed_session_count": 1,
                "executed_session_count": 0,
                "blocked_session_count": 0,
                "skipped_stale_feed_session_count": 0,
                "skipped_degraded_feed_session_count": 0,
                "skipped_unavailable_feed_session_count": 1,
                "failed_session_count": 0,
                "interrupted_session_count": 0,
                "request_artifact_count": 0,
                "result_artifact_count": 0,
                "status_artifact_count": 0,
                "skip_evidence_count": 1,
                "all_expected_evidence_present": True,
                "rows": [],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    def _fake_runtime(*_: object, **__: object) -> ForwardPaperRuntimeResult:
        return ForwardPaperRuntimeResult.model_validate(
            {
                "runtime_id": "shadow-canary-cli",
                "registry_path": str(tmp_path / "runs" / "forward_paper_registry.json"),
                "status_path": str(tmp_path / "runs" / "shadow-canary-cli" / "status.json"),
                "history_path": str(tmp_path / "runs" / "shadow-canary-cli" / "history.jsonl"),
                "sessions_dir": str(tmp_path / "runs" / "shadow-canary-cli" / "sessions"),
                "live_market_status_path": None,
                "venue_constraints_path": None,
                "account_state_path": str(tmp_path / "runs" / "shadow-canary-cli" / "account.json"),
                "reconciliation_report_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "reconcile.json"
                ),
                "recovery_status_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "recovery.json"
                ),
                "execution_mode": "shadow",
                "execution_state_dir": str(tmp_path / "runs" / "shadow-canary-cli" / "execution"),
                "live_control_config_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "controls.json"
                ),
                "live_control_status_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "control_status.json"
                ),
                "readiness_status_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "readiness.json"
                ),
                "manual_control_state_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "manual.json"
                ),
                "shadow_canary_evaluation_path": str(canary_path),
                "live_market_preflight_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "preflight.json"
                ),
                "soak_evaluation_path": str(tmp_path / "runs" / "shadow-canary-cli" / "soak.json"),
                "shadow_evaluation_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "shadow_eval.json"
                ),
                "live_gate_decision_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "gate.json"
                ),
                "live_gate_threshold_summary_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "thresholds.json"
                ),
                "live_gate_report_path": str(tmp_path / "runs" / "shadow-canary-cli" / "gate.md"),
                "live_launch_verdict_path": str(
                    tmp_path / "runs" / "shadow-canary-cli" / "launch_verdict.json"
                ),
                "session_count": 1,
                "session_summaries": [],
            }
        )

    monkeypatch.setattr("crypto_agent.cli.forward_paper.run_forward_paper_runtime", _fake_runtime)

    from crypto_agent.cli.forward_paper import main

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--runtime-id",
            "shadow-canary-cli",
            "--market-source",
            "binance_spot",
            "--live-symbol",
            "BTCUSDT",
            "--execution-mode",
            "shadow",
            "--canary-only",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert output["runtime_id"] == "shadow-canary-cli"
    assert output["shadow_canary_evaluation_path"] == str(canary_path)


def test_cli_canary_only_returns_zero_for_passing_canary(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
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
    canary_path = tmp_path / "runs" / "shadow-canary-cli-pass" / "shadow_canary_evaluation.json"
    canary_path.parent.mkdir(parents=True, exist_ok=True)
    canary_path.write_text(
        json.dumps(
            {
                "runtime_id": "shadow-canary-cli-pass",
                "generated_at": _ts(2026, 4, 7, 10, 0).isoformat(),
                "execution_mode": "shadow",
                "market_source": "binance_spot",
                "applicable": True,
                "state": "pass",
                "summary": "Shadow canary passed.",
                "reason_codes": [],
                "session_count": 1,
                "completed_session_count": 1,
                "executed_session_count": 1,
                "blocked_session_count": 0,
                "skipped_stale_feed_session_count": 0,
                "skipped_degraded_feed_session_count": 0,
                "skipped_unavailable_feed_session_count": 0,
                "failed_session_count": 0,
                "interrupted_session_count": 0,
                "request_artifact_count": 1,
                "result_artifact_count": 1,
                "status_artifact_count": 1,
                "skip_evidence_count": 0,
                "all_expected_evidence_present": True,
                "rows": [],
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    def _fake_runtime(*_: object, **__: object) -> ForwardPaperRuntimeResult:
        return ForwardPaperRuntimeResult.model_validate(
            {
                "runtime_id": "shadow-canary-cli-pass",
                "registry_path": str(tmp_path / "runs" / "forward_paper_registry.json"),
                "status_path": str(tmp_path / "runs" / "shadow-canary-cli-pass" / "status.json"),
                "history_path": str(tmp_path / "runs" / "shadow-canary-cli-pass" / "history.jsonl"),
                "sessions_dir": str(tmp_path / "runs" / "shadow-canary-cli-pass" / "sessions"),
                "live_market_status_path": None,
                "venue_constraints_path": None,
                "account_state_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "account.json"
                ),
                "reconciliation_report_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "reconcile.json"
                ),
                "recovery_status_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "recovery.json"
                ),
                "execution_mode": "shadow",
                "execution_state_dir": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "execution"
                ),
                "live_control_config_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "controls.json"
                ),
                "live_control_status_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "control_status.json"
                ),
                "readiness_status_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "readiness.json"
                ),
                "manual_control_state_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "manual.json"
                ),
                "shadow_canary_evaluation_path": str(canary_path),
                "live_market_preflight_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "preflight.json"
                ),
                "soak_evaluation_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "soak.json"
                ),
                "shadow_evaluation_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "shadow_eval.json"
                ),
                "live_gate_decision_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "gate.json"
                ),
                "live_gate_threshold_summary_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "thresholds.json"
                ),
                "live_gate_report_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "gate.md"
                ),
                "live_launch_verdict_path": str(
                    tmp_path / "runs" / "shadow-canary-cli-pass" / "launch_verdict.json"
                ),
                "session_count": 1,
                "session_summaries": [],
            }
        )

    monkeypatch.setattr("crypto_agent.cli.forward_paper.run_forward_paper_runtime", _fake_runtime)

    from crypto_agent.cli.forward_paper import main

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--runtime-id",
            "shadow-canary-cli-pass",
            "--market-source",
            "binance_spot",
            "--live-symbol",
            "BTCUSDT",
            "--execution-mode",
            "shadow",
            "--canary-only",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["runtime_id"] == "shadow-canary-cli-pass"
    assert output["shadow_canary_evaluation_path"] == str(canary_path)


def test_shadow_canary_pass_snapshot(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    generated_at = _ts(2026, 4, 5, 10, 0)
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="shadow-canary-snapshot-pass",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=2,
        tick_times=[
            _ts(2026, 4, 3, 16, 4),
            _ts(2026, 4, 3, 16, 5),
        ],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(2),
        readiness_status=LiveReadinessStatus(
            runtime_id="shadow-canary-snapshot-pass",
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
        now_fn=lambda: generated_at,
    )

    snapshot_payload = json.loads(result.shadow_canary_evaluation_path.read_text(encoding="utf-8"))

    assert snapshot_payload == _load_snapshot("forward_shadow_canary_pass.snapshot.json")


def test_shadow_canary_fail_snapshot(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "shadow-canary-snapshot-fail"
    generated_at = _ts(2026, 4, 5, 10, 0)

    run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(1),
        readiness_status=LiveReadinessStatus(
            runtime_id=runtime_id,
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
        now_fn=lambda: generated_at,
    )

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 5)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=BinanceSpotLiveMarketDataAdapter(
            fetch_json=ScriptedFetcher([RuntimeError("HTTP Error 451: ")])
        ),
        live_market_poll_retry_count=0,
        readiness_status=LiveReadinessStatus(
            runtime_id=runtime_id,
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
        now_fn=lambda: generated_at,
    )

    snapshot_payload = json.loads(result.shadow_canary_evaluation_path.read_text(encoding="utf-8"))

    assert snapshot_payload == _load_snapshot("forward_shadow_canary_fail.snapshot.json")


def test_cli_sandbox_fixture_rehearsal_passes_flag_and_prints_paths(
    tmp_path: Path,
    capsys,
    monkeypatch,
) -> None:
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

    captured: dict[str, object] = {}

    def _fake_runtime(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs

        class Result:
            runtime_id = "sandbox-fixture-cli"
            execution_mode = "sandbox"
            status_path = tmp_path / "runs" / "sandbox-fixture-cli" / "status.json"
            history_path = tmp_path / "runs" / "sandbox-fixture-cli" / "history.jsonl"
            sessions_dir = tmp_path / "runs" / "sandbox-fixture-cli" / "sessions"
            account_state_path = tmp_path / "runs" / "sandbox-fixture-cli" / "account.json"
            execution_state_dir = tmp_path / "runs" / "sandbox-fixture-cli" / "execution"
            live_control_config_path = tmp_path / "runs" / "sandbox-fixture-cli" / "controls.json"
            live_control_status_path = (
                tmp_path / "runs" / "sandbox-fixture-cli" / "control_status.json"
            )
            readiness_status_path = tmp_path / "runs" / "sandbox-fixture-cli" / "readiness.json"
            manual_control_state_path = tmp_path / "runs" / "sandbox-fixture-cli" / "manual.json"
            shadow_canary_evaluation_path = (
                tmp_path / "runs" / "sandbox-fixture-cli" / "shadow_canary.json"
            )
            live_market_preflight_path = (
                tmp_path / "runs" / "sandbox-fixture-cli" / "preflight.json"
            )
            live_market_status_path = (
                tmp_path / "runs" / "sandbox-fixture-cli" / "live_market_status.json"
            )
            venue_constraints_path = (
                tmp_path / "runs" / "sandbox-fixture-cli" / "venue_constraints.json"
            )
            soak_evaluation_path = tmp_path / "runs" / "sandbox-fixture-cli" / "soak.json"
            shadow_evaluation_path = tmp_path / "runs" / "sandbox-fixture-cli" / "shadow_eval.json"
            live_gate_decision_path = tmp_path / "runs" / "sandbox-fixture-cli" / "gate.json"
            live_gate_threshold_summary_path = (
                tmp_path / "runs" / "sandbox-fixture-cli" / "thresholds.json"
            )
            live_gate_report_path = tmp_path / "runs" / "sandbox-fixture-cli" / "gate.md"
            live_launch_verdict_path = (
                tmp_path / "runs" / "sandbox-fixture-cli" / "launch_verdict.json"
            )
            reconciliation_report_path = (
                tmp_path / "runs" / "sandbox-fixture-cli" / "reconcile.json"
            )
            recovery_status_path = tmp_path / "runs" / "sandbox-fixture-cli" / "recovery.json"
            registry_path = tmp_path / "runs" / "forward_paper_registry.json"
            session_count = 1
            session_ids = ["session-0001"]
            session_summaries = []

        return Result()

    monkeypatch.setattr("crypto_agent.cli.forward_paper.run_forward_paper_runtime", _fake_runtime)

    from crypto_agent.cli.forward_paper import main

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--runtime-id",
            "sandbox-fixture-cli",
            "--market-source",
            "replay",
            "--execution-mode",
            "sandbox",
            "--sandbox-fixture-rehearsal",
            "--allow-execution-mode",
            "sandbox",
            "tests/fixtures/paper_candles_breakout_long.jsonl",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert captured["args"][0] == "tests/fixtures/paper_candles_breakout_long.jsonl"
    assert captured["kwargs"]["sandbox_fixture_rehearsal"] is True
    assert output["runtime_id"] == "sandbox-fixture-cli"
    assert output["execution_mode"] == "sandbox"
    assert output["live_launch_verdict_path"].endswith("launch_verdict.json")


def test_cli_sandbox_fixture_rehearsal_requires_sandbox_execution_mode(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "paper_test.yaml"
    config_path.write_text(
        "mode: paper\npaths:\n"
        f"  runs_dir: {tmp_path / 'runs'}\n"
        f"  journals_dir: {tmp_path / 'journals'}\n",
        encoding="utf-8",
    )

    from crypto_agent.cli.forward_paper import main

    with pytest.raises(SystemExit):
        main(
            [
                "--config",
                str(config_path),
                "--runtime-id",
                "bad-fixture-mode",
                "--market-source",
                "replay",
                "--execution-mode",
                "paper",
                "--sandbox-fixture-rehearsal",
                "tests/fixtures/paper_candles_breakout_long.jsonl",
            ]
        )


def test_cli_sandbox_fixture_rehearsal_requires_replay_market_source(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "paper_test.yaml"
    config_path.write_text(
        "mode: paper\npaths:\n"
        f"  runs_dir: {tmp_path / 'runs'}\n"
        f"  journals_dir: {tmp_path / 'journals'}\n",
        encoding="utf-8",
    )

    from crypto_agent.cli.forward_paper import main

    with pytest.raises(SystemExit):
        main(
            [
                "--config",
                str(config_path),
                "--runtime-id",
                "bad-fixture-source",
                "--market-source",
                "binance_spot",
                "--live-symbol",
                "BTCUSDT",
                "--execution-mode",
                "sandbox",
                "--sandbox-fixture-rehearsal",
            ]
        )


def test_cli_sandbox_fixture_rehearsal_rejects_preflight_only(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "paper_test.yaml"
    config_path.write_text(
        "mode: paper\npaths:\n"
        f"  runs_dir: {tmp_path / 'runs'}\n"
        f"  journals_dir: {tmp_path / 'journals'}\n",
        encoding="utf-8",
    )

    from crypto_agent.cli.forward_paper import main

    with pytest.raises(SystemExit):
        main(
            [
                "--config",
                str(config_path),
                "--runtime-id",
                "bad-fixture-preflight",
                "--market-source",
                "replay",
                "--execution-mode",
                "sandbox",
                "--sandbox-fixture-rehearsal",
                "--preflight-only",
                "tests/fixtures/paper_candles_breakout_long.jsonl",
            ]
        )


def test_cli_sandbox_fixture_rehearsal_rejects_canary_only(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "paper_test.yaml"
    config_path.write_text(
        "mode: paper\npaths:\n"
        f"  runs_dir: {tmp_path / 'runs'}\n"
        f"  journals_dir: {tmp_path / 'journals'}\n",
        encoding="utf-8",
    )

    from crypto_agent.cli.forward_paper import main

    with pytest.raises(SystemExit):
        main(
            [
                "--config",
                str(config_path),
                "--runtime-id",
                "bad-fixture-canary",
                "--market-source",
                "replay",
                "--execution-mode",
                "sandbox",
                "--sandbox-fixture-rehearsal",
                "--canary-only",
                "tests/fixtures/paper_candles_breakout_long.jsonl",
            ]
        )
