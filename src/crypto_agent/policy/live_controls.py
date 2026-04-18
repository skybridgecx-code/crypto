from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.config import Settings
from crypto_agent.evaluation.models import ReplayPnLSummary
from crypto_agent.execution.models import ExecutionRequestArtifact

if TYPE_CHECKING:
    from crypto_agent.runtime.models import (
        ForwardPaperRuntimeAccountState,
        ForwardPaperSessionSummary,
        LiveTransmissionDecisionArtifact,
    )


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _normalize_symbol(value: str) -> str:
    return value.strip().upper()


def _daily_loss_fraction(account_state: ForwardPaperRuntimeAccountState) -> float:
    if account_state.starting_equity_usd <= 0:
        return 0.0
    return max(0.0, -account_state.net_realized_pnl_usd / account_state.starting_equity_usd)


def _session_loss_fraction(pnl: ReplayPnLSummary | None) -> float | None:
    if pnl is None or pnl.starting_equity_usd <= 0:
        return None
    return max(0.0, (pnl.starting_equity_usd - pnl.ending_equity_usd) / pnl.starting_equity_usd)


def _default_allowed_execution_modes() -> list[Literal["paper", "shadow", "sandbox"]]:
    return ["paper", "shadow", "sandbox"]


class LiveControlConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    updated_at: datetime
    allowed_execution_modes: list[Literal["paper", "shadow", "sandbox"]] = Field(
        default_factory=_default_allowed_execution_modes
    )
    symbol_allowlist: list[str] = Field(default_factory=list)
    per_symbol_max_notional_usd: dict[str, float] = Field(default_factory=dict)
    max_session_loss_fraction: float = Field(default=1.0, ge=0, le=1)
    max_daily_loss_fraction: float = Field(default=1.0, ge=0, le=1)
    max_open_positions: int = Field(default=999, ge=0)
    manual_approval_above_notional_usd: float = Field(default=0.0, ge=0)
    sandbox_venue_suffix: str = "_testnet"

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)

    @field_validator("symbol_allowlist")
    @classmethod
    def normalize_symbol_allowlist(cls, value: list[str]) -> list[str]:
        return [_normalize_symbol(symbol) for symbol in value]

    @field_validator("per_symbol_max_notional_usd")
    @classmethod
    def normalize_symbol_caps(cls, value: dict[str, float]) -> dict[str, float]:
        return {_normalize_symbol(symbol): cap for symbol, cap in value.items()}


class ManualControlState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    updated_at: datetime
    halt_active: bool = False
    halt_reason: str | None = None
    approval_granted: bool = False
    approval_note: str | None = None

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveControlDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    checked_at: datetime
    stage: Literal["preflight", "post_run"]
    execution_mode: Literal["paper", "shadow", "sandbox"]
    action: Literal["go", "no_go", "manual_approval_required"]
    summary: str
    reason_codes: list[str] = Field(default_factory=list)
    requested_symbols: list[str] = Field(default_factory=list)
    request_count: int = Field(default=0, ge=0)
    max_estimated_notional_usd: float | None = Field(default=None, ge=0)
    current_open_position_count: int = Field(default=0, ge=0)
    current_daily_loss_fraction: float = Field(default=0.0, ge=0)
    last_session_loss_fraction: float | None = Field(default=None, ge=0)
    projected_daily_loss_fraction: float | None = Field(default=None, ge=0)

    @field_validator("checked_at")
    @classmethod
    def normalize_checked_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveControlStatusArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    updated_at: datetime
    execution_mode: Literal["paper", "shadow", "sandbox"]
    market_source: Literal["replay", "binance_spot"]
    readiness_status: Literal["ready", "not_ready"]
    limited_live_gate_status: Literal["not_ready", "ready_for_review"]
    allowed_execution_modes: list[Literal["paper", "shadow", "sandbox"]] = Field(
        default_factory=list
    )
    symbol_allowlist: list[str] = Field(default_factory=list)
    per_symbol_max_notional_usd: dict[str, float] = Field(default_factory=dict)
    max_session_loss_fraction: float = Field(ge=0, le=1)
    max_daily_loss_fraction: float = Field(ge=0, le=1)
    max_open_positions: int = Field(ge=0)
    manual_approval_above_notional_usd: float = Field(ge=0)
    manual_halt_active: bool = False
    manual_halt_reason: str | None = None
    approval_granted: bool = False
    current_open_position_count: int = Field(default=0, ge=0)
    current_daily_loss_fraction: float = Field(default=0.0, ge=0)
    last_session_loss_fraction: float | None = Field(default=None, ge=0)
    latest_decision_path: Path | None = None
    go_no_go_action: Literal["go", "no_go", "manual_approval_required"]
    go_no_go_summary: str
    go_no_go_reason_codes: list[str] = Field(default_factory=list)

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


def default_live_control_config(
    *,
    runtime_id: str,
    settings: Settings,
    updated_at: datetime,
) -> LiveControlConfig:
    return LiveControlConfig(
        runtime_id=runtime_id,
        updated_at=updated_at,
        symbol_allowlist=settings.venue.allowed_symbols,
        max_session_loss_fraction=settings.policy.max_drawdown_fraction,
        max_daily_loss_fraction=settings.risk.max_daily_realized_loss,
        max_open_positions=settings.risk.max_open_positions,
    )


def default_manual_control_state(
    *,
    runtime_id: str,
    updated_at: datetime,
) -> ManualControlState:
    return ManualControlState(runtime_id=runtime_id, updated_at=updated_at)


def evaluate_preflight_controls(
    *,
    runtime_id: str,
    session_id: str,
    execution_mode: Literal["paper", "shadow", "sandbox"],
    requested_symbols: list[str],
    account_state: ForwardPaperRuntimeAccountState,
    controls: LiveControlConfig,
    readiness_status: Literal["ready", "not_ready"],
    manual_controls: ManualControlState,
    checked_at: datetime,
    last_completed_session: ForwardPaperSessionSummary | None,
) -> LiveControlDecision:
    normalized_symbols = sorted({_normalize_symbol(symbol) for symbol in requested_symbols})
    reasons: list[str] = []
    current_daily_loss_fraction = _daily_loss_fraction(account_state)
    last_session_loss_fraction = _session_loss_fraction(
        last_completed_session.pnl if last_completed_session is not None else None
    )

    if readiness_status != "ready":
        reasons.append("operator_not_ready")
    if manual_controls.halt_active:
        reasons.append("manual_halt_active")
    if execution_mode not in controls.allowed_execution_modes:
        reasons.append("execution_mode_not_allowed")
    if normalized_symbols:
        disallowed_symbols = [
            symbol for symbol in normalized_symbols if symbol not in controls.symbol_allowlist
        ]
        if disallowed_symbols:
            reasons.extend(f"symbol_not_allowed:{symbol}" for symbol in disallowed_symbols)
    if len(account_state.positions) > controls.max_open_positions:
        reasons.append("max_open_positions_exceeded")
    if current_daily_loss_fraction > controls.max_daily_loss_fraction:
        reasons.append("max_daily_loss_exceeded")
    if (
        last_session_loss_fraction is not None
        and last_session_loss_fraction > controls.max_session_loss_fraction
    ):
        reasons.append("max_session_loss_exceeded")

    action: Literal["go", "no_go", "manual_approval_required"] = "go" if not reasons else "no_go"
    summary = (
        "Live controls passed for this session."
        if action == "go"
        else "Live controls blocked this session before runtime execution."
    )
    return LiveControlDecision(
        runtime_id=runtime_id,
        session_id=session_id,
        checked_at=checked_at,
        stage="preflight",
        execution_mode=execution_mode,
        action=action,
        summary=summary,
        reason_codes=reasons,
        requested_symbols=normalized_symbols,
        current_open_position_count=len(account_state.positions),
        current_daily_loss_fraction=current_daily_loss_fraction,
        last_session_loss_fraction=last_session_loss_fraction,
    )


def evaluate_post_run_controls(
    *,
    runtime_id: str,
    session_id: str,
    execution_mode: Literal["paper", "shadow", "sandbox"],
    request_artifact: ExecutionRequestArtifact | None,
    session_pnl: ReplayPnLSummary | None,
    account_state: ForwardPaperRuntimeAccountState,
    controls: LiveControlConfig,
    manual_controls: ManualControlState,
    checked_at: datetime,
) -> LiveControlDecision:
    reasons: list[str] = []
    requests = [] if request_artifact is None else request_artifact.requests
    requested_symbols = sorted({_normalize_symbol(request.symbol) for request in requests})
    max_estimated_notional_usd = (
        max((request.estimated_notional_usd for request in requests), default=0.0)
        if requests
        else None
    )
    session_loss_fraction = _session_loss_fraction(session_pnl)
    projected_daily_loss_fraction = max(
        0.0,
        -(
            account_state.net_realized_pnl_usd
            + (session_pnl.net_realized_pnl_usd if session_pnl is not None else 0.0)
        )
        / account_state.starting_equity_usd,
    )

    if request_artifact is not None:
        disallowed_symbols = [
            symbol for symbol in requested_symbols if symbol not in controls.symbol_allowlist
        ]
        if disallowed_symbols:
            reasons.extend(f"symbol_not_allowed:{symbol}" for symbol in disallowed_symbols)

        for request in requests:
            symbol_cap = controls.per_symbol_max_notional_usd.get(_normalize_symbol(request.symbol))
            if symbol_cap is not None and request.estimated_notional_usd > symbol_cap:
                reasons.append(
                    f"per_symbol_max_notional_exceeded:{_normalize_symbol(request.symbol)}"
                )
            if execution_mode == "sandbox" and not request.venue.endswith(
                controls.sandbox_venue_suffix
            ):
                reasons.append("sandbox_venue_not_testnet")

        if (
            controls.manual_approval_above_notional_usd > 0
            and max_estimated_notional_usd is not None
            and max_estimated_notional_usd > controls.manual_approval_above_notional_usd
            and not manual_controls.approval_granted
        ):
            reasons.append("manual_approval_required")

    if (
        session_loss_fraction is not None
        and session_loss_fraction > controls.max_session_loss_fraction
    ):
        reasons.append("max_session_loss_exceeded")
    if projected_daily_loss_fraction > controls.max_daily_loss_fraction:
        reasons.append("max_daily_loss_exceeded")

    action: Literal["go", "no_go", "manual_approval_required"] = "go"
    if "manual_approval_required" in reasons:
        action = "manual_approval_required"
    elif reasons:
        action = "no_go"

    summary = (
        "Live controls passed for post-run execution review."
        if action == "go"
        else "Manual approval is required before non-paper execution evidence can proceed."
        if action == "manual_approval_required"
        else "Live controls blocked post-run non-paper execution evidence."
    )
    return LiveControlDecision(
        runtime_id=runtime_id,
        session_id=session_id,
        checked_at=checked_at,
        stage="post_run",
        execution_mode=execution_mode,
        action=action,
        summary=summary,
        reason_codes=reasons,
        requested_symbols=requested_symbols,
        request_count=0 if request_artifact is None else request_artifact.request_count,
        max_estimated_notional_usd=max_estimated_notional_usd,
        current_open_position_count=len(account_state.positions),
        current_daily_loss_fraction=_daily_loss_fraction(account_state),
        last_session_loss_fraction=session_loss_fraction,
        projected_daily_loss_fraction=projected_daily_loss_fraction,
    )


def build_live_control_status_artifact(
    *,
    runtime_id: str,
    execution_mode: Literal["paper", "shadow", "sandbox"],
    market_source: Literal["replay", "binance_spot"],
    controls: LiveControlConfig,
    manual_controls: ManualControlState,
    readiness_status: Literal["ready", "not_ready"],
    limited_live_gate_status: Literal["not_ready", "ready_for_review"],
    account_state: ForwardPaperRuntimeAccountState,
    last_completed_session: ForwardPaperSessionSummary | None,
    latest_decision_path: Path | None,
    latest_decision: LiveControlDecision,
    updated_at: datetime,
) -> LiveControlStatusArtifact:
    return LiveControlStatusArtifact(
        runtime_id=runtime_id,
        updated_at=updated_at,
        execution_mode=execution_mode,
        market_source=market_source,
        readiness_status=readiness_status,
        limited_live_gate_status=limited_live_gate_status,
        allowed_execution_modes=controls.allowed_execution_modes,
        symbol_allowlist=controls.symbol_allowlist,
        per_symbol_max_notional_usd=controls.per_symbol_max_notional_usd,
        max_session_loss_fraction=controls.max_session_loss_fraction,
        max_daily_loss_fraction=controls.max_daily_loss_fraction,
        max_open_positions=controls.max_open_positions,
        manual_approval_above_notional_usd=controls.manual_approval_above_notional_usd,
        manual_halt_active=manual_controls.halt_active,
        manual_halt_reason=manual_controls.halt_reason,
        approval_granted=manual_controls.approval_granted,
        current_open_position_count=len(account_state.positions),
        current_daily_loss_fraction=_daily_loss_fraction(account_state),
        last_session_loss_fraction=_session_loss_fraction(
            last_completed_session.pnl if last_completed_session is not None else None
        ),
        latest_decision_path=latest_decision_path,
        go_no_go_action=latest_decision.action,
        go_no_go_summary=latest_decision.summary,
        go_no_go_reason_codes=latest_decision.reason_codes,
    )


def build_limited_live_transmission_decision_artifact(
    *,
    runtime_id: str,
    authority_state_path: Path,
    launch_window_path: Path,
    approval_state_path: Path,
    readiness_status: Literal["ready", "not_ready"],
    limited_live_gate_status: Literal["not_ready", "ready_for_review"],
    manual_controls: ManualControlState,
    reconciliation_status: Literal["not_checked", "clean", "mismatch"],
    latest_decision: LiveControlDecision,
    generated_at: datetime,
) -> LiveTransmissionDecisionArtifact:
    from crypto_agent.runtime.models import (
        LiveApprovalStateArtifact,
        LiveAuthorityStateArtifact,
        LiveLaunchWindowArtifact,
        LiveTransmissionDecisionArtifact,
    )

    authority_state = LiveAuthorityStateArtifact.model_validate(
        json.loads(authority_state_path.read_text(encoding="utf-8"))
    )
    launch_window = LiveLaunchWindowArtifact.model_validate(
        json.loads(launch_window_path.read_text(encoding="utf-8"))
    )
    approval_state = LiveApprovalStateArtifact.model_validate(
        json.loads(approval_state_path.read_text(encoding="utf-8"))
    )

    reasons: list[str] = []
    if not authority_state.authority_enabled:
        reasons.extend(
            authority_state.reason_codes
            if authority_state.reason_codes
            else ["live_authority_disabled"]
        )
    if launch_window.state != "active":
        reasons.extend(
            launch_window.reason_codes
            if launch_window.reason_codes
            else ["launch_window_not_active"]
        )
    if approval_state.required_for_live_transmission and approval_state.active_approval_count < 1:
        reasons.extend(
            approval_state.reason_codes
            if approval_state.reason_codes
            else ["no_active_live_approval"]
        )
    if readiness_status != "ready":
        reasons.append("operator_not_ready")
    if limited_live_gate_status != "ready_for_review":
        reasons.append("limited_live_gate_not_ready_for_review")
    if manual_controls.halt_active:
        reasons.append("manual_halt_active")
    if reconciliation_status != "clean":
        reasons.append("reconciliation_not_clean")
    if latest_decision.action != "go":
        reasons.append(f"live_control_not_go:{latest_decision.action}")
    reasons.append("limited_live_transmission_not_implemented")

    deduped_reasons: list[str] = []
    for reason in reasons:
        if reason not in deduped_reasons:
            deduped_reasons.append(reason)

    return LiveTransmissionDecisionArtifact(
        runtime_id=runtime_id,
        generated_at=generated_at,
        reason_codes=deduped_reasons,
        authority_state_path=authority_state_path,
        launch_window_path=launch_window_path,
        approval_state_path=approval_state_path,
    )
