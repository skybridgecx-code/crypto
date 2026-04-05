from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.execution.live_adapter import ScriptedSandboxExecutionAdapter
from crypto_agent.execution.models import (
    VenueExecutionAck,
    VenueOrderState,
)
from crypto_agent.execution.sandbox import execute_sandbox_requests
from crypto_agent.market_data.live_models import LiveFeedHealth, LiveMarketState
from crypto_agent.market_data.models import BookLevel, Candle, OrderBookSnapshot
from crypto_agent.market_data.venue_constraints import (
    VenueConstraintRegistry,
    VenueSymbolConstraints,
)

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


def _write_live_files(tmp_path: Path) -> tuple[Path, Path]:
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    constraints = VenueSymbolConstraints(
        venue="binance_spot_testnet",
        symbol="BTCUSDT",
        status="TRADING",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=0.1,
        step_size=0.001,
        min_quantity=0.001,
        min_notional=10.0,
    )
    market_state = LiveMarketState(
        venue="binance_spot",
        symbol="BTCUSDT",
        interval="1m",
        polled_at=now,
        candles=[
            Candle(
                venue="binance_spot",
                symbol="BTCUSDT",
                interval="1m",
                open_time=now,
                close_time=now + timedelta(minutes=1),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000.0,
                closed=True,
            )
        ],
        order_book=OrderBookSnapshot(
            venue="binance_spot",
            symbol="BTCUSDT",
            timestamp=now,
            bids=[BookLevel(price=100.4, quantity=1.0)],
            asks=[BookLevel(price=100.6, quantity=1.0)],
        ),
        constraints=constraints,
        constraint_registry=VenueConstraintRegistry(
            venue="binance_spot_testnet",
            updated_at=now,
            symbol_constraints=[constraints],
        ),
        feed_health=LiveFeedHealth(
            status="healthy",
            observed_at=now,
            last_success_at=now,
            last_candle_close_time=now,
            stale_after_seconds=120,
        ),
    )
    market_state_path = tmp_path / "live_market_state.json"
    venue_constraints_path = tmp_path / "venue_constraints.json"
    market_state_path.write_text(
        json.dumps(market_state.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    venue_constraints_path.write_text(
        json.dumps(
            market_state.constraint_registry.model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return market_state_path, venue_constraints_path


def test_sandbox_execution_handles_submit_poll_cancel_and_duplicate_reuse(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="sandbox-demo",
    )
    market_state_path, venue_constraints_path = _write_live_files(tmp_path)
    calls = {"submit": 0, "fetch": 0, "cancel": 0}

    adapter = ScriptedSandboxExecutionAdapter(
        submit_fn=lambda request: (
            calls.__setitem__("submit", calls["submit"] + 1)
            or VenueExecutionAck(
                request_id=request.request_id,
                client_order_id=request.client_order_id,
                venue=request.venue,
                execution_mode="sandbox",
                sandbox=True,
                intent_id=request.intent_id,
                status="accepted",
                venue_order_id="order-1",
                observed_at=datetime(2026, 4, 7, 12, 1, tzinfo=UTC),
            )
        ),
        fetch_state_fn=lambda client_order_id, request: (
            calls.__setitem__("fetch", calls["fetch"] + 1)
            or VenueOrderState(
                request_id=request.request_id,
                client_order_id=client_order_id,
                venue=request.venue,
                execution_mode="sandbox",
                sandbox=True,
                intent_id=request.intent_id,
                venue_order_id="order-1",
                state="open",
                terminal=False,
                updated_at=datetime(2026, 4, 7, 12, 1, 1, tzinfo=UTC),
            )
        ),
        cancel_fn=lambda client_order_id, request: (
            calls.__setitem__("cancel", calls["cancel"] + 1)
            or VenueOrderState(
                request_id=request.request_id,
                client_order_id=client_order_id,
                venue=request.venue,
                execution_mode="sandbox",
                sandbox=True,
                intent_id=request.intent_id,
                venue_order_id="order-1",
                state="canceled",
                terminal=True,
                updated_at=datetime(2026, 4, 7, 12, 1, 2, tzinfo=UTC),
            )
        ),
    )

    request_artifact, result_artifact, status_artifact = execute_sandbox_requests(
        session_id="session-0001",
        run_id=result.run_id,
        journal_path=result.journal_path,
        market_state_path=market_state_path,
        venue_constraints_path=venue_constraints_path,
        existing_status_path=tmp_path / "session-0001.execution_status.json",
        adapter=adapter,
        observed_at=datetime(2026, 4, 7, 12, 1, tzinfo=UTC),
    )

    assert request_artifact.request_count >= 1
    assert result_artifact.results[0].status == "accepted"
    assert status_artifact.statuses[0].state == "canceled"
    assert calls == {"submit": 1, "fetch": 1, "cancel": 1}

    existing_status_path = tmp_path / "session-0001.execution_status.json"
    existing_status_path.write_text(
        json.dumps(status_artifact.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _, duplicate_results, duplicate_statuses = execute_sandbox_requests(
        session_id="session-0001",
        run_id=result.run_id,
        journal_path=result.journal_path,
        market_state_path=market_state_path,
        venue_constraints_path=venue_constraints_path,
        existing_status_path=existing_status_path,
        adapter=adapter,
        observed_at=datetime(2026, 4, 7, 12, 2, tzinfo=UTC),
    )

    assert duplicate_results.results[0].status == "duplicate"
    assert duplicate_statuses.statuses[0].state == "canceled"
    assert calls == {"submit": 1, "fetch": 1, "cancel": 1}
