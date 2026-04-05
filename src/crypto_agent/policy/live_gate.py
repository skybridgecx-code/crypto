from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.policy.live_controls import LiveControlStatusArtifact, ManualControlState
from crypto_agent.policy.readiness import LiveReadinessStatus
from crypto_agent.runtime.models import (
    ForwardPaperReconciliationReport,
    ForwardPaperShadowEvaluation,
    ForwardPaperSoakEvaluation,
    LiveGateDecision,
    LiveGateThresholdCheck,
    LiveGateThresholdSummary,
)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class LiveGateConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    updated_at: datetime
    min_completed_sessions: int = Field(default=3, ge=0)
    min_executed_sessions: int = Field(default=2, ge=0)
    min_shadow_sessions: int = Field(default=1, ge=0)
    min_shadow_request_count: int = Field(default=1, ge=0)
    max_failed_sessions: int = Field(default=0, ge=0)
    max_interrupted_sessions: int = Field(default=0, ge=0)

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


def default_live_gate_config(*, runtime_id: str, updated_at: datetime) -> LiveGateConfig:
    return LiveGateConfig(runtime_id=runtime_id, updated_at=updated_at)


def build_live_gate_threshold_summary(
    *,
    runtime_id: str,
    generated_at: datetime,
    config: LiveGateConfig,
    soak: ForwardPaperSoakEvaluation,
    shadow: ForwardPaperShadowEvaluation,
    reconciliation: ForwardPaperReconciliationReport,
    control_status: LiveControlStatusArtifact,
    readiness: LiveReadinessStatus,
    manual_controls: ManualControlState,
) -> LiveGateThresholdSummary:
    checks = [
        LiveGateThresholdCheck(
            check_id="reconciliation_clean",
            category="blocking",
            description="Runtime reconciliation must be clean.",
            passed=reconciliation.status == "clean",
            actual=reconciliation.status,
            expected="clean",
            reason_code="reconciliation_mismatch",
        ),
        LiveGateThresholdCheck(
            check_id="operator_ready",
            category="blocking",
            description="Operator readiness must be ready.",
            passed=readiness.status == "ready",
            actual=readiness.status,
            expected="ready",
            reason_code="operator_not_ready_status",
        ),
        LiveGateThresholdCheck(
            check_id="manual_halt_inactive",
            category="blocking",
            description="Manual halt must be inactive.",
            passed=manual_controls.halt_active is False,
            actual="active" if manual_controls.halt_active else "inactive",
            expected="inactive",
            reason_code="manual_halt_active",
        ),
        LiveGateThresholdCheck(
            check_id="current_controls_go",
            category="blocking",
            description="Current live controls must be go.",
            passed=control_status.go_no_go_action == "go",
            actual=control_status.go_no_go_action,
            expected="go",
            reason_code=f"control_status_{control_status.go_no_go_action}",
        ),
        LiveGateThresholdCheck(
            check_id="limited_live_ready_for_review",
            category="readiness",
            description="Future limited-live gate status must be ready_for_review.",
            passed=readiness.limited_live_gate_status == "ready_for_review",
            actual=readiness.limited_live_gate_status,
            expected="ready_for_review",
            reason_code="limited_live_gate_not_ready_for_review",
        ),
        LiveGateThresholdCheck(
            check_id="min_completed_sessions",
            category="readiness",
            description="Completed sessions must meet the minimum soak requirement.",
            passed=soak.completed_session_count >= config.min_completed_sessions,
            actual=str(soak.completed_session_count),
            expected=f">={config.min_completed_sessions}",
            reason_code="insufficient_completed_sessions",
        ),
        LiveGateThresholdCheck(
            check_id="min_executed_sessions",
            category="readiness",
            description="Executed sessions must meet the minimum paper baseline requirement.",
            passed=soak.executed_session_count >= config.min_executed_sessions,
            actual=str(soak.executed_session_count),
            expected=f">={config.min_executed_sessions}",
            reason_code="insufficient_executed_sessions",
        ),
        LiveGateThresholdCheck(
            check_id="max_failed_sessions",
            category="readiness",
            description="Failed sessions must stay within the allowed maximum.",
            passed=soak.failed_session_count <= config.max_failed_sessions,
            actual=str(soak.failed_session_count),
            expected=f"<={config.max_failed_sessions}",
            reason_code="failed_sessions_present",
        ),
        LiveGateThresholdCheck(
            check_id="max_interrupted_sessions",
            category="readiness",
            description="Interrupted sessions must stay within the allowed maximum.",
            passed=soak.interrupted_session_count <= config.max_interrupted_sessions,
            actual=str(soak.interrupted_session_count),
            expected=f"<={config.max_interrupted_sessions}",
            reason_code="interrupted_sessions_present",
        ),
        LiveGateThresholdCheck(
            check_id="min_shadow_sessions",
            category="readiness",
            description="Shadow evaluation must include the minimum number of sessions.",
            passed=shadow.shadow_session_count >= config.min_shadow_sessions,
            actual=str(shadow.shadow_session_count),
            expected=f">={config.min_shadow_sessions}",
            reason_code="insufficient_shadow_sessions",
        ),
        LiveGateThresholdCheck(
            check_id="min_shadow_request_count",
            category="readiness",
            description="Shadow evaluation must include the minimum number of normalized requests.",
            passed=shadow.request_count >= config.min_shadow_request_count,
            actual=str(shadow.request_count),
            expected=f">={config.min_shadow_request_count}",
            reason_code="insufficient_shadow_requests",
        ),
        LiveGateThresholdCheck(
            check_id="shadow_artifacts_present",
            category="readiness",
            description="Shadow evidence artifacts must be present for evaluated sessions.",
            passed=shadow.all_shadow_artifacts_present,
            actual="present" if shadow.all_shadow_artifacts_present else "missing",
            expected="present",
            reason_code="shadow_artifacts_missing",
        ),
    ]
    return LiveGateThresholdSummary(
        runtime_id=runtime_id,
        generated_at=generated_at,
        blocking_passed=all(check.passed for check in checks if check.category == "blocking"),
        readiness_passed=all(check.passed for check in checks if check.category == "readiness"),
        checks=checks,
    )


def build_live_gate_decision(
    *,
    runtime_id: str,
    generated_at: datetime,
    threshold_summary: LiveGateThresholdSummary,
    soak_evaluation_path: Path,
    shadow_evaluation_path: Path,
    threshold_summary_path: Path,
) -> LiveGateDecision:
    blocking_failures = [
        check.reason_code
        for check in threshold_summary.checks
        if check.category == "blocking" and not check.passed and check.reason_code is not None
    ]
    readiness_failures = [
        check.reason_code
        for check in threshold_summary.checks
        if check.category == "readiness" and not check.passed and check.reason_code is not None
    ]

    if blocking_failures:
        state: Literal["ready", "not_ready", "blocked"] = "blocked"
        summary = "Live gate is blocked by explicit runtime or operator controls."
        reasons = blocking_failures
    elif readiness_failures:
        state = "not_ready"
        summary = "Live gate is not ready because soak or shadow thresholds are not yet met."
        reasons = readiness_failures
    else:
        state = "ready"
        summary = "Live gate is ready for future limited-live review. No live execution is enabled."
        reasons = []

    return LiveGateDecision(
        runtime_id=runtime_id,
        generated_at=generated_at,
        state=state,
        summary=summary,
        reason_codes=reasons,
        soak_evaluation_path=soak_evaluation_path,
        shadow_evaluation_path=shadow_evaluation_path,
        threshold_summary_path=threshold_summary_path,
    )


def build_live_gate_report(
    *,
    decision: LiveGateDecision,
    threshold_summary: LiveGateThresholdSummary,
    soak: ForwardPaperSoakEvaluation,
    shadow: ForwardPaperShadowEvaluation,
) -> str:
    lines = [
        "# Forward Paper Live Gate",
        "",
        "## Decision",
        f"- runtime_id: {decision.runtime_id}",
        f"- state: {decision.state}",
        f"- summary: {decision.summary}",
        f"- reason_codes: {', '.join(decision.reason_codes) if decision.reason_codes else 'none'}",
        "",
        "## Soak Summary",
        f"- session_count: {soak.session_count}",
        f"- completed_session_count: {soak.completed_session_count}",
        f"- executed_session_count: {soak.executed_session_count}",
        f"- blocked_session_count: {soak.blocked_session_count}",
        f"- skipped_session_count: {soak.skipped_session_count}",
        f"- failed_session_count: {soak.failed_session_count}",
        f"- interrupted_session_count: {soak.interrupted_session_count}",
        f"- cumulative_net_realized_pnl_usd: {soak.cumulative_net_realized_pnl_usd:.6f}",
        "- latest_ending_equity_usd: "
        f"{soak.latest_ending_equity_usd if soak.latest_ending_equity_usd is not None else 'none'}",
        f"- average_return_fraction: {soak.average_return_fraction:.12f}",
        "",
        "## Shadow Summary",
        f"- shadow_session_count: {shadow.shadow_session_count}",
        f"- shadow_executed_session_count: {shadow.shadow_executed_session_count}",
        f"- request_count: {shadow.request_count}",
        f"- would_send_count: {shadow.would_send_count}",
        f"- accepted_count: {shadow.accepted_count}",
        f"- rejected_count: {shadow.rejected_count}",
        f"- duplicate_count: {shadow.duplicate_count}",
        f"- status_count: {shadow.status_count}",
        f"- terminal_status_count: {shadow.terminal_status_count}",
        f"- all_shadow_artifacts_present: {str(shadow.all_shadow_artifacts_present).lower()}",
        "",
        "## Threshold Checks",
    ]
    for check in threshold_summary.checks:
        status = "pass" if check.passed else "fail"
        lines.append(
            f"- [{status}] {check.check_id}: actual={check.actual} expected={check.expected}"
        )
    lines.append("")
    return "\n".join(lines)
