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
from crypto_agent.policy.readiness import default_live_readiness_status
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


def test_manual_halt_blocks_then_resume_allows_execution(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-manual-halt-demo"
    updated_at = _ts(2026, 4, 3, 16, 0)
    controls = default_live_control_config(
        runtime_id=runtime_id,
        settings=settings,
        updated_at=updated_at,
    )
    readiness = default_live_readiness_status(runtime_id=runtime_id, updated_at=updated_at)

    first_result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="paper",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        live_control_config=controls,
        readiness_status=readiness,
        manual_control_state=default_manual_control_state(
            runtime_id=runtime_id,
            updated_at=updated_at,
        ).model_copy(update={"halt_active": True, "halt_reason": "operator_pause"}),
    )

    second_result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="paper",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        live_control_config=controls,
        readiness_status=readiness,
        manual_control_state=default_manual_control_state(
            runtime_id=runtime_id,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
    )

    first_session = first_result.session_summaries[0]
    second_session = second_result.session_summaries[0]
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(second_result.status_path.read_text(encoding="utf-8"))
    )
    manual_state = json.loads(second_result.manual_control_state_path.read_text(encoding="utf-8"))

    assert first_session.session_id == "session-0001"
    assert first_session.session_outcome == "blocked_controls"
    assert first_session.control_reason_codes == ["manual_halt_active"]
    assert first_session.run_id is None

    assert second_session.session_id == "session-0002"
    assert second_session.session_outcome == "executed"
    assert second_session.run_id == f"{runtime_id}-session-0002"
    assert status.completed_session_count == 2
    assert status.control_status == "go"
    assert manual_state["halt_active"] is False
