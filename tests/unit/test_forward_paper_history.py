from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.runtime.history import read_forward_paper_history
from crypto_agent.runtime.loop import run_forward_paper_runtime
from crypto_agent.runtime.models import ForwardPaperRuntimeRegistry, ForwardPaperRuntimeStatus

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


def _tick(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_forward_paper_history_and_registry_reconcile_to_single_run_outputs(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id="forward-paper-history-demo",
        session_interval_seconds=300,
        max_sessions=2,
        tick_times=[
            _tick(2026, 4, 5, 12, 0),
            _tick(2026, 4, 5, 12, 5),
        ],
    )

    history = read_forward_paper_history(result.history_path)
    registry = ForwardPaperRuntimeRegistry.model_validate(
        json.loads(result.registry_path.read_text(encoding="utf-8"))
    )
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert [event.event_type for event in history] == [
        "session.started",
        "session.completed",
        "session.started",
        "session.completed",
    ]
    assert [event.session_id for event in history] == [
        "session-0001",
        "session-0001",
        "session-0002",
        "session-0002",
    ]
    assert registry.runtime_count == 1
    assert registry.runtimes[0].runtime_id == "forward-paper-history-demo"
    assert registry.runtimes[0].last_session_id == "session-0002"
    assert status.completed_session_count == 2
    assert status.last_session_id == "session-0002"

    fee_total = 0.0
    net_pnl_total = 0.0
    for session in result.session_summaries:
        session_payload = json.loads(
            (result.sessions_dir / f"{session.session_id}.json").read_text(encoding="utf-8")
        )
        run_summary = json.loads(Path(str(session.summary_path)).read_text(encoding="utf-8"))
        assert session_payload["run_id"] == run_summary["run_id"]
        assert session_payload["journal_path"] == run_summary["journal_path"]
        assert session_payload["report_path"] == str(session.report_path)
        assert session_payload["trade_ledger_path"] == run_summary["trade_ledger_path"]
        assert session_payload["scorecard"] == run_summary["scorecard"]
        assert session_payload["pnl"] == run_summary["pnl"]
        assert session_payload["operator_summary"] == run_summary["operator_summary"]
        fee_total += float(session_payload["pnl"]["total_fee_usd"])
        net_pnl_total += float(session_payload["pnl"]["net_realized_pnl_usd"])

    assert fee_total > 0
    assert net_pnl_total != 0
