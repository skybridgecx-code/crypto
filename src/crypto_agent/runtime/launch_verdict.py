from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from crypto_agent.policy.live_controls import LiveControlStatusArtifact
from crypto_agent.policy.readiness import LiveReadinessStatus
from crypto_agent.runtime.models import (
    ForwardPaperShadowCanaryEvaluation,
    LiveGateDecision,
    LiveGateThresholdSummary,
    LiveLaunchVerdictArtifact,
    LiveLaunchVerdictChecks,
    LiveLaunchVerdictInputArtifact,
    LiveMarketPreflightArtifact,
)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def _dedupe_reason_codes(reason_codes: list[str]) -> list[str]:
    ordered: list[str] = []
    seen: set[str] = set()
    for reason_code in reason_codes:
        normalized = reason_code.strip()
        if not normalized or normalized in seen:
            continue
        ordered.append(normalized)
        seen.add(normalized)
    return ordered


def _failed_threshold_reason_codes(threshold_summary: LiveGateThresholdSummary) -> list[str]:
    return [
        check.reason_code
        for check in threshold_summary.checks
        if not check.passed and check.reason_code is not None
    ]


def build_live_launch_verdict(
    *,
    runtime_id: str,
    generated_at: datetime,
    preflight_artifact: LiveMarketPreflightArtifact | None,
    preflight_path: Path,
    shadow_canary: ForwardPaperShadowCanaryEvaluation,
    shadow_canary_path: Path,
    threshold_summary: LiveGateThresholdSummary,
    threshold_summary_path: Path,
    gate_decision: LiveGateDecision,
    gate_decision_path: Path,
    readiness_status: LiveReadinessStatus,
    readiness_status_path: Path,
    control_status: LiveControlStatusArtifact,
    control_status_path: Path,
) -> LiveLaunchVerdictArtifact:
    normalized_generated_at = _normalize_datetime(generated_at)
    checks = LiveLaunchVerdictChecks(
        preflight_batch_ready=(
            preflight_artifact is not None and preflight_artifact.batch_readiness is True
        ),
        shadow_canary_passed=shadow_canary.state == "pass",
        blocking_thresholds_passed=threshold_summary.blocking_passed,
        readiness_thresholds_passed=threshold_summary.readiness_passed,
        live_gate_ready=gate_decision.state == "ready",
        operator_readiness_ready=readiness_status.status == "ready",
        limited_live_gate_ready_for_review=(
            readiness_status.limited_live_gate_status == "ready_for_review"
        ),
    )

    reason_codes: list[str] = []
    if preflight_artifact is None:
        reason_codes.append("preflight_missing")
    elif not checks.preflight_batch_ready:
        reason_codes.extend(
            [
                "preflight_not_batch_ready",
                f"preflight_status_{preflight_artifact.status}",
                f"preflight_reason_{preflight_artifact.batch_readiness_reason}",
            ]
        )

    if not checks.shadow_canary_passed:
        reason_codes.append("shadow_canary_not_passed")
    reason_codes.extend(shadow_canary.reason_codes)

    if not checks.blocking_thresholds_passed:
        reason_codes.append("live_gate_blocking_thresholds_not_passed")
    if not checks.readiness_thresholds_passed:
        reason_codes.append("live_gate_readiness_thresholds_not_passed")
    reason_codes.extend(_failed_threshold_reason_codes(threshold_summary))

    if not checks.live_gate_ready:
        reason_codes.append(f"live_gate_state_{gate_decision.state}")
    reason_codes.extend(gate_decision.reason_codes)

    if not checks.operator_readiness_ready:
        reason_codes.append("operator_readiness_not_ready")
    if not checks.limited_live_gate_ready_for_review:
        reason_codes.append("limited_live_gate_not_ready_for_review")
    reason_codes.extend(readiness_status.reason_codes)

    if control_status.go_no_go_action != "go":
        reason_codes.append(f"control_status_{control_status.go_no_go_action}")
    reason_codes.extend(control_status.go_no_go_reason_codes)

    deduped_reason_codes = _dedupe_reason_codes(reason_codes)
    launchable = (
        checks.preflight_batch_ready
        and checks.shadow_canary_passed
        and checks.blocking_thresholds_passed
        and checks.readiness_thresholds_passed
        and checks.live_gate_ready
        and checks.operator_readiness_ready
        and checks.limited_live_gate_ready_for_review
        and not deduped_reason_codes
    )

    verdict: Literal["launchable_here_now", "not_launchable_here_now"] = (
        "launchable_here_now" if launchable else "not_launchable_here_now"
    )
    summary = (
        "Current preflight, canary, gate, readiness, and control artifacts agree that this "
        "environment is launchable here now for operator review only. No live execution "
        "authority is enabled by this artifact."
        if launchable
        else "Current preflight, canary, gate, readiness, or control artifacts do not support "
        "launch here now. No live execution authority is enabled by this artifact."
    )

    return LiveLaunchVerdictArtifact(
        runtime_id=runtime_id,
        generated_at=normalized_generated_at,
        artifact_only=True,
        execution_authority="none",
        verdict=verdict,
        summary=summary,
        reason_codes=deduped_reason_codes,
        checks=checks,
        input_artifacts=[
            LiveLaunchVerdictInputArtifact(
                artifact_id="live_market_preflight",
                path=preflight_path,
                present=preflight_artifact is not None and preflight_path.exists(),
                status=preflight_artifact.status if preflight_artifact is not None else None,
                state=None,
                reason_codes=(
                    []
                    if preflight_artifact is None or preflight_artifact.batch_readiness
                    else [
                        "preflight_not_batch_ready",
                        f"preflight_reason_{preflight_artifact.batch_readiness_reason}",
                    ]
                ),
            ),
            LiveLaunchVerdictInputArtifact(
                artifact_id="shadow_canary_evaluation",
                path=shadow_canary_path,
                present=shadow_canary_path.exists(),
                status=None,
                state=shadow_canary.state,
                reason_codes=shadow_canary.reason_codes,
            ),
            LiveLaunchVerdictInputArtifact(
                artifact_id="live_gate_threshold_summary",
                path=threshold_summary_path,
                present=threshold_summary_path.exists(),
                status=(
                    "passed"
                    if threshold_summary.blocking_passed and threshold_summary.readiness_passed
                    else "not_passed"
                ),
                state=None,
                reason_codes=_failed_threshold_reason_codes(threshold_summary),
            ),
            LiveLaunchVerdictInputArtifact(
                artifact_id="live_gate_decision",
                path=gate_decision_path,
                present=gate_decision_path.exists(),
                status=None,
                state=gate_decision.state,
                reason_codes=gate_decision.reason_codes,
            ),
            LiveLaunchVerdictInputArtifact(
                artifact_id="live_readiness_status",
                path=readiness_status_path,
                present=readiness_status_path.exists(),
                status=readiness_status.status,
                state=readiness_status.limited_live_gate_status,
                reason_codes=readiness_status.reason_codes,
            ),
            LiveLaunchVerdictInputArtifact(
                artifact_id="live_control_status",
                path=control_status_path,
                present=control_status_path.exists(),
                status=control_status.go_no_go_action,
                state=None,
                reason_codes=control_status.go_no_go_reason_codes,
            ),
        ],
    )
