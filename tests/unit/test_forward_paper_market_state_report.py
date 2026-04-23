from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.forward_paper_market_state_report import main


def _build_candle(
    *, minute: int, close: float, high: float, low: float, volume: float
) -> dict[str, object]:
    base_time = f"2026-04-23T00:{minute:02d}:00+00:00"
    close_time = f"2026-04-23T00:{minute + 1:02d}:00+00:00"
    return {
        "venue": "binance_spot",
        "symbol": "BTCUSDT",
        "interval": "1m",
        "open_time": base_time,
        "close_time": close_time,
        "open": close - 10.0,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "closed": True,
    }


def _write_market_state(
    run_dir: Path,
    *,
    session_number: int,
    candles: list[dict[str, object]],
    feed_health_status: str,
) -> None:
    session_id = f"session-{session_number:04d}"
    sessions_dir = run_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "venue": "binance_spot",
        "symbol": "BTCUSDT",
        "interval": "1m",
        "polled_at": "2026-04-23T00:10:00+00:00",
        "candles": candles,
        "order_book": {
            "venue": "binance_spot",
            "symbol": "BTCUSDT",
            "timestamp": "2026-04-23T00:10:00+00:00",
            "bids": [{"price": 100000.0, "quantity": 1.0}],
            "asks": [{"price": 100001.0, "quantity": 1.0}],
        },
        "constraints": {
            "venue": "binance_spot",
            "symbol": "BTCUSDT",
            "status": "TRADING",
            "base_asset": "BTC",
            "quote_asset": "USDT",
            "tick_size": 0.1,
            "step_size": 0.001,
            "min_quantity": 0.001,
            "min_notional": 10.0,
            "raw_filters": {},
        },
        "constraint_registry": {
            "venue": "binance_spot",
            "updated_at": "2026-04-23T00:10:00+00:00",
            "symbol_constraints": [
                {
                    "venue": "binance_spot",
                    "symbol": "BTCUSDT",
                    "status": "TRADING",
                    "base_asset": "BTC",
                    "quote_asset": "USDT",
                    "tick_size": 0.1,
                    "step_size": 0.001,
                    "min_quantity": 0.001,
                    "min_notional": 10.0,
                    "raw_filters": {},
                }
            ],
        },
        "feed_health": {
            "status": feed_health_status,
            "observed_at": "2026-04-23T00:10:00+00:00",
            "last_success_at": "2026-04-23T00:10:00+00:00",
            "last_candle_close_time": "2026-04-23T00:10:00+00:00",
            "consecutive_failure_count": 0,
            "stale_after_seconds": 120,
            "message": None,
            "recovered": False,
        },
    }
    path = sessions_dir / f"{session_id}.live_market_state.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_forward_paper_market_state_report_aggregates_regimes_and_features(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_id = "omega-btc-evidence-4-btcusdt-advisory"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Trend-like session
    _write_market_state(
        run_dir,
        session_number=2,
        candles=[
            _build_candle(minute=0, close=100000.0, high=100100.0, low=99900.0, volume=90.0),
            _build_candle(minute=1, close=100400.0, high=100600.0, low=100200.0, volume=120.0),
            _build_candle(minute=2, close=100900.0, high=101100.0, low=100700.0, volume=140.0),
        ],
        feed_health_status="healthy",
    )
    # Insufficient-candles session (feature unavailable)
    _write_market_state(
        run_dir,
        session_number=1,
        candles=[_build_candle(minute=0, close=100000.0, high=100020.0, low=99980.0, volume=5.0)],
        feed_health_status="stale",
    )
    # sibling artifact should be ignored
    (run_dir / "sessions" / "session-0001.execution_status.json").write_text(
        json.dumps({"artifact_kind": "execution_status"}), encoding="utf-8"
    )

    assert main(["--run-id", run_id, "--runs-dir", str(runs_dir)]) == 0

    output_dir = runs_dir / "market_state_reports"
    json_path = output_dir / f"{run_id}.market_state_aggregate.json"
    report_path = output_dir / f"{run_id}.market_state_aggregate.md"
    assert json_path.exists()
    assert report_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "forward_paper_market_state_aggregate_v1"
    assert payload["run_count"] == 1

    run_payload = payload["runs"][0]
    assert run_payload["run_id"] == run_id
    assert run_payload["session_count"] == 2
    assert run_payload["feed_health_status_counts"] == {"healthy": 1, "stale": 1}
    assert run_payload["feature_unavailable_session_count"] == 1
    assert run_payload["regime_label_counts"]
    assert run_payload["feature_summaries"]["average_dollar_volume"]["count"] == 1
    assert len(run_payload["session_snapshots"]) == 2
    assert [entry["session_id"] for entry in run_payload["session_snapshots"]] == [
        "session-0001",
        "session-0002",
    ]
    assert run_payload["session_snapshots"][0]["regime_label"] is None
    assert run_payload["session_snapshots"][1]["regime_label"] is not None

    report = report_path.read_text(encoding="utf-8")
    assert "# Forward-Paper Market-State Aggregate Report" in report
    assert f"## {run_id}" in report
    assert "regime_label_counts" in report


def test_forward_paper_market_state_report_supports_multiple_run_ids(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    advisory_id = "omega-btc-evidence-4-btcusdt-advisory"
    control_id = "omega-btc-evidence-4-btcusdt-control"
    advisory_dir = runs_dir / advisory_id
    control_dir = runs_dir / control_id
    advisory_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    _write_market_state(
        advisory_dir,
        session_number=1,
        candles=[_build_candle(minute=0, close=100000.0, high=100200.0, low=99800.0, volume=100.0)],
        feed_health_status="healthy",
    )
    _write_market_state(
        control_dir,
        session_number=1,
        candles=[_build_candle(minute=0, close=100000.0, high=100200.0, low=99800.0, volume=100.0)],
        feed_health_status="healthy",
    )

    assert (
        main(
            [
                "--run-id",
                advisory_id,
                "--run-id",
                control_id,
                "--runs-dir",
                str(runs_dir),
            ]
        )
        == 0
    )

    output_dir = runs_dir / "market_state_reports"
    base_name = f"{advisory_id}__{control_id}"
    json_path = output_dir / f"{base_name}.market_state_aggregate.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_count"] == 2
    assert [entry["run_id"] for entry in payload["runs"]] == [advisory_id, control_id]


def test_forward_paper_market_state_report_missing_run_is_deterministic_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="forward_paper_market_state_missing_run_dir:"):
        main(
            [
                "--run-id",
                "omega-btc-evidence-4-btcusdt-advisory",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
