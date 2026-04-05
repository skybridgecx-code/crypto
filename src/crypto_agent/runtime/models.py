from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.enums import Mode
from crypto_agent.evaluation.models import EvaluationScorecard, ReplayPnLSummary
from crypto_agent.market_data.live_models import LiveFeedHealth
from crypto_agent.portfolio.positions import PortfolioState, Position


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
    account_state_path: Path
    reconciliation_report_path: Path
    recovery_status_path: Path
    execution_state_dir: Path
    live_control_config_path: Path
    live_control_status_path: Path
    readiness_status_path: Path
    manual_control_state_path: Path


class RuntimeAccountPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    quantity: float
    entry_price: float = Field(gt=0)
    mark_price: float = Field(gt=0)
    market_value_usd: float
    unrealized_pnl_usd: float

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()


class ForwardPaperRuntimeAccountState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    as_of_session_id: str | None = None
    as_of_run_id: str | None = None
    updated_at: datetime
    starting_equity_usd: float = Field(gt=0)
    cash_balance_usd: float
    gross_position_notional_usd: float = Field(default=0.0, ge=0)
    gross_realized_pnl_usd: float = 0.0
    total_fee_usd: float = Field(default=0.0, ge=0)
    net_realized_pnl_usd: float = 0.0
    ending_unrealized_pnl_usd: float = 0.0
    ending_equity_usd: float = Field(gt=0)
    return_fraction: float = 0.0
    open_intent_ids: list[str] = Field(default_factory=list)
    positions: list[RuntimeAccountPosition] = Field(default_factory=list)

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)

    def to_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            equity_usd=self.ending_equity_usd,
            available_cash_usd=self.cash_balance_usd,
            daily_realized_pnl_usd=self.net_realized_pnl_usd,
            positions=[
                Position(
                    symbol=position.symbol,
                    quantity=position.quantity,
                    entry_price=position.entry_price,
                    mark_price=position.mark_price,
                )
                for position in self.positions
            ],
        )


class ForwardPaperReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    reconciled_at: datetime
    status: Literal["clean", "mismatch"]
    message: str | None = None
    checked_session_count: int = Field(default=0, ge=0)
    executed_session_count: int = Field(default=0, ge=0)
    last_completed_session_id: str | None = None
    last_completed_run_id: str | None = None
    local_account_state_present: bool = False
    expected_account_state: ForwardPaperRuntimeAccountState
    local_account_state: ForwardPaperRuntimeAccountState | None = None
    differences: list[str] = Field(default_factory=list)

    @field_validator("reconciled_at")
    @classmethod
    def normalize_reconciled_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class ForwardPaperRecoveryStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    checked_at: datetime
    status: Literal["clean", "recovered", "blocked_mismatch"]
    reconciliation_status: Literal["clean", "mismatch"]
    recovered_session_id: str | None = None
    recovery_note: str | None = None
    account_state_path: Path
    reconciliation_report_path: Path

    @field_validator("checked_at")
    @classmethod
    def normalize_checked_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class ForwardPaperSessionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    session_number: int = Field(ge=1)
    mode: Mode = Mode.PAPER
    execution_mode: Literal["paper", "shadow", "sandbox"] = "paper"
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
            "blocked_controls",
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
    execution_request_path: Path | None = None
    execution_result_path: Path | None = None
    execution_status_path: Path | None = None
    control_decision_path: Path | None = None
    control_action: Literal["go", "no_go", "manual_approval_required"] | None = None
    control_reason_codes: list[str] = Field(default_factory=list)
    execution_request_count: int | None = Field(default=None, ge=0)
    execution_terminal_count: int | None = Field(default=None, ge=0)
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
    execution_mode: Literal["paper", "shadow", "sandbox"] = "paper"
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
    reconciliation_status: Literal["not_checked", "clean", "mismatch"] = "not_checked"
    mismatch_detected: bool = False
    last_reconciled_session_id: str | None = None
    last_reconciliation_at: datetime | None = None
    updated_at: datetime
    status_path: Path
    history_path: Path
    sessions_dir: Path
    registry_path: Path
    live_market_status_path: Path | None = None
    venue_constraints_path: Path | None = None
    account_state_path: Path
    reconciliation_report_path: Path
    recovery_status_path: Path
    execution_state_dir: Path
    live_control_config_path: Path
    live_control_status_path: Path
    readiness_status_path: Path
    manual_control_state_path: Path
    control_status: Literal["go", "no_go", "manual_approval_required"] = "go"
    control_block_reasons: list[str] = Field(default_factory=list)

    @field_validator(
        "active_session_started_at",
        "next_scheduled_at",
        "last_reconciliation_at",
        "updated_at",
    )
    @classmethod
    def normalize_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_datetime(value)


class ForwardPaperRuntimeRegistryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    mode: Mode = Mode.PAPER
    execution_mode: Literal["paper", "shadow", "sandbox"] = "paper"
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
    account_state_path: Path
    reconciliation_report_path: Path
    recovery_status_path: Path
    execution_state_dir: Path
    live_control_config_path: Path
    live_control_status_path: Path
    readiness_status_path: Path
    manual_control_state_path: Path
    starting_equity_usd: float = Field(gt=0)
    session_interval_seconds: int = Field(gt=0)
    status: Literal["idle", "running"]
    next_session_number: int = Field(ge=1)
    active_session_id: str | None = None
    last_session_id: str | None = None
    reconciliation_status: Literal["not_checked", "clean", "mismatch"] = "not_checked"
    mismatch_detected: bool = False
    control_status: Literal["go", "no_go", "manual_approval_required"] = "go"
    control_block_reasons: list[str] = Field(default_factory=list)
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
    account_state_path: Path
    reconciliation_report_path: Path
    recovery_status_path: Path
    execution_mode: Literal["paper", "shadow", "sandbox"] = "paper"
    execution_state_dir: Path
    live_control_config_path: Path
    live_control_status_path: Path
    readiness_status_path: Path
    manual_control_state_path: Path
    session_count: int = Field(ge=0)
    session_summaries: list[ForwardPaperSessionSummary] = Field(default_factory=list)
