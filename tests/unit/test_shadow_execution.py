from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.execution.shadow import build_shadow_execution_artifacts
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
        venue="binance_spot",
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
            venue="binance_spot",
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


def test_shadow_execution_builds_would_send_artifacts_from_run_journal(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="shadow-demo",
    )
    market_state_path, venue_constraints_path = _write_live_files(tmp_path)

    requests, results, statuses = build_shadow_execution_artifacts(
        session_id="session-0001",
        run_id=result.run_id,
        journal_path=result.journal_path,
        market_state_path=market_state_path,
        venue_constraints_path=venue_constraints_path,
        observed_at=datetime(2026, 4, 7, 12, 1, tzinfo=UTC),
    )

    assert requests.request_count >= 1
    assert requests.request_count == results.result_count == statuses.status_count
    assert all(result.status in {"would_send", "rejected"} for result in results.results)
    assert all(status.terminal is True for status in statuses.statuses)
    assert all(status.state in {"shadow_only", "rejected"} for status in statuses.statuses)
