from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.runtime.history import append_forward_paper_history
from crypto_agent.runtime.loop import build_forward_paper_runtime_paths, run_forward_paper_runtime
from crypto_agent.runtime.models import (
    ForwardPaperHistoryEvent,
    ForwardPaperRecoveryStatus,
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


def _tick(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_runtime_recovery_writes_recovery_status_and_preserves_continuity(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-runtime-recovery"
    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.sessions_dir.mkdir(parents=True, exist_ok=True)

    started_at = _tick(2026, 4, 6, 11, 0)
    interrupted_session = ForwardPaperSessionSummary(
        runtime_id=runtime_id,
        session_id="session-0001",
        session_number=1,
        status="running",
        replay_path=FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        scheduled_at=started_at,
        started_at=started_at,
    )
    (paths.sessions_dir / "session-0001.json").write_text(
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
        account_state_path=paths.account_state_path,
        reconciliation_report_path=paths.reconciliation_report_path,
        recovery_status_path=paths.recovery_status_path,
        execution_state_dir=paths.execution_state_dir,
        live_control_config_path=paths.live_control_config_path,
        live_control_status_path=paths.live_control_status_path,
        readiness_status_path=paths.readiness_status_path,
        manual_control_state_path=paths.manual_control_state_path,
        shadow_canary_evaluation_path=paths.shadow_canary_evaluation_path,
        soak_evaluation_path=paths.soak_evaluation_path,
        shadow_evaluation_path=paths.shadow_evaluation_path,
        live_gate_decision_path=paths.live_gate_decision_path,
        live_gate_threshold_summary_path=paths.live_gate_threshold_summary_path,
        live_gate_report_path=paths.live_gate_report_path,
        live_launch_verdict_path=paths.live_launch_verdict_path,
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
        tick_times=[_tick(2026, 4, 6, 11, 1)],
    )

    recovery_status = ForwardPaperRecoveryStatus.model_validate(
        json.loads(result.recovery_status_path.read_text(encoding="utf-8"))
    )
    status_after = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert recovery_status.status == "recovered"
    assert recovery_status.reconciliation_status == "clean"
    assert recovery_status.recovered_session_id == "session-0001"
    assert recovery_status.recovery_note == "recovered_after_restart"
    assert status_after.interrupted_session_count == 1
    assert status_after.completed_session_count == 1
    assert result.session_summaries[0].session_id == "session-0002"


def test_runtime_recovery_is_not_reapplied_after_clean_restart(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-runtime-stale-recovery"

    first_result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_tick(2026, 4, 6, 12, 0)],
    )
    initial_status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(first_result.status_path.read_text(encoding="utf-8"))
    )

    second_result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_tick(2026, 4, 6, 12, 1)],
    )
    status_after = ForwardPaperRuntimeStatus.model_validate(
        json.loads(second_result.status_path.read_text(encoding="utf-8"))
    )
    recovery_status = ForwardPaperRecoveryStatus.model_validate(
        json.loads(second_result.recovery_status_path.read_text(encoding="utf-8"))
    )

    assert initial_status.interrupted_session_count == 0
    assert status_after.interrupted_session_count == 0
    assert recovery_status.status == "clean"
    assert recovery_status.recovered_session_id is None
