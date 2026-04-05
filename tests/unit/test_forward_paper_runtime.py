from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from crypto_agent.cli.forward_paper import main
from crypto_agent.config import load_settings
from crypto_agent.runtime.history import append_forward_paper_history
from crypto_agent.runtime.loop import (
    RuntimeAlreadyActiveError,
    build_forward_paper_runtime_paths,
    run_forward_paper_runtime,
)
from crypto_agent.runtime.models import (
    ForwardPaperHistoryEvent,
    ForwardPaperRuntimeStatus,
    ForwardPaperSessionSummary,
)
from crypto_agent.runtime.session_registry import upsert_forward_paper_registry_entry

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


def _write_paper_config(tmp_path: Path) -> Path:
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
                "    - ETHUSDT",
                "  quote_currency: USDT",
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
    return config_path


def _tick(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_forward_paper_runtime_runs_repeated_sessions_and_persists_status(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-demo"
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=2,
        tick_times=[
            _tick(2026, 4, 5, 9, 0),
            _tick(2026, 4, 5, 9, 1),
        ],
    )

    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))

    assert result.registry_path.exists()
    assert result.status_path.exists()
    assert result.history_path.exists()
    assert result.sessions_dir.exists()
    assert result.session_count == 2
    assert [session.session_id for session in result.session_summaries] == [
        "session-0001",
        "session-0002",
    ]
    assert status.runtime_id == runtime_id
    assert status.status == "idle"
    assert status.completed_session_count == 2
    assert status.failed_session_count == 0
    assert status.interrupted_session_count == 0
    assert status.next_session_number == 3
    assert status.last_session_id == "session-0002"
    assert status.next_scheduled_at == _tick(2026, 4, 5, 9, 2)
    assert registry["runtime_count"] == 1
    assert registry["runtimes"][0]["runtime_id"] == runtime_id
    assert registry["runtimes"][0]["status"] == "idle"

    for session in result.session_summaries:
        session_path = result.sessions_dir / f"{session.session_id}.json"
        summary = ForwardPaperSessionSummary.model_validate(
            json.loads(session_path.read_text(encoding="utf-8"))
        )
        linked_run_summary = json.loads(Path(summary.summary_path).read_text(encoding="utf-8"))
        assert summary.status == "completed"
        assert summary.run_id == f"{runtime_id}-{summary.session_id}"
        assert summary.all_artifact_paths_exist is True
        assert summary.scorecard == session.scorecard
        assert summary.pnl == session.pnl
        assert linked_run_summary["run_id"] == summary.run_id
        assert linked_run_summary["scorecard"] == summary.scorecard.model_dump(mode="json")
        assert linked_run_summary["pnl"] == summary.pnl.model_dump(mode="json")


def test_forward_paper_runtime_recovers_interrupted_session_on_restart(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-recovery"
    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.sessions_dir.mkdir(parents=True, exist_ok=True)

    started_at = _tick(2026, 4, 5, 10, 0)
    interrupted_session = ForwardPaperSessionSummary(
        runtime_id=runtime_id,
        session_id="session-0001",
        session_number=1,
        status="running",
        replay_path=FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        scheduled_at=started_at,
        started_at=started_at,
    )
    interrupted_session_path = paths.sessions_dir / "session-0001.json"
    interrupted_session_path.write_text(
        json.dumps(interrupted_session.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    status = ForwardPaperRuntimeStatus(
        runtime_id=runtime_id,
        replay_path=FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        starting_equity_usd=100_000.0,
        session_interval_seconds=60,
        status="running",
        next_session_number=2,
        active_session_id="session-0001",
        active_session_started_at=started_at,
        updated_at=started_at,
        status_path=paths.status_path,
        history_path=paths.history_path,
        sessions_dir=paths.sessions_dir,
        registry_path=paths.registry_path,
    )
    paths.status_path.write_text(
        json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    upsert_forward_paper_registry_entry(paths.registry_path, status)
    append_forward_paper_history(
        paths.history_path,
        ForwardPaperHistoryEvent(
            event_type="session.started",
            runtime_id=runtime_id,
            session_id="session-0001",
            session_number=1,
            occurred_at=started_at,
            status="running",
        ),
    )

    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_tick(2026, 4, 5, 10, 1)],
    )

    recovered = ForwardPaperSessionSummary.model_validate(
        json.loads(interrupted_session_path.read_text(encoding="utf-8"))
    )
    status_after = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert recovered.status == "interrupted"
    assert recovered.recovery_note == "recovered_after_restart"
    assert recovered.completed_at == _tick(2026, 4, 5, 10, 1)
    assert result.session_count == 1
    assert result.session_summaries[0].session_id == "session-0002"
    assert status_after.interrupted_session_count == 1
    assert status_after.completed_session_count == 1
    assert status_after.next_session_number == 3


def test_forward_paper_runtime_prevents_duplicate_active_session_without_recovery(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-duplicate"
    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.sessions_dir.mkdir(parents=True, exist_ok=True)

    started_at = _tick(2026, 4, 5, 11, 0)
    status = ForwardPaperRuntimeStatus(
        runtime_id=runtime_id,
        replay_path=FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        starting_equity_usd=100_000.0,
        session_interval_seconds=60,
        status="running",
        next_session_number=2,
        active_session_id="session-0001",
        active_session_started_at=started_at,
        updated_at=started_at,
        status_path=paths.status_path,
        history_path=paths.history_path,
        sessions_dir=paths.sessions_dir,
        registry_path=paths.registry_path,
    )
    paths.status_path.write_text(
        json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    upsert_forward_paper_registry_entry(paths.registry_path, status)

    with pytest.raises(RuntimeAlreadyActiveError):
        run_forward_paper_runtime(
            FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
            settings=settings,
            runtime_id=runtime_id,
            session_interval_seconds=60,
            max_sessions=1,
            tick_times=[_tick(2026, 4, 5, 11, 1)],
            recover_interrupted=False,
        )


def test_cli_forward_paper_runtime_runs_single_session_and_prints_status(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_paper_config(tmp_path)

    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_breakout_long.jsonl"),
            "--config",
            str(config_path),
            "--runtime-id",
            "forward-paper-cli",
            "--session-interval-seconds",
            "60",
            "--max-sessions",
            "1",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["runtime_id"] == "forward-paper-cli"
    assert Path(output["registry_path"]).exists()
    assert Path(output["status_path"]).exists()
    assert Path(output["history_path"]).exists()
    assert Path(output["sessions_dir"]).exists()
    assert output["session_count"] == 1
    assert output["session_ids"] == ["session-0001"]
