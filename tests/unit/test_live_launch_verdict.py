from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.policy.live_controls import LiveControlStatusArtifact
from crypto_agent.policy.readiness import LiveReadinessStatus
from crypto_agent.runtime.launch_verdict import build_live_launch_verdict
from crypto_agent.runtime.models import (
    ForwardPaperShadowCanaryEvaluation,
    LiveGateDecision,
    LiveGateThresholdCheck,
    LiveGateThresholdSummary,
    LiveMarketPreflightArtifact,
)


def _ts(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def _preflight_ready(runtime_id: str) -> LiveMarketPreflightArtifact:
    return LiveMarketPreflightArtifact(
        runtime_id=runtime_id,
        market_source="binance_spot",
        symbol="BTCUSDT",
        interval="1m",
        configured_base_url="https://api.binance.com",
        retry_count=2,
        retry_delay_seconds=2.0,
        attempt_count_used=1,
        observed_at=_ts(2026, 4, 17, 12, 0),
        status="batch_ready",
        success=True,
        single_probe_success=True,
        batch_readiness=True,
        batch_readiness_reason="batch_ready",
        feed_health_status="healthy",
        feed_health_message=None,
        required_closed_candle_count=8,
        candle_count=8,
        stability_window_probe_count=2,
        stability_window_success_count=2,
        stability_window_result="passed",
        stability_failure_status=None,
        stability_probe_attempt_count_used=1,
        stability_feed_health_status="healthy",
        stability_feed_health_message=None,
        order_book_present=True,
        constraints_present=True,
    )


def _canary(
    runtime_id: str,
    state: str,
    reason_codes: list[str],
) -> ForwardPaperShadowCanaryEvaluation:
    return ForwardPaperShadowCanaryEvaluation(
        runtime_id=runtime_id,
        generated_at=_ts(2026, 4, 17, 12, 1),
        execution_mode="shadow",
        market_source="binance_spot",
        applicable=True,
        state=state,
        summary=f"Canary {state}.",
        reason_codes=reason_codes,
        session_count=3,
        completed_session_count=3,
        executed_session_count=3 if state == "pass" else 2,
        blocked_session_count=0,
        skipped_stale_feed_session_count=0,
        skipped_degraded_feed_session_count=0,
        skipped_unavailable_feed_session_count=0 if state == "pass" else 1,
        failed_session_count=0,
        interrupted_session_count=0,
        request_artifact_count=3 if state == "pass" else 2,
        result_artifact_count=3 if state == "pass" else 2,
        status_artifact_count=3 if state == "pass" else 2,
        skip_evidence_count=0 if state == "pass" else 1,
        all_expected_evidence_present=True,
        rows=[],
    )


def _thresholds(
    runtime_id: str,
    *,
    blocking_passed: bool,
    readiness_passed: bool,
) -> LiveGateThresholdSummary:
    checks: list[LiveGateThresholdCheck] = []
    if not blocking_passed:
        checks.append(
            LiveGateThresholdCheck(
                check_id="operator_ready",
                category="blocking",
                description="Operator readiness must be ready.",
                passed=False,
                actual="not_ready",
                expected="ready",
                reason_code="operator_not_ready_status",
            )
        )
    return LiveGateThresholdSummary(
        runtime_id=runtime_id,
        generated_at=_ts(2026, 4, 17, 12, 2),
        blocking_passed=blocking_passed,
        readiness_passed=readiness_passed,
        checks=checks,
    )


def _gate(runtime_id: str, state: str, reason_codes: list[str]) -> LiveGateDecision:
    return LiveGateDecision(
        runtime_id=runtime_id,
        generated_at=_ts(2026, 4, 17, 12, 3),
        state=state,
        summary=f"Gate is {state}.",
        reason_codes=reason_codes,
        soak_evaluation_path=Path("runs") / runtime_id / "soak_evaluation.json",
        shadow_evaluation_path=Path("runs") / runtime_id / "shadow_evaluation.json",
        threshold_summary_path=Path("runs") / runtime_id / "live_gate_threshold_summary.json",
    )


def _readiness(
    runtime_id: str,
    *,
    status: str,
    limited_live_gate_status: str,
    reason_codes: list[str],
) -> LiveReadinessStatus:
    return LiveReadinessStatus(
        runtime_id=runtime_id,
        updated_at=_ts(2026, 4, 17, 12, 4),
        status=status,
        limited_live_gate_status=limited_live_gate_status,
        note=None,
        reason_codes=reason_codes,
    )


def _control_status(
    runtime_id: str,
    *,
    action: str,
    reason_codes: list[str],
) -> LiveControlStatusArtifact:
    return LiveControlStatusArtifact(
        runtime_id=runtime_id,
        updated_at=_ts(2026, 4, 17, 12, 5),
        execution_mode="shadow",
        market_source="binance_spot",
        readiness_status="ready",
        limited_live_gate_status="ready_for_review",
        allowed_execution_modes=["paper", "shadow", "sandbox"],
        symbol_allowlist=["BTCUSDT"],
        per_symbol_max_notional_usd={"BTCUSDT": 25.0},
        max_session_loss_fraction=0.03,
        max_daily_loss_fraction=0.015,
        max_open_positions=1,
        manual_approval_above_notional_usd=1.0,
        manual_halt_active=False,
        manual_halt_reason=None,
        approval_granted=True,
        current_open_position_count=0,
        current_daily_loss_fraction=0.0,
        last_session_loss_fraction=0.0,
        latest_decision_path=None,
        go_no_go_action=action,
        go_no_go_summary="Control status for verdict tests.",
        go_no_go_reason_codes=reason_codes,
    )


def test_live_launch_verdict_is_launchable_when_all_checks_pass(tmp_path: Path) -> None:
    runtime_id = "launch-verdict-pass"
    runtime_dir = tmp_path / "runs" / runtime_id
    preflight_path = _touch(runtime_dir / "live_market_preflight.json")
    canary_path = _touch(runtime_dir / "shadow_canary_evaluation.json")
    thresholds_path = _touch(runtime_dir / "live_gate_threshold_summary.json")
    gate_path = _touch(runtime_dir / "live_gate_decision.json")
    readiness_path = _touch(runtime_dir / "live_readiness_status.json")
    control_path = _touch(runtime_dir / "live_control_status.json")

    verdict = build_live_launch_verdict(
        runtime_id=runtime_id,
        generated_at=_ts(2026, 4, 17, 12, 6),
        preflight_artifact=_preflight_ready(runtime_id),
        preflight_path=preflight_path,
        shadow_canary=_canary(runtime_id, "pass", []),
        shadow_canary_path=canary_path,
        threshold_summary=_thresholds(runtime_id, blocking_passed=True, readiness_passed=True),
        threshold_summary_path=thresholds_path,
        gate_decision=_gate(runtime_id, "ready", []),
        gate_decision_path=gate_path,
        readiness_status=_readiness(
            runtime_id,
            status="ready",
            limited_live_gate_status="ready_for_review",
            reason_codes=[],
        ),
        readiness_status_path=readiness_path,
        control_status=_control_status(runtime_id, action="go", reason_codes=[]),
        control_status_path=control_path,
    )

    assert verdict.verdict == "launchable_here_now"
    assert verdict.reason_codes == []
    assert verdict.checks.preflight_batch_ready is True
    assert verdict.checks.shadow_canary_passed is True
    assert verdict.checks.live_gate_ready is True
    assert verdict.artifact_only is True
    assert verdict.execution_authority == "none"


def test_live_launch_verdict_is_not_launchable_when_preflight_is_not_batch_ready(
    tmp_path: Path,
) -> None:
    runtime_id = "launch-verdict-preflight-fail"
    runtime_dir = tmp_path / "runs" / runtime_id
    canary_path = _touch(runtime_dir / "shadow_canary_evaluation.json")
    thresholds_path = _touch(runtime_dir / "live_gate_threshold_summary.json")
    gate_path = _touch(runtime_dir / "live_gate_decision.json")
    readiness_path = _touch(runtime_dir / "live_readiness_status.json")
    control_path = _touch(runtime_dir / "live_control_status.json")

    verdict = build_live_launch_verdict(
        runtime_id=runtime_id,
        generated_at=_ts(2026, 4, 17, 12, 6),
        preflight_artifact=None,
        preflight_path=runtime_dir / "live_market_preflight.json",
        shadow_canary=_canary(runtime_id, "pass", []),
        shadow_canary_path=canary_path,
        threshold_summary=_thresholds(runtime_id, blocking_passed=True, readiness_passed=True),
        threshold_summary_path=thresholds_path,
        gate_decision=_gate(runtime_id, "ready", []),
        gate_decision_path=gate_path,
        readiness_status=_readiness(
            runtime_id,
            status="ready",
            limited_live_gate_status="ready_for_review",
            reason_codes=[],
        ),
        readiness_status_path=readiness_path,
        control_status=_control_status(runtime_id, action="go", reason_codes=[]),
        control_status_path=control_path,
    )

    assert verdict.verdict == "not_launchable_here_now"
    assert verdict.checks.preflight_batch_ready is False
    assert "preflight_missing" in verdict.reason_codes


def test_live_launch_verdict_is_not_launchable_when_canary_fails(tmp_path: Path) -> None:
    runtime_id = "launch-verdict-canary-fail"
    runtime_dir = tmp_path / "runs" / runtime_id
    preflight_path = _touch(runtime_dir / "live_market_preflight.json")
    canary_path = _touch(runtime_dir / "shadow_canary_evaluation.json")
    thresholds_path = _touch(runtime_dir / "live_gate_threshold_summary.json")
    gate_path = _touch(runtime_dir / "live_gate_decision.json")
    readiness_path = _touch(runtime_dir / "live_readiness_status.json")
    control_path = _touch(runtime_dir / "live_control_status.json")

    verdict = build_live_launch_verdict(
        runtime_id=runtime_id,
        generated_at=_ts(2026, 4, 17, 12, 6),
        preflight_artifact=_preflight_ready(runtime_id),
        preflight_path=preflight_path,
        shadow_canary=_canary(runtime_id, "fail", ["unavailable_feed_sessions_present"]),
        shadow_canary_path=canary_path,
        threshold_summary=_thresholds(runtime_id, blocking_passed=True, readiness_passed=True),
        threshold_summary_path=thresholds_path,
        gate_decision=_gate(runtime_id, "ready", []),
        gate_decision_path=gate_path,
        readiness_status=_readiness(
            runtime_id,
            status="ready",
            limited_live_gate_status="ready_for_review",
            reason_codes=[],
        ),
        readiness_status_path=readiness_path,
        control_status=_control_status(runtime_id, action="go", reason_codes=[]),
        control_status_path=control_path,
    )

    assert verdict.verdict == "not_launchable_here_now"
    assert verdict.checks.shadow_canary_passed is False
    assert "shadow_canary_not_passed" in verdict.reason_codes
    assert "unavailable_feed_sessions_present" in verdict.reason_codes


def test_live_launch_verdict_is_not_launchable_when_operator_readiness_is_not_ready(
    tmp_path: Path,
) -> None:
    runtime_id = "launch-verdict-operator-not-ready"
    runtime_dir = tmp_path / "runs" / runtime_id
    preflight_path = _touch(runtime_dir / "live_market_preflight.json")
    canary_path = _touch(runtime_dir / "shadow_canary_evaluation.json")
    thresholds_path = _touch(runtime_dir / "live_gate_threshold_summary.json")
    gate_path = _touch(runtime_dir / "live_gate_decision.json")
    readiness_path = _touch(runtime_dir / "live_readiness_status.json")
    control_path = _touch(runtime_dir / "live_control_status.json")

    verdict = build_live_launch_verdict(
        runtime_id=runtime_id,
        generated_at=_ts(2026, 4, 17, 12, 6),
        preflight_artifact=_preflight_ready(runtime_id),
        preflight_path=preflight_path,
        shadow_canary=_canary(runtime_id, "pass", []),
        shadow_canary_path=canary_path,
        threshold_summary=_thresholds(runtime_id, blocking_passed=False, readiness_passed=True),
        threshold_summary_path=thresholds_path,
        gate_decision=_gate(runtime_id, "blocked", ["operator_not_ready_status"]),
        gate_decision_path=gate_path,
        readiness_status=_readiness(
            runtime_id,
            status="not_ready",
            limited_live_gate_status="ready_for_review",
            reason_codes=["operator_not_ready_status"],
        ),
        readiness_status_path=readiness_path,
        control_status=_control_status(runtime_id, action="go", reason_codes=[]),
        control_status_path=control_path,
    )

    assert verdict.verdict == "not_launchable_here_now"
    assert verdict.checks.operator_readiness_ready is False
    assert verdict.checks.blocking_thresholds_passed is False
    assert verdict.checks.live_gate_ready is False
    assert "operator_not_ready_status" in verdict.reason_codes
    assert "live_gate_state_blocked" in verdict.reason_codes
