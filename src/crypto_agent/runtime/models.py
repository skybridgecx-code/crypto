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
    shadow_canary_evaluation_path: Path
    soak_evaluation_path: Path
    shadow_evaluation_path: Path
    live_market_preflight_path: Path
    live_gate_decision_path: Path
    live_gate_threshold_summary_path: Path
    live_gate_report_path: Path
    live_launch_verdict_path: Path
    live_authority_state_path: Path
    live_launch_window_path: Path
    live_transmission_decision_path: Path
    live_transmission_result_path: Path
    live_approval_state_path: Path


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


class ForwardPaperSessionSkipEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    session_outcome: Literal["skipped_unavailable_feed"]
    feed_health_status: str
    feed_health_message: str | None
    configured_base_url: str
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
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
    live_transmission_request_path: Path | None = None
    live_transmission_result_path: Path | None = None
    live_transmission_state_path: Path | None = None
    live_transmission_request_decision_path: Path | None = None
    live_transmission_request_result_path: Path | None = None
    skip_evidence_path: Path | None = None
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


class ForwardPaperSoakSessionRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    session_number: int = Field(ge=1)
    status: Literal["running", "completed", "interrupted", "failed"]
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
    execution_mode: Literal["paper", "shadow", "sandbox"] = "paper"
    run_id: str | None = None
    return_fraction: float | None = None
    ending_equity_usd: float | None = None
    control_action: Literal["go", "no_go", "manual_approval_required"] | None = None
    control_reason_codes: list[str] = Field(default_factory=list)


class ForwardPaperSoakEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    session_count: int = Field(ge=0)
    completed_session_count: int = Field(default=0, ge=0)
    executed_session_count: int = Field(default=0, ge=0)
    blocked_session_count: int = Field(default=0, ge=0)
    skipped_session_count: int = Field(default=0, ge=0)
    failed_session_count: int = Field(default=0, ge=0)
    interrupted_session_count: int = Field(default=0, ge=0)
    cumulative_net_realized_pnl_usd: float = 0.0
    latest_ending_equity_usd: float | None = None
    average_return_fraction: float = 0.0
    worst_session_return_fraction: float | None = None
    best_session_return_fraction: float | None = None
    rows: list[ForwardPaperSoakSessionRow] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class ForwardPaperShadowEvaluationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    session_number: int = Field(ge=1)
    run_id: str | None = None
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
    control_action: Literal["go", "no_go", "manual_approval_required"] | None = None
    request_count: int = Field(default=0, ge=0)
    rejected_request_count: int = Field(default=0, ge=0)
    would_send_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    status_count: int = Field(default=0, ge=0)
    terminal_status_count: int = Field(default=0, ge=0)
    filled_status_count: int = Field(default=0, ge=0)
    canceled_status_count: int = Field(default=0, ge=0)
    skip_evidence_present: bool = False
    all_artifacts_present: bool = True


class ForwardPaperShadowEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    shadow_session_count: int = Field(default=0, ge=0)
    shadow_executed_session_count: int = Field(default=0, ge=0)
    request_count: int = Field(default=0, ge=0)
    rejected_request_count: int = Field(default=0, ge=0)
    would_send_count: int = Field(default=0, ge=0)
    duplicate_count: int = Field(default=0, ge=0)
    accepted_count: int = Field(default=0, ge=0)
    rejected_count: int = Field(default=0, ge=0)
    status_count: int = Field(default=0, ge=0)
    terminal_status_count: int = Field(default=0, ge=0)
    filled_status_count: int = Field(default=0, ge=0)
    canceled_status_count: int = Field(default=0, ge=0)
    missing_request_artifact_count: int = Field(default=0, ge=0)
    missing_result_artifact_count: int = Field(default=0, ge=0)
    missing_status_artifact_count: int = Field(default=0, ge=0)
    shadow_unavailable_feed_session_count: int = Field(default=0, ge=0)
    skip_evidence_count: int = Field(default=0, ge=0)
    missing_skip_evidence_count: int = Field(default=0, ge=0)
    all_shadow_artifacts_present: bool = True
    rows: list[ForwardPaperShadowEvaluationRow] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class ForwardPaperShadowCanaryRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    session_number: int = Field(ge=1)
    run_id: str | None = None
    status: Literal["running", "completed", "interrupted", "failed"]
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
    request_artifact_present: bool = False
    result_artifact_present: bool = False
    status_artifact_present: bool = False
    skip_evidence_present: bool = False
    all_expected_evidence_present: bool = True


class ForwardPaperShadowCanaryEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    execution_mode: Literal["paper", "shadow", "sandbox"]
    market_source: Literal["replay", "binance_spot"]
    applicable: bool
    state: Literal["pass", "fail", "not_applicable"]
    summary: str
    reason_codes: list[str] = Field(default_factory=list)
    session_count: int = Field(default=0, ge=0)
    completed_session_count: int = Field(default=0, ge=0)
    executed_session_count: int = Field(default=0, ge=0)
    blocked_session_count: int = Field(default=0, ge=0)
    skipped_stale_feed_session_count: int = Field(default=0, ge=0)
    skipped_degraded_feed_session_count: int = Field(default=0, ge=0)
    skipped_unavailable_feed_session_count: int = Field(default=0, ge=0)
    failed_session_count: int = Field(default=0, ge=0)
    interrupted_session_count: int = Field(default=0, ge=0)
    request_artifact_count: int = Field(default=0, ge=0)
    result_artifact_count: int = Field(default=0, ge=0)
    status_artifact_count: int = Field(default=0, ge=0)
    skip_evidence_count: int = Field(default=0, ge=0)
    all_expected_evidence_present: bool = True
    rows: list[ForwardPaperShadowCanaryRow] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveGateThresholdCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    category: Literal["blocking", "readiness"]
    description: str
    passed: bool
    actual: str
    expected: str
    reason_code: str | None = None


class LiveGateThresholdSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    blocking_passed: bool
    readiness_passed: bool
    checks: list[LiveGateThresholdCheck] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveGateDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    state: Literal["ready", "not_ready", "blocked"]
    summary: str
    reason_codes: list[str] = Field(default_factory=list)
    soak_evaluation_path: Path
    shadow_evaluation_path: Path
    threshold_summary_path: Path

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveLaunchVerdictChecks(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preflight_batch_ready: bool
    shadow_canary_passed: bool
    blocking_thresholds_passed: bool
    readiness_thresholds_passed: bool
    live_gate_ready: bool
    operator_readiness_ready: bool
    limited_live_gate_ready_for_review: bool


class LiveLaunchVerdictInputArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: Literal[
        "live_market_preflight",
        "shadow_canary_evaluation",
        "live_gate_threshold_summary",
        "live_gate_decision",
        "live_readiness_status",
        "live_control_status",
    ]
    path: Path
    present: bool
    status: str | None = None
    state: str | None = None
    reason_codes: list[str] = Field(default_factory=list)


class LiveLaunchVerdictArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    artifact_only: bool = True
    execution_authority: Literal["none"] = "none"
    verdict: Literal["launchable_here_now", "not_launchable_here_now"]
    summary: str
    reason_codes: list[str] = Field(default_factory=list)
    checks: LiveLaunchVerdictChecks
    input_artifacts: list[LiveLaunchVerdictInputArtifact] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveAuthorityStateArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    authority_enabled: bool = False
    execution_authority: Literal["none", "limited_live"] = "none"
    scope: Literal["disabled", "tiny_limited_live"] = "disabled"
    summary: str
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveLaunchWindowArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    state: Literal["not_configured", "scheduled", "active", "expired"] = "not_configured"
    configured: bool = False
    starts_at: datetime | None = None
    ends_at: datetime | None = None
    summary: str
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("generated_at", "starts_at", "ends_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_datetime(value)


class LiveTransmissionDecisionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    decision: Literal["authorized", "denied"] = "denied"
    transmission_authorized: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    authority_state_path: Path
    launch_window_path: Path
    approval_state_path: Path

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveTransmissionRuntimeResultArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    transmission_attempted: bool = False
    adapter_submission_attempted: bool = False
    transmission_eligible: bool = False
    eligibility_state: Literal["eligible", "ineligible"] = "ineligible"
    rehearsal_gate_required: bool = True
    rehearsal_gate_state: Literal["inactive", "active"] = "inactive"
    rehearsal_gate_scope_state: Literal["absent", "mismatched", "matched"] = "absent"
    rehearsal_gate_match: bool = False
    rehearsal_gate_reason_codes: list[str] = Field(default_factory=list)
    rehearsal_gate_passed: bool = False
    final_state: Literal[
        "not_attempted",
        "not_submitted_terminal_blocked",
        "accepted",
        "open",
        "partially_filled",
        "filled",
        "canceled",
        "rejected",
        "error_terminal_blocked",
    ] = "not_attempted"
    summary: str
    reason_codes: list[str] = Field(default_factory=list)
    per_request_request_id: str | None = None
    per_request_decision_path: Path | None = None
    per_request_result_path: Path | None = None
    transmission_decision_path: Path

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveTransmissionPerRequestDecisionArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    run_id: str
    generated_at: datetime
    request_id: str
    client_order_id: str
    intent_id: str
    symbol: str
    side: str
    bounded_decision: Literal["allowed", "denied"] = "denied"
    bounded_seam_allowed: bool = False
    reason_codes: list[str] = Field(default_factory=list)
    rehearsal_gate_reason_codes: list[str] = Field(default_factory=list)
    adapter_call_attempted: bool = False
    submission_status: Literal["not_submitted", "submitted", "rejected", "error"] = "not_submitted"
    live_transmission_result_path: Path
    live_transmission_state_path: Path

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveTransmissionPerRequestResultArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    run_id: str
    generated_at: datetime
    request_id: str
    client_order_id: str
    intent_id: str
    symbol: str
    side: str
    bounded_result_state: Literal[
        "not_submitted_terminal_blocked",
        "accepted",
        "open",
        "partially_filled",
        "filled",
        "canceled",
        "rejected",
        "error_terminal_blocked",
    ]
    adapter_call_attempted: bool = False
    submission_status: Literal["not_submitted", "submitted", "rejected", "error"] = "not_submitted"
    ack_status: Literal["accepted", "rejected", "duplicate"] | None = None
    order_state: (
        Literal["accepted", "open", "partially_filled", "filled", "canceled", "rejected"] | None
    ) = None
    reason_codes: list[str] = Field(default_factory=list)
    rehearsal_gate_reason_codes: list[str] = Field(default_factory=list)
    per_request_decision_path: Path
    live_transmission_result_path: Path
    live_transmission_state_path: Path
    runtime_live_transmission_result_path: Path | None = None

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveRehearsalGateScope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    request_id: str


class LiveApprovalRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    request_id: str
    symbol: str
    side: Literal["buy", "sell"]
    estimated_notional_usd: float = Field(ge=0)
    state: Literal["pending", "approved", "expired", "rejected"] = "pending"
    generated_at: datetime
    approved_at: datetime | None = None
    approval_note: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("generated_at", "approved_at")
    @classmethod
    def normalize_timestamps(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _normalize_datetime(value)


class LiveApprovalStateArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    generated_at: datetime
    required_for_live_transmission: bool = True
    active_approval_count: int = Field(default=0, ge=0)
    approvals: list[LiveApprovalRecord] = Field(default_factory=list)
    summary: str
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveMarketPreflightArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    market_source: Literal["binance_spot"]
    symbol: str
    interval: str
    configured_base_url: str
    retry_count: int = Field(ge=0)
    retry_delay_seconds: float = Field(ge=0)
    attempt_count_used: int = Field(ge=1)
    observed_at: datetime
    status: Literal[
        "batch_ready",
        "recovered_after_retry",
        "single_probe_ready",
        "stale",
        "unavailable",
        "retries_exhausted",
    ]
    success: bool
    single_probe_success: bool
    batch_readiness: bool
    batch_readiness_reason: str
    feed_health_status: Literal["healthy", "stale", "degraded"] | None = None
    feed_health_message: str | None = None
    required_closed_candle_count: int = Field(default=0, ge=0)
    candle_count: int = Field(default=0, ge=0)
    stability_window_probe_count: int = Field(default=0, ge=0)
    stability_window_success_count: int = Field(default=0, ge=0)
    stability_window_result: Literal["passed", "failed", "not_run"]
    stability_failure_status: Literal["stale", "unavailable", "retries_exhausted"] | None = None
    stability_probe_attempt_count_used: int | None = Field(default=None, ge=1)
    stability_feed_health_status: Literal["healthy", "stale", "degraded"] | None = None
    stability_feed_health_message: str | None = None
    order_book_present: bool = False
    constraints_present: bool = False

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
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
    binance_base_url: str | None = None
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
    shadow_canary_evaluation_path: Path
    soak_evaluation_path: Path
    shadow_evaluation_path: Path
    live_gate_decision_path: Path
    live_gate_threshold_summary_path: Path
    live_gate_report_path: Path
    live_launch_verdict_path: Path
    live_authority_state_path: Path | None = None
    live_launch_window_path: Path | None = None
    live_transmission_decision_path: Path | None = None
    live_transmission_result_path: Path | None = None
    live_approval_state_path: Path | None = None
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
    shadow_canary_evaluation_path: Path
    soak_evaluation_path: Path
    shadow_evaluation_path: Path
    live_gate_decision_path: Path
    live_gate_threshold_summary_path: Path
    live_gate_report_path: Path
    live_launch_verdict_path: Path
    live_authority_state_path: Path | None = None
    live_launch_window_path: Path | None = None
    live_transmission_decision_path: Path | None = None
    live_transmission_result_path: Path | None = None
    live_approval_state_path: Path | None = None
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
    shadow_canary_evaluation_path: Path
    live_market_preflight_path: Path
    soak_evaluation_path: Path
    shadow_evaluation_path: Path
    live_gate_decision_path: Path
    live_gate_threshold_summary_path: Path
    live_gate_report_path: Path
    live_launch_verdict_path: Path
    live_authority_state_path: Path | None = None
    live_launch_window_path: Path | None = None
    live_transmission_decision_path: Path | None = None
    live_transmission_result_path: Path | None = None
    live_approval_state_path: Path | None = None
    session_count: int = Field(ge=0)
    session_summaries: list[ForwardPaperSessionSummary] = Field(default_factory=list)


class LiveMarketPreflightResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    artifact_path: Path
    artifact: LiveMarketPreflightArtifact
