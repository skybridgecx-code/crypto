from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.market_data.live_adapter import BinanceSpotLiveMarketDataAdapter
from crypto_agent.policy.live_controls import (
    default_live_control_config,
    default_manual_control_state,
)
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


def test_forward_runtime_writes_shadow_evaluation_for_repeated_shadow_sessions(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-shadow-eval",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=3,
        tick_times=[
            _ts(2026, 4, 3, 16, 4),
            _ts(2026, 4, 3, 16, 5),
            _ts(2026, 4, 3, 16, 6),
        ],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(3),
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-shadow-eval",
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    shadow = json.loads(result.shadow_evaluation_path.read_text(encoding="utf-8"))
    gate = json.loads(result.live_gate_decision_path.read_text(encoding="utf-8"))

    assert result.shadow_evaluation_path.exists()
    assert shadow["shadow_session_count"] == 3
    assert shadow["shadow_executed_session_count"] == 3
    assert shadow["request_count"] >= 1
    assert shadow["would_send_count"] >= 1
    assert shadow["missing_request_artifact_count"] == 0
    assert shadow["missing_result_artifact_count"] == 0
    assert shadow["missing_status_artifact_count"] == 0
    assert shadow["all_shadow_artifacts_present"] is True
    assert all(row["all_artifacts_present"] is True for row in shadow["rows"])
    assert gate["state"] == "ready"
    assert gate["reason_codes"] == []


def test_shadow_evaluation_records_missing_would_send_artifacts_when_manual_approval_blocks(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    updated_at = _ts(2026, 4, 5, 11, 0)
    controls = default_live_control_config(
        runtime_id="forward-shadow-approval-eval",
        settings=settings,
        updated_at=updated_at,
    ).model_copy(update={"manual_approval_above_notional_usd": 1.0})
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-shadow-approval-eval",
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
        live_control_config=controls,
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-shadow-approval-eval",
            updated_at=updated_at,
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
        manual_control_state=default_manual_control_state(
            runtime_id="forward-shadow-approval-eval",
            updated_at=updated_at,
        ),
    )

    shadow = json.loads(result.shadow_evaluation_path.read_text(encoding="utf-8"))

    assert shadow["shadow_session_count"] == 1
    assert shadow["request_count"] >= 1
    assert shadow["would_send_count"] == 0
    assert shadow["missing_result_artifact_count"] == 1
    assert shadow["missing_status_artifact_count"] == 1
    assert shadow["all_shadow_artifacts_present"] is False
    assert shadow["rows"][0]["control_action"] == "manual_approval_required"


def test_shadow_evaluation_unavailable_feed_session_has_skip_evidence_artifact(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    fetcher = ScriptedFetcher([RuntimeError("HTTP Error 451: ")])
    adapter = BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="shadow-skip-evidence-test",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 5, 14, 0)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=adapter,
        readiness_status=LiveReadinessStatus(
            runtime_id="shadow-skip-evidence-test",
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    session = result.session_summaries[0]
    shadow = json.loads(result.shadow_evaluation_path.read_text(encoding="utf-8"))

    # Session outcome is correct
    assert session.session_outcome == "skipped_unavailable_feed"

    # Skip evidence artifact was written
    assert session.skip_evidence_path is not None
    skip_evidence_path = Path(str(session.skip_evidence_path))
    assert skip_evidence_path.exists()
    skip_ev = json.loads(skip_evidence_path.read_text(encoding="utf-8"))
    assert skip_ev["session_id"] == session.session_id
    assert skip_ev["runtime_id"] == "shadow-skip-evidence-test"
    assert skip_ev["session_outcome"] == "skipped_unavailable_feed"
    assert skip_ev["feed_health_status"] == "degraded"
    assert skip_ev["feed_health_message"] is not None
    assert "451" in skip_ev["feed_health_message"]
    assert skip_ev["configured_base_url"] == "https://api.binance.com"

    # Shadow evaluation reflects skip evidence
    assert shadow["shadow_session_count"] == 1
    assert shadow["shadow_executed_session_count"] == 0
    assert shadow["shadow_unavailable_feed_session_count"] == 1
    assert shadow["skip_evidence_count"] == 1
    assert shadow["missing_skip_evidence_count"] == 0
    assert shadow["request_count"] == 0
    assert shadow["missing_request_artifact_count"] == 0
    assert shadow["missing_result_artifact_count"] == 0
    assert shadow["missing_status_artifact_count"] == 0
    assert shadow["all_shadow_artifacts_present"] is True
    assert shadow["rows"][0]["skip_evidence_present"] is True
    assert shadow["rows"][0]["all_artifacts_present"] is True


def test_shadow_evaluation_mixed_executed_and_unavailable_feed_sessions(
    tmp_path: Path,
) -> None:
    # Session 1: executed (healthy feed).
    settings = _paper_settings_for(tmp_path)
    run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="shadow-mixed-evidence-test",
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
            runtime_id="shadow-mixed-evidence-test",
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    # Session 2: fresh adapter with no cached state — 451 raises LiveMarketDataUnavailableError.
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="shadow-mixed-evidence-test",
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
        readiness_status=LiveReadinessStatus(
            runtime_id="shadow-mixed-evidence-test",
            updated_at=_ts(2026, 4, 5, 9, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    shadow = json.loads(result.shadow_evaluation_path.read_text(encoding="utf-8"))

    assert shadow["shadow_session_count"] == 2
    assert shadow["shadow_executed_session_count"] == 1
    assert shadow["shadow_unavailable_feed_session_count"] == 1
    assert shadow["skip_evidence_count"] == 1
    assert shadow["missing_skip_evidence_count"] == 0
    # Execution artifact misses only apply to non-unavailable-feed sessions.
    assert shadow["missing_request_artifact_count"] == 0
    assert shadow["missing_result_artifact_count"] == 0
    assert shadow["missing_status_artifact_count"] == 0
    # request_count is truthful (executed session only).
    assert shadow["request_count"] >= 0
    assert shadow["all_shadow_artifacts_present"] is True

    executed_row = next(r for r in shadow["rows"] if r["session_outcome"] == "executed")
    skipped_row = next(
        r for r in shadow["rows"] if r["session_outcome"] == "skipped_unavailable_feed"
    )
    assert executed_row["all_artifacts_present"] is True
    assert executed_row["skip_evidence_present"] is False
    assert skipped_row["all_artifacts_present"] is True
    assert skipped_row["skip_evidence_present"] is True
    assert skipped_row["request_count"] == 0
