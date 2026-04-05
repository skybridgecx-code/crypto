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


class ScriptedFetcher:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(self, endpoint: str, params: dict[str, str]) -> object:
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


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


def _live_adapter() -> BinanceSpotLiveMarketDataAdapter:
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
    fetcher = ScriptedFetcher(
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
    return BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)


def test_runtime_blocks_when_readiness_is_not_ready_and_writes_artifacts(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    updated_at = _ts(2026, 4, 3, 16, 0)
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-readiness-blocked",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        live_control_config=default_live_control_config(
            runtime_id="forward-readiness-blocked",
            settings=settings,
            updated_at=updated_at,
        ),
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-readiness-blocked",
            updated_at=updated_at,
            status="not_ready",
            note="operator_hold",
        ),
        manual_control_state=default_manual_control_state(
            runtime_id="forward-readiness-blocked",
            updated_at=updated_at,
        ),
    )

    session = result.session_summaries[0]
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    readiness = json.loads(result.readiness_status_path.read_text(encoding="utf-8"))
    control_status = json.loads(result.live_control_status_path.read_text(encoding="utf-8"))
    manual_state = json.loads(result.manual_control_state_path.read_text(encoding="utf-8"))
    control_decision = json.loads(Path(session.control_decision_path).read_text(encoding="utf-8"))

    assert session.session_outcome == "blocked_controls"
    assert session.run_id is None
    assert session.control_action == "no_go"
    assert session.control_reason_codes == ["operator_not_ready"]
    assert session.market_input_path is not None
    assert session.market_state_path is not None
    assert session.execution_request_path is None
    assert status.control_status == "no_go"
    assert status.control_block_reasons == ["operator_not_ready"]
    assert readiness["status"] == "not_ready"
    assert readiness["note"] == "operator_hold"
    assert manual_state["halt_active"] is False
    assert control_status["go_no_go_action"] == "no_go"
    assert control_status["go_no_go_reason_codes"] == ["operator_not_ready"]
    assert control_decision["action"] == "no_go"
    assert control_decision["stage"] == "preflight"


def test_shadow_runtime_records_request_but_blocks_would_send_without_manual_approval(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    updated_at = _ts(2026, 4, 3, 16, 0)
    controls = default_live_control_config(
        runtime_id="forward-shadow-approval",
        settings=settings,
        updated_at=updated_at,
    ).model_copy(
        update={
            "manual_approval_above_notional_usd": 1.0,
            "per_symbol_max_notional_usd": {"BTCUSDT": 1.0},
        }
    )
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-shadow-approval",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        live_control_config=controls,
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-shadow-approval",
            updated_at=updated_at,
            status="ready",
        ),
        manual_control_state=default_manual_control_state(
            runtime_id="forward-shadow-approval",
            updated_at=updated_at,
        ),
    )

    session = result.session_summaries[0]
    control_status = json.loads(result.live_control_status_path.read_text(encoding="utf-8"))
    control_decision = json.loads(Path(session.control_decision_path).read_text(encoding="utf-8"))

    assert session.session_outcome == "executed"
    assert session.execution_request_path is not None
    assert Path(session.execution_request_path).exists()
    assert session.execution_result_path is None
    assert session.execution_status_path is None
    assert session.control_action == "manual_approval_required"
    assert "manual_approval_required" in session.control_reason_codes
    assert control_status["go_no_go_action"] == "manual_approval_required"
    assert control_decision["stage"] == "post_run"
