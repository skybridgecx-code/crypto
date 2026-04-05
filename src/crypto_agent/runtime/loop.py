from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path

from crypto_agent.cli.main import PaperRunResult, run_paper_replay
from crypto_agent.config import Settings
from crypto_agent.enums import Mode
from crypto_agent.runtime.history import append_forward_paper_history
from crypto_agent.runtime.models import (
    ForwardPaperHistoryEvent,
    ForwardPaperRuntimePaths,
    ForwardPaperRuntimeResult,
    ForwardPaperRuntimeStatus,
    ForwardPaperSessionSummary,
)
from crypto_agent.runtime.session_registry import upsert_forward_paper_registry_entry


class RuntimeAlreadyActiveError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("scheduled tick timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _write_runtime_status(status: ForwardPaperRuntimeStatus) -> None:
    status.status_path.parent.mkdir(parents=True, exist_ok=True)
    status.status_path.write_text(
        json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_runtime_status(path: Path) -> ForwardPaperRuntimeStatus:
    return ForwardPaperRuntimeStatus.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _session_summary_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.json"


def _write_session_summary(summary: ForwardPaperSessionSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_session_summary(path: Path) -> ForwardPaperSessionSummary:
    return ForwardPaperSessionSummary.model_validate(json.loads(path.read_text(encoding="utf-8")))


def build_forward_paper_runtime_paths(
    runs_dir: Path,
    runtime_id: str,
) -> ForwardPaperRuntimePaths:
    runtime_dir = runs_dir / runtime_id
    return ForwardPaperRuntimePaths(
        runtime_dir=runtime_dir,
        status_path=runtime_dir / "forward_paper_status.json",
        history_path=runtime_dir / "forward_paper_history.jsonl",
        sessions_dir=runtime_dir / "sessions",
        registry_path=runs_dir / "forward_paper_registry.json",
    )


def _initial_runtime_status(
    *,
    runtime_id: str,
    replay_path: Path,
    starting_equity_usd: float,
    session_interval_seconds: int,
    now: datetime,
    paths: ForwardPaperRuntimePaths,
) -> ForwardPaperRuntimeStatus:
    return ForwardPaperRuntimeStatus(
        runtime_id=runtime_id,
        mode=Mode.PAPER,
        replay_path=replay_path,
        starting_equity_usd=starting_equity_usd,
        session_interval_seconds=session_interval_seconds,
        status="idle",
        next_session_number=1,
        updated_at=now,
        status_path=paths.status_path,
        history_path=paths.history_path,
        sessions_dir=paths.sessions_dir,
        registry_path=paths.registry_path,
    )


def _ensure_runtime_status(
    *,
    settings: Settings,
    replay_path: Path,
    runtime_id: str,
    starting_equity_usd: float,
    session_interval_seconds: int,
    now: datetime,
    recover_interrupted: bool,
) -> ForwardPaperRuntimeStatus:
    if settings.mode is not Mode.PAPER:
        raise ValueError("Forward paper runtime requires settings.mode to be paper.")

    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    runtime_dir = paths.runtime_dir
    summary_conflict = runtime_dir / "summary.json"
    manifest_conflict = runtime_dir / "manifest.json"
    if runtime_dir.exists() and (summary_conflict.exists() or manifest_conflict.exists()):
        raise ValueError(f"Runtime id conflicts with existing run artifacts: {runtime_id}")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.sessions_dir.mkdir(parents=True, exist_ok=True)

    if not paths.status_path.exists():
        status = _initial_runtime_status(
            runtime_id=runtime_id,
            replay_path=replay_path,
            starting_equity_usd=starting_equity_usd,
            session_interval_seconds=session_interval_seconds,
            now=now,
            paths=paths,
        )
        _write_runtime_status(status)
        upsert_forward_paper_registry_entry(paths.registry_path, status)
        return status

    status = _load_runtime_status(paths.status_path)
    if status.replay_path != replay_path:
        raise ValueError("Existing runtime replay_path does not match requested replay_path")
    if status.starting_equity_usd != starting_equity_usd:
        raise ValueError("Existing runtime starting_equity_usd does not match requested value")
    if status.session_interval_seconds != session_interval_seconds:
        raise ValueError("Existing runtime interval does not match requested value")
    if status.status == "running" and status.active_session_id is not None:
        if not recover_interrupted:
            raise RuntimeAlreadyActiveError(
                f"Forward paper runtime is already active: {runtime_id}"
            )
        status = _recover_interrupted_session(status=status, recovered_at=now)

    _write_runtime_status(status)
    upsert_forward_paper_registry_entry(paths.registry_path, status)
    return status


def _recover_interrupted_session(
    *,
    status: ForwardPaperRuntimeStatus,
    recovered_at: datetime,
) -> ForwardPaperRuntimeStatus:
    if status.active_session_id is None:
        return status.model_copy(update={"status": "idle", "updated_at": recovered_at})

    session_path = _session_summary_path(status.sessions_dir, status.active_session_id)
    if session_path.exists():
        session_summary = _load_session_summary(session_path).model_copy(
            update={
                "status": "interrupted",
                "completed_at": recovered_at,
                "recovery_note": "recovered_after_restart",
                "all_artifact_paths_exist": False,
            }
        )
    else:
        session_number = status.next_session_number - 1 if status.next_session_number > 1 else 1
        session_summary = ForwardPaperSessionSummary(
            runtime_id=status.runtime_id,
            session_id=status.active_session_id,
            session_number=session_number,
            mode=Mode.PAPER,
            status="interrupted",
            replay_path=status.replay_path,
            scheduled_at=status.active_session_started_at or recovered_at,
            started_at=status.active_session_started_at or recovered_at,
            completed_at=recovered_at,
            recovery_note="recovered_after_restart_without_session_file",
            all_artifact_paths_exist=False,
        )

    _write_session_summary(session_summary, session_path)
    append_forward_paper_history(
        status.history_path,
        ForwardPaperHistoryEvent(
            event_type="session.interrupted",
            runtime_id=status.runtime_id,
            session_id=session_summary.session_id,
            session_number=session_summary.session_number,
            occurred_at=recovered_at,
            status="interrupted",
            message=session_summary.recovery_note,
        ),
    )

    recovered_status = status.model_copy(
        update={
            "status": "idle",
            "active_session_id": None,
            "active_session_started_at": None,
            "last_session_id": session_summary.session_id,
            "interrupted_session_count": status.interrupted_session_count + 1,
            "updated_at": recovered_at,
        }
    )
    _write_runtime_status(recovered_status)
    upsert_forward_paper_registry_entry(recovered_status.registry_path, recovered_status)
    return recovered_status


def _start_session(
    *,
    status: ForwardPaperRuntimeStatus,
    scheduled_at: datetime,
) -> tuple[ForwardPaperRuntimeStatus, ForwardPaperSessionSummary, Path]:
    session_number = status.next_session_number
    session_id = f"session-{session_number:04d}"
    started_at = scheduled_at
    session_summary = ForwardPaperSessionSummary(
        runtime_id=status.runtime_id,
        session_id=session_id,
        session_number=session_number,
        mode=Mode.PAPER,
        status="running",
        replay_path=status.replay_path,
        scheduled_at=scheduled_at,
        started_at=started_at,
        all_artifact_paths_exist=False,
    )
    session_path = _session_summary_path(status.sessions_dir, session_id)
    _write_session_summary(session_summary, session_path)
    append_forward_paper_history(
        status.history_path,
        ForwardPaperHistoryEvent(
            event_type="session.started",
            runtime_id=status.runtime_id,
            session_id=session_id,
            session_number=session_number,
            occurred_at=started_at,
            status="running",
        ),
    )

    running_status = status.model_copy(
        update={
            "status": "running",
            "next_session_number": session_number + 1,
            "active_session_id": session_id,
            "active_session_started_at": started_at,
            "updated_at": started_at,
        }
    )
    _write_runtime_status(running_status)
    upsert_forward_paper_registry_entry(running_status.registry_path, running_status)
    return running_status, session_summary, session_path


def _completed_session_summary(
    *,
    session_summary: ForwardPaperSessionSummary,
    result: PaperRunResult,
    completed_at: datetime,
) -> ForwardPaperSessionSummary:
    path_exists = {
        "journal_path": result.journal_path.exists(),
        "summary_path": result.summary_path.exists(),
        "report_path": result.report_path.exists(),
        "trade_ledger_path": result.trade_ledger_path.exists(),
    }
    return session_summary.model_copy(
        update={
            "status": "completed",
            "completed_at": completed_at,
            "run_id": result.run_id,
            "journal_path": result.journal_path,
            "summary_path": result.summary_path,
            "report_path": result.report_path,
            "trade_ledger_path": result.trade_ledger_path,
            "quality_issue_count": result.quality_issue_count,
            "scorecard": result.scorecard,
            "pnl": result.pnl,
            "review_packet": result.review_packet,
            "operator_summary": result.operator_summary,
            "artifact_paths_exist": path_exists,
            "all_artifact_paths_exist": all(path_exists.values()),
        }
    )


def _failed_session_summary(
    *,
    session_summary: ForwardPaperSessionSummary,
    failed_at: datetime,
    error: Exception,
) -> ForwardPaperSessionSummary:
    return session_summary.model_copy(
        update={
            "status": "failed",
            "completed_at": failed_at,
            "error_message": str(error),
            "all_artifact_paths_exist": False,
        }
    )


def _complete_status(
    *,
    status: ForwardPaperRuntimeStatus,
    session_summary: ForwardPaperSessionSummary,
    completed_at: datetime,
) -> ForwardPaperRuntimeStatus:
    next_scheduled_at = session_summary.scheduled_at + timedelta(
        seconds=status.session_interval_seconds
    )
    completed_session_count = status.completed_session_count
    failed_session_count = status.failed_session_count
    last_error_message = status.last_error_message
    if session_summary.status == "completed":
        completed_session_count += 1
        last_error_message = None
    elif session_summary.status == "failed":
        failed_session_count += 1
        last_error_message = session_summary.error_message

    completed_status = status.model_copy(
        update={
            "status": "idle",
            "active_session_id": None,
            "active_session_started_at": None,
            "last_session_id": session_summary.session_id,
            "completed_session_count": completed_session_count,
            "failed_session_count": failed_session_count,
            "next_scheduled_at": next_scheduled_at,
            "last_error_message": last_error_message,
            "updated_at": completed_at,
        }
    )
    _write_runtime_status(completed_status)
    upsert_forward_paper_registry_entry(completed_status.registry_path, completed_status)
    return completed_status


def _iter_scheduled_times(
    *,
    tick_times: Iterable[datetime] | None,
    max_sessions: int | None,
    initial_next_scheduled_at: datetime | None,
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
    interval_seconds: int,
) -> list[datetime]:
    if tick_times is not None:
        normalized = [_normalize_datetime(tick) for tick in tick_times]
        if max_sessions is not None:
            return normalized[:max_sessions]
        return normalized

    scheduled_times: list[datetime] = []
    if max_sessions is None:
        raise ValueError("Real-clock forward paper runtime requires max_sessions to be explicit.")

    next_scheduled_at = initial_next_scheduled_at
    for _ in range(max_sessions):
        due_at = (
            _normalize_datetime(next_scheduled_at)
            if next_scheduled_at
            else _normalize_datetime(now_fn())
        )
        current_time = _normalize_datetime(now_fn())
        delay_seconds = (due_at - current_time).total_seconds()
        if delay_seconds > 0:
            sleep_fn(delay_seconds)
        scheduled_times.append(due_at)
        next_scheduled_at = due_at + timedelta(seconds=interval_seconds)
    return scheduled_times


def run_forward_paper_runtime(
    replay_path: str | Path,
    *,
    settings: Settings,
    runtime_id: str,
    session_interval_seconds: int,
    equity_usd: float = 100_000.0,
    max_sessions: int | None = None,
    tick_times: Iterable[datetime] | None = None,
    recover_interrupted: bool = True,
    now_fn: Callable[[], datetime] = _utc_now,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> ForwardPaperRuntimeResult:
    replay_fixture_path = Path(replay_path)
    scheduled_ticks = (
        [_normalize_datetime(tick) for tick in tick_times] if tick_times is not None else None
    )
    initial_now = scheduled_ticks[0] if scheduled_ticks else _normalize_datetime(now_fn())
    status = _ensure_runtime_status(
        settings=settings,
        replay_path=replay_fixture_path,
        runtime_id=runtime_id,
        starting_equity_usd=equity_usd,
        session_interval_seconds=session_interval_seconds,
        now=initial_now,
        recover_interrupted=recover_interrupted,
    )
    scheduled_times = _iter_scheduled_times(
        tick_times=scheduled_ticks,
        max_sessions=max_sessions,
        initial_next_scheduled_at=status.next_scheduled_at,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
        interval_seconds=session_interval_seconds,
    )

    completed_sessions: list[ForwardPaperSessionSummary] = []

    for scheduled_at in scheduled_times:
        status, running_session, session_path = _start_session(
            status=status,
            scheduled_at=scheduled_at,
        )
        run_id = f"{runtime_id}-{running_session.session_id}"
        try:
            result = run_paper_replay(
                replay_fixture_path,
                settings=settings,
                run_id=run_id,
                equity_usd=equity_usd,
            )
            completed_at = _normalize_datetime(now_fn())
            completed_session = _completed_session_summary(
                session_summary=running_session,
                result=result,
                completed_at=completed_at,
            )
            _write_session_summary(completed_session, session_path)
            append_forward_paper_history(
                status.history_path,
                ForwardPaperHistoryEvent(
                    event_type="session.completed",
                    runtime_id=runtime_id,
                    session_id=completed_session.session_id,
                    session_number=completed_session.session_number,
                    occurred_at=completed_at,
                    status="completed",
                    run_id=completed_session.run_id,
                ),
            )
            status = _complete_status(
                status=status,
                session_summary=completed_session,
                completed_at=completed_at,
            )
            completed_sessions.append(completed_session)
        except Exception as exc:
            failed_at = _normalize_datetime(now_fn())
            failed_session = _failed_session_summary(
                session_summary=running_session,
                failed_at=failed_at,
                error=exc,
            )
            _write_session_summary(failed_session, session_path)
            append_forward_paper_history(
                status.history_path,
                ForwardPaperHistoryEvent(
                    event_type="session.failed",
                    runtime_id=runtime_id,
                    session_id=failed_session.session_id,
                    session_number=failed_session.session_number,
                    occurred_at=failed_at,
                    status="failed",
                    run_id=failed_session.run_id,
                    message=failed_session.error_message,
                ),
            )
            status = _complete_status(
                status=status,
                session_summary=failed_session,
                completed_at=failed_at,
            )
            raise

    return ForwardPaperRuntimeResult(
        runtime_id=runtime_id,
        registry_path=status.registry_path,
        status_path=status.status_path,
        history_path=status.history_path,
        sessions_dir=status.sessions_dir,
        session_count=len(completed_sessions),
        session_summaries=completed_sessions,
    )
