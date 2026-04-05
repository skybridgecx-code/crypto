from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.execution.live_adapter import ScriptedSandboxExecutionAdapter
from crypto_agent.execution.models import (
    ExecutionRequestArtifact,
    ExecutionResultArtifact,
    ExecutionStatusArtifact,
    VenueExecutionAck,
    VenueOrderState,
)
from crypto_agent.market_data.live_adapter import BinanceSpotLiveMarketDataAdapter
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


def test_forward_runtime_live_shadow_mode_writes_execution_artifacts(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-live-shadow",
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
    )

    session = result.session_summaries[0]
    assert session.execution_mode == "shadow"
    assert session.execution_request_path is not None
    assert session.execution_result_path is not None
    assert session.execution_status_path is not None

    requests = ExecutionRequestArtifact.model_validate(
        json.loads(Path(session.execution_request_path).read_text(encoding="utf-8"))
    )
    results = ExecutionResultArtifact.model_validate(
        json.loads(Path(session.execution_result_path).read_text(encoding="utf-8"))
    )
    statuses = ExecutionStatusArtifact.model_validate(
        json.loads(Path(session.execution_status_path).read_text(encoding="utf-8"))
    )
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert requests.execution_mode == "shadow"
    assert results.result_count == requests.request_count
    assert statuses.terminal_status_count == statuses.status_count
    assert status.execution_mode == "shadow"


def test_forward_runtime_live_sandbox_mode_writes_adapter_evidence(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    adapter = ScriptedSandboxExecutionAdapter(
        submit_fn=lambda request: VenueExecutionAck(
            request_id=request.request_id,
            client_order_id=request.client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            status="accepted",
            venue_order_id="sandbox-order-1",
            observed_at=_ts(2026, 4, 3, 16, 4),
        ),
        fetch_state_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="filled",
            terminal=True,
            filled_quantity=request.quantity,
            average_fill_price=request.reference_price,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
        cancel_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="canceled",
            terminal=True,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
    )

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-live-sandbox",
        session_interval_seconds=60,
        execution_mode="sandbox",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        sandbox_execution_adapter=adapter,
    )

    session = result.session_summaries[0]
    requests = ExecutionRequestArtifact.model_validate(
        json.loads(Path(session.execution_request_path).read_text(encoding="utf-8"))
    )
    results = ExecutionResultArtifact.model_validate(
        json.loads(Path(session.execution_result_path).read_text(encoding="utf-8"))
    )
    statuses = ExecutionStatusArtifact.model_validate(
        json.loads(Path(session.execution_status_path).read_text(encoding="utf-8"))
    )

    assert session.execution_mode == "sandbox"
    assert requests.request_count >= 1
    assert results.results[0].status == "accepted"
    assert statuses.statuses[0].state == "filled"
