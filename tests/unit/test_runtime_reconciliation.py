from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from crypto_agent.config import load_settings
from crypto_agent.runtime.loop import RuntimeAccountMismatchError, run_forward_paper_runtime
from crypto_agent.runtime.models import (
    ForwardPaperReconciliationReport,
    ForwardPaperRecoveryStatus,
    ForwardPaperRuntimeAccountState,
    ForwardPaperRuntimeStatus,
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


def _tick(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_runtime_reconciliation_writes_clean_account_state_and_report(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id="forward-paper-reconcile-demo",
        session_interval_seconds=300,
        max_sessions=2,
        tick_times=[
            _tick(2026, 4, 6, 9, 0),
            _tick(2026, 4, 6, 9, 5),
        ],
    )

    account_state = ForwardPaperRuntimeAccountState.model_validate(
        json.loads(result.account_state_path.read_text(encoding="utf-8"))
    )
    report = ForwardPaperReconciliationReport.model_validate(
        json.loads(result.reconciliation_report_path.read_text(encoding="utf-8"))
    )
    recovery_status = ForwardPaperRecoveryStatus.model_validate(
        json.loads(result.recovery_status_path.read_text(encoding="utf-8"))
    )
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert account_state.as_of_session_id == "session-0002"
    assert account_state.as_of_run_id == result.session_summaries[-1].run_id
    assert account_state.positions
    assert account_state.ending_equity_usd == pytest.approx(
        result.session_summaries[-1].pnl.ending_equity_usd
    )
    assert result.session_summaries[1].pnl.starting_equity_usd == pytest.approx(
        result.session_summaries[0].pnl.ending_equity_usd
    )

    assert report.status == "clean"
    assert report.checked_session_count == 2
    assert report.executed_session_count == 2
    assert report.local_account_state_present is True
    assert report.expected_account_state == account_state
    assert report.local_account_state == account_state
    assert report.differences == []

    assert recovery_status.status == "clean"
    assert recovery_status.reconciliation_status == "clean"
    assert recovery_status.recovered_session_id is None

    assert status.reconciliation_status == "clean"
    assert status.mismatch_detected is False
    assert status.last_reconciled_session_id == "session-0002"


def test_runtime_reconciliation_blocks_on_account_state_mismatch(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-reconcile-mismatch"
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=300,
        max_sessions=1,
        tick_times=[_tick(2026, 4, 6, 10, 0)],
    )

    corrupted_account_state = json.loads(result.account_state_path.read_text(encoding="utf-8"))
    corrupted_account_state["cash_balance_usd"] += 1.0
    result.account_state_path.write_text(
        json.dumps(corrupted_account_state, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeAccountMismatchError):
        run_forward_paper_runtime(
            FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
            settings=settings,
            runtime_id=runtime_id,
            session_interval_seconds=300,
            max_sessions=1,
            tick_times=[_tick(2026, 4, 6, 10, 5)],
        )

    report = ForwardPaperReconciliationReport.model_validate(
        json.loads(result.reconciliation_report_path.read_text(encoding="utf-8"))
    )
    recovery_status = ForwardPaperRecoveryStatus.model_validate(
        json.loads(result.recovery_status_path.read_text(encoding="utf-8"))
    )
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert report.status == "mismatch"
    assert report.differences
    assert "cash_balance_usd" in report.differences[0]
    assert recovery_status.status == "blocked_mismatch"
    assert recovery_status.reconciliation_status == "mismatch"
    assert status.reconciliation_status == "mismatch"
    assert status.mismatch_detected is True
