from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from crypto_agent.cli.main import PaperRunResult, run_paper_replay
from crypto_agent.config import Settings
from crypto_agent.enums import Mode
from crypto_agent.market_data.live_adapter import (
    BinanceSpotLiveMarketDataAdapter,
    LiveMarketDataUnavailableError,
)
from crypto_agent.market_data.live_models import LiveFeedHealth, LiveMarketState
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


def _session_market_input_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.live_input.jsonl"


def _session_market_state_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.live_market_state.json"


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
        live_market_status_path=runtime_dir / "live_market_status.json",
        venue_constraints_path=runtime_dir / "venue_constraints.json",
    )


def _write_live_market_state(paths: ForwardPaperRuntimePaths, state: LiveMarketState) -> None:
    paths.live_market_status_path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths.venue_constraints_path.write_text(
        json.dumps(state.constraint_registry.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_live_market_input(path: Path, state: LiveMarketState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for candle in state.candles:
            handle.write(json.dumps(candle.model_dump(mode="json"), sort_keys=True) + "\n")


def _initial_runtime_status(
    *,
    runtime_id: str,
    market_source: Literal["replay", "binance_spot"],
    replay_path: Path | None,
    live_symbol: str | None,
    live_interval: str | None,
    live_lookback_candles: int | None,
    feed_stale_after_seconds: int | None,
    starting_equity_usd: float,
    session_interval_seconds: int,
    now: datetime,
    paths: ForwardPaperRuntimePaths,
) -> ForwardPaperRuntimeStatus:
    return ForwardPaperRuntimeStatus(
        runtime_id=runtime_id,
        mode=Mode.PAPER,
        market_source=market_source,
        replay_path=replay_path,
        live_symbol=live_symbol,
        live_interval=live_interval,
        live_lookback_candles=live_lookback_candles,
        feed_stale_after_seconds=feed_stale_after_seconds,
        starting_equity_usd=starting_equity_usd,
        session_interval_seconds=session_interval_seconds,
        status="idle",
        next_session_number=1,
        updated_at=now,
        status_path=paths.status_path,
        history_path=paths.history_path,
        sessions_dir=paths.sessions_dir,
        registry_path=paths.registry_path,
        live_market_status_path=paths.live_market_status_path,
        venue_constraints_path=paths.venue_constraints_path,
    )


def _ensure_runtime_status(
    *,
    settings: Settings,
    market_source: Literal["replay", "binance_spot"],
    replay_path: Path | None,
    live_symbol: str | None,
    live_interval: str | None,
    live_lookback_candles: int | None,
    feed_stale_after_seconds: int | None,
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

    if market_source == "replay" and replay_path is None:
        raise ValueError("Replay market source requires replay_path")
    if market_source == "binance_spot" and (
        live_symbol is None
        or live_interval is None
        or live_lookback_candles is None
        or feed_stale_after_seconds is None
    ):
        raise ValueError(
            "Live market source requires symbol, interval, lookback, and stale feed threshold"
        )

    if not paths.status_path.exists():
        status = _initial_runtime_status(
            runtime_id=runtime_id,
            market_source=market_source,
            replay_path=replay_path,
            live_symbol=live_symbol,
            live_interval=live_interval,
            live_lookback_candles=live_lookback_candles,
            feed_stale_after_seconds=feed_stale_after_seconds,
            starting_equity_usd=starting_equity_usd,
            session_interval_seconds=session_interval_seconds,
            now=now,
            paths=paths,
        )
        _write_runtime_status(status)
        upsert_forward_paper_registry_entry(paths.registry_path, status)
        return status

    status = _load_runtime_status(paths.status_path)
    if status.market_source != market_source:
        raise ValueError("Existing runtime market_source does not match requested market_source")
    if status.replay_path != replay_path:
        raise ValueError("Existing runtime replay_path does not match requested replay_path")
    if status.live_symbol != live_symbol:
        raise ValueError("Existing runtime live_symbol does not match requested value")
    if status.live_interval != live_interval:
        raise ValueError("Existing runtime live_interval does not match requested value")
    if status.live_lookback_candles != live_lookback_candles:
        raise ValueError("Existing runtime lookback does not match requested value")
    if status.feed_stale_after_seconds != feed_stale_after_seconds:
        raise ValueError("Existing runtime stale-feed threshold does not match requested value")
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
            market_source=status.market_source,
            live_symbol=status.live_symbol,
            live_interval=status.live_interval,
            status="interrupted",
            replay_path=status.replay_path,
            venue_constraints_path=(
                status.venue_constraints_path if status.market_source == "binance_spot" else None
            ),
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
    session_summary = ForwardPaperSessionSummary(
        runtime_id=status.runtime_id,
        session_id=session_id,
        session_number=session_number,
        mode=Mode.PAPER,
        market_source=status.market_source,
        live_symbol=status.live_symbol,
        live_interval=status.live_interval,
        status="running",
        replay_path=status.replay_path,
        venue_constraints_path=(
            status.venue_constraints_path if status.market_source == "binance_spot" else None
        ),
        scheduled_at=scheduled_at,
        started_at=scheduled_at,
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
            occurred_at=scheduled_at,
            status="running",
        ),
    )

    running_status = status.model_copy(
        update={
            "status": "running",
            "next_session_number": session_number + 1,
            "active_session_id": session_id,
            "active_session_started_at": scheduled_at,
            "updated_at": scheduled_at,
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
    if session_summary.market_input_path is not None:
        path_exists["market_input_path"] = session_summary.market_input_path.exists()
    if session_summary.market_state_path is not None:
        path_exists["market_state_path"] = session_summary.market_state_path.exists()
    if session_summary.venue_constraints_path is not None:
        path_exists["venue_constraints_path"] = session_summary.venue_constraints_path.exists()
    return session_summary.model_copy(
        update={
            "status": "completed",
            "session_outcome": "executed",
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


def _skipped_session_summary(
    *,
    session_summary: ForwardPaperSessionSummary,
    completed_at: datetime,
    outcome: str,
    feed_health: LiveFeedHealth,
) -> ForwardPaperSessionSummary:
    path_exists = {}
    if session_summary.market_input_path is not None:
        path_exists["market_input_path"] = session_summary.market_input_path.exists()
    if session_summary.market_state_path is not None:
        path_exists["market_state_path"] = session_summary.market_state_path.exists()
    if session_summary.venue_constraints_path is not None:
        path_exists["venue_constraints_path"] = session_summary.venue_constraints_path.exists()
    return session_summary.model_copy(
        update={
            "status": "completed",
            "session_outcome": outcome,
            "completed_at": completed_at,
            "feed_health": feed_health,
            "artifact_paths_exist": path_exists,
            "all_artifact_paths_exist": all(path_exists.values()) if path_exists else True,
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

    if max_sessions is None:
        raise ValueError("Real-clock forward paper runtime requires max_sessions to be explicit.")

    scheduled_times: list[datetime] = []
    next_scheduled_at = initial_next_scheduled_at
    for _ in range(max_sessions):
        due_at = (
            _normalize_datetime(next_scheduled_at)
            if next_scheduled_at is not None
            else _normalize_datetime(now_fn())
        )
        current_time = _normalize_datetime(now_fn())
        delay_seconds = (due_at - current_time).total_seconds()
        if delay_seconds > 0:
            sleep_fn(delay_seconds)
        scheduled_times.append(due_at)
        next_scheduled_at = due_at + timedelta(seconds=interval_seconds)
    return scheduled_times


def _refresh_live_state(
    *,
    status: ForwardPaperRuntimeStatus,
    adapter: BinanceSpotLiveMarketDataAdapter,
    now: datetime,
) -> LiveMarketState:
    if (
        status.live_symbol is None
        or status.live_interval is None
        or status.live_lookback_candles is None
        or status.feed_stale_after_seconds is None
    ):
        raise ValueError("Live runtime status is missing required live market fields")
    return adapter.poll_market_state(
        symbol=status.live_symbol,
        interval=status.live_interval,
        lookback_candles=status.live_lookback_candles,
        stale_after_seconds=status.feed_stale_after_seconds,
        now=now,
    )


def _session_summary_with_live_state(
    *,
    session_summary: ForwardPaperSessionSummary,
    session_market_input_path: Path,
    session_market_state_path: Path,
    state: LiveMarketState,
    paths: ForwardPaperRuntimePaths,
) -> ForwardPaperSessionSummary:
    return session_summary.model_copy(
        update={
            "market_input_path": session_market_input_path,
            "market_state_path": session_market_state_path,
            "venue_constraints_path": paths.venue_constraints_path,
            "feed_health": state.feed_health,
        }
    )


def run_forward_paper_runtime(
    replay_path: str | Path | None,
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
    market_source: Literal["replay", "binance_spot"] = "replay",
    live_symbol: str | None = None,
    live_interval: str | None = None,
    live_lookback_candles: int | None = None,
    feed_stale_after_seconds: int | None = None,
    live_adapter: BinanceSpotLiveMarketDataAdapter | None = None,
) -> ForwardPaperRuntimeResult:
    replay_fixture_path = Path(replay_path) if replay_path is not None else None
    scheduled_ticks = (
        [_normalize_datetime(tick) for tick in tick_times] if tick_times is not None else None
    )
    initial_now = scheduled_ticks[0] if scheduled_ticks else _normalize_datetime(now_fn())
    status = _ensure_runtime_status(
        settings=settings,
        market_source=market_source,
        replay_path=replay_fixture_path,
        live_symbol=live_symbol,
        live_interval=live_interval,
        live_lookback_candles=live_lookback_candles,
        feed_stale_after_seconds=feed_stale_after_seconds,
        runtime_id=runtime_id,
        starting_equity_usd=equity_usd,
        session_interval_seconds=session_interval_seconds,
        now=initial_now,
        recover_interrupted=recover_interrupted,
    )
    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    scheduled_times = _iter_scheduled_times(
        tick_times=scheduled_ticks,
        max_sessions=max_sessions,
        initial_next_scheduled_at=status.next_scheduled_at,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
        interval_seconds=session_interval_seconds,
    )

    completed_sessions: list[ForwardPaperSessionSummary] = []
    resolved_live_adapter = (live_adapter if market_source == "binance_spot" else None) or (
        BinanceSpotLiveMarketDataAdapter() if market_source == "binance_spot" else None
    )

    for scheduled_at in scheduled_times:
        status, running_session, session_path = _start_session(
            status=status,
            scheduled_at=scheduled_at,
        )
        run_id = f"{runtime_id}-{running_session.session_id}"
        try:
            if market_source == "replay":
                if replay_fixture_path is None:
                    raise ValueError("Replay runtime requires replay fixture path")
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
            else:
                if resolved_live_adapter is None:
                    raise ValueError("Live market runtime requires a live market adapter")
                market_state = _refresh_live_state(
                    status=status,
                    adapter=resolved_live_adapter,
                    now=scheduled_at,
                )
                _write_live_market_state(paths, market_state)
                session_market_input_path = _session_market_input_path(
                    status.sessions_dir,
                    running_session.session_id,
                )
                session_market_state_path = _session_market_state_path(
                    status.sessions_dir,
                    running_session.session_id,
                )
                _write_live_market_input(session_market_input_path, market_state)
                session_market_state_path.write_text(
                    json.dumps(market_state.model_dump(mode="json"), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                live_session = _session_summary_with_live_state(
                    session_summary=running_session,
                    session_market_input_path=session_market_input_path,
                    session_market_state_path=session_market_state_path,
                    state=market_state,
                    paths=paths,
                )
                status = status.model_copy(
                    update={
                        "feed_health": market_state.feed_health,
                        "venue_constraints_ready": True,
                        "live_market_status_path": paths.live_market_status_path,
                        "venue_constraints_path": paths.venue_constraints_path,
                        "updated_at": scheduled_at,
                    }
                )
                _write_runtime_status(status)
                upsert_forward_paper_registry_entry(status.registry_path, status)

                if market_state.feed_health.status == "healthy":
                    result = run_paper_replay(
                        session_market_input_path,
                        settings=settings,
                        run_id=run_id,
                        equity_usd=equity_usd,
                    )
                    completed_at = _normalize_datetime(now_fn())
                    completed_session = _completed_session_summary(
                        session_summary=live_session,
                        result=result,
                        completed_at=completed_at,
                    )
                else:
                    completed_at = _normalize_datetime(now_fn())
                    outcome = (
                        "skipped_stale_feed"
                        if market_state.feed_health.status == "stale"
                        else "skipped_degraded_feed"
                    )
                    completed_session = _skipped_session_summary(
                        session_summary=live_session,
                        completed_at=completed_at,
                        outcome=outcome,
                        feed_health=market_state.feed_health,
                    )

            _write_session_summary(completed_session, session_path)
            append_forward_paper_history(
                status.history_path,
                ForwardPaperHistoryEvent(
                    event_type="session.completed",
                    runtime_id=runtime_id,
                    session_id=completed_session.session_id,
                    session_number=completed_session.session_number,
                    occurred_at=completed_session.completed_at or scheduled_at,
                    status="completed",
                    run_id=completed_session.run_id,
                    message=completed_session.session_outcome,
                ),
            )
            status = _complete_status(
                status=status,
                session_summary=completed_session,
                completed_at=completed_session.completed_at or scheduled_at,
            )
            completed_sessions.append(completed_session)
        except LiveMarketDataUnavailableError as exc:
            completed_at = _normalize_datetime(now_fn())
            unavailable_health = LiveFeedHealth(
                status="degraded",
                observed_at=completed_at,
                last_success_at=status.feed_health.last_success_at if status.feed_health else None,
                last_candle_close_time=(
                    status.feed_health.last_candle_close_time if status.feed_health else None
                ),
                consecutive_failure_count=(
                    (status.feed_health.consecutive_failure_count if status.feed_health else 0) + 1
                ),
                stale_after_seconds=status.feed_stale_after_seconds or 60,
                message=str(exc),
            )
            skipped_session = _skipped_session_summary(
                session_summary=running_session.model_copy(
                    update={
                        "market_source": market_source,
                        "live_symbol": status.live_symbol,
                        "live_interval": status.live_interval,
                        "venue_constraints_path": status.venue_constraints_path,
                    }
                ),
                completed_at=completed_at,
                outcome="skipped_unavailable_feed",
                feed_health=unavailable_health,
            )
            _write_session_summary(skipped_session, session_path)
            append_forward_paper_history(
                status.history_path,
                ForwardPaperHistoryEvent(
                    event_type="session.completed",
                    runtime_id=runtime_id,
                    session_id=skipped_session.session_id,
                    session_number=skipped_session.session_number,
                    occurred_at=completed_at,
                    status="completed",
                    message=skipped_session.session_outcome,
                ),
            )
            status = status.model_copy(
                update={
                    "feed_health": unavailable_health,
                    "venue_constraints_ready": status.venue_constraints_ready,
                    "updated_at": completed_at,
                }
            )
            _write_runtime_status(status)
            upsert_forward_paper_registry_entry(status.registry_path, status)
            status = _complete_status(
                status=status,
                session_summary=skipped_session,
                completed_at=completed_at,
            )
            completed_sessions.append(skipped_session)
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
        runtime_id=status.runtime_id,
        registry_path=status.registry_path,
        status_path=status.status_path,
        history_path=status.history_path,
        sessions_dir=status.sessions_dir,
        live_market_status_path=status.live_market_status_path,
        venue_constraints_path=status.venue_constraints_path,
        session_count=len(completed_sessions),
        session_summaries=completed_sessions,
    )
