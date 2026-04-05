from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.enums import Mode
from crypto_agent.evaluation.models import EvaluationScorecard, ReplayPnLSummary
from crypto_agent.market_data.live_models import LiveFeedHealth


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class ForwardPaperRuntimePaths(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_dir: Path
    status_path: Path
    history_path: Path
    sessions_dir: Path
    registry_path: Path
    live_market_status_path: Path
    venue_constraints_path: Path


class ForwardPaperSessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    session_number: int = Field(ge=1)
    mode: Mode = Mode.PAPER
    market_source: Literal["replay", "binance_spot"] = "replay"
    live_symbol: str | None = None
    live_interval: str | None = None
    status: Literal["running", "completed", "interrupted", "failed"]
    replay_path: Path | None = None
    market_input_path: Path | None = None
    market_state_path: Path | None = None
    venue_constraints_path: Path | None = None
    feed_health: LiveFeedHealth | None = None
    session_outcome: (
        Literal[
            "executed",
            "skipped_stale_feed",
            "skipped_degraded_feed",
            "skipped_unavailable_feed",
        ]
        | None
    ) = None
    scheduled_at: datetime
    started_at: datetime
    completed_at: datetime | None = None
    run_id: str | None = None
    journal_path: Path | None = None
    summary_path: Path | None = None
    report_path: Path | None = None
    trade_ledger_path: Path | None = None
    quality_issue_count: int | None = Field(default=None, ge=0)
    scorecard: EvaluationScorecard | None = None
    pnl: ReplayPnLSummary | None = None
    review_packet: dict[str, Any] | None = None
    operator_summary: dict[str, Any] | None = None
    artifact_paths_exist: dict[str, bool] = Field(default_factory=dict)
    all_artifact_paths_exist: bool = True
    recovery_note: str | None = None
    error_message: str | None = None

    @field_validator("scheduled_at", "started_at", "completed_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_datetime(value)


class ForwardPaperRuntimeStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    mode: Mode = Mode.PAPER
    market_source: Literal["replay", "binance_spot"] = "replay"
    replay_path: Path | None = None
    live_symbol: str | None = None
    live_interval: str | None = None
    live_lookback_candles: int | None = Field(default=None, ge=2)
    feed_stale_after_seconds: int | None = Field(default=None, gt=0)
    starting_equity_usd: float = Field(gt=0)
    session_interval_seconds: int = Field(gt=0)
    status: Literal["idle", "running"] = "idle"
    next_session_number: int = Field(default=1, ge=1)
    active_session_id: str | None = None
    active_session_started_at: datetime | None = None
    last_session_id: str | None = None
    completed_session_count: int = Field(default=0, ge=0)
    interrupted_session_count: int = Field(default=0, ge=0)
    failed_session_count: int = Field(default=0, ge=0)
    next_scheduled_at: datetime | None = None
    last_error_message: str | None = None
    feed_health: LiveFeedHealth | None = None
    venue_constraints_ready: bool = False
    updated_at: datetime
    status_path: Path
    history_path: Path
    sessions_dir: Path
    registry_path: Path
    live_market_status_path: Path | None = None
    venue_constraints_path: Path | None = None

    @field_validator("active_session_started_at", "next_scheduled_at", "updated_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_datetime(value)


class ForwardPaperRuntimeRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    mode: Mode = Mode.PAPER
    market_source: Literal["replay", "binance_spot"] = "replay"
    replay_path: Path | None = None
    live_symbol: str | None = None
    live_interval: str | None = None
    runtime_dir: Path
    status_path: Path
    history_path: Path
    sessions_dir: Path
    live_market_status_path: Path | None = None
    venue_constraints_path: Path | None = None
    starting_equity_usd: float = Field(gt=0)
    session_interval_seconds: int = Field(gt=0)
    status: Literal["idle", "running"]
    next_session_number: int = Field(ge=1)
    active_session_id: str | None = None
    last_session_id: str | None = None
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class ForwardPaperRuntimeRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    registry_path: Path
    runtime_count: int = Field(ge=0)
    runtimes: list[ForwardPaperRuntimeRegistryEntry] = Field(default_factory=list)


class ForwardPaperHistoryEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal[
        "session.started",
        "session.completed",
        "session.interrupted",
        "session.failed",
    ]
    runtime_id: str
    session_id: str
    session_number: int = Field(ge=1)
    occurred_at: datetime
    status: Literal["running", "completed", "interrupted", "failed"]
    run_id: str | None = None
    message: str | None = None

    @field_validator("occurred_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class ForwardPaperRuntimeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    registry_path: Path
    status_path: Path
    history_path: Path
    sessions_dir: Path
    live_market_status_path: Path | None = None
    venue_constraints_path: Path | None = None
    session_count: int = Field(ge=0)
    session_summaries: list[ForwardPaperSessionSummary] = Field(default_factory=list)
