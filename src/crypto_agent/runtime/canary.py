from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

from crypto_agent.runtime.models import (
    ForwardPaperSessionSummary,
    ForwardPaperShadowCanaryEvaluation,
    ForwardPaperShadowCanaryRow,
)


def _path_exists(path: Path | None) -> bool:
    return path is not None and Path(path).exists()


def build_forward_paper_shadow_canary_evaluation(
    *,
    runtime_id: str,
    execution_mode: Literal["paper", "shadow", "sandbox"],
    market_source: Literal["replay", "binance_spot"],
    sessions: list[ForwardPaperSessionSummary],
    generated_at: datetime,
) -> ForwardPaperShadowCanaryEvaluation:
    rows = [
        ForwardPaperShadowCanaryRow(
            session_id=session.session_id,
            session_number=session.session_number,
            run_id=session.run_id,
            status=session.status,
            session_outcome=session.session_outcome,
            request_artifact_present=_path_exists(session.execution_request_path),
            result_artifact_present=_path_exists(session.execution_result_path),
            status_artifact_present=_path_exists(session.execution_status_path),
            skip_evidence_present=_path_exists(session.skip_evidence_path),
            all_expected_evidence_present=(
                _path_exists(session.skip_evidence_path)
                if session.session_outcome == "skipped_unavailable_feed"
                else (
                    _path_exists(session.execution_request_path)
                    and _path_exists(session.execution_result_path)
                    and _path_exists(session.execution_status_path)
                )
                if session.session_outcome == "executed"
                else True
            ),
        )
        for session in sessions
    ]
    applicable = execution_mode == "shadow" and market_source == "binance_spot"
    completed_rows = [row for row in rows if row.status == "completed"]
    executed_count = sum(1 for row in completed_rows if row.session_outcome == "executed")
    blocked_count = sum(1 for row in completed_rows if row.session_outcome == "blocked_controls")
    skipped_stale_count = sum(
        1 for row in completed_rows if row.session_outcome == "skipped_stale_feed"
    )
    skipped_degraded_count = sum(
        1 for row in completed_rows if row.session_outcome == "skipped_degraded_feed"
    )
    skipped_unavailable_count = sum(
        1 for row in completed_rows if row.session_outcome == "skipped_unavailable_feed"
    )
    failed_count = sum(1 for row in rows if row.status == "failed")
    interrupted_count = sum(1 for row in rows if row.status == "interrupted")
    request_artifact_count = sum(1 for row in rows if row.request_artifact_present)
    result_artifact_count = sum(1 for row in rows if row.result_artifact_present)
    status_artifact_count = sum(1 for row in rows if row.status_artifact_present)
    skip_evidence_count = sum(1 for row in rows if row.skip_evidence_present)
    all_expected_evidence_present = all(row.all_expected_evidence_present for row in rows)
    reason_codes: list[str]
    state: Literal["pass", "fail", "not_applicable"]

    if not applicable:
        state = "not_applicable"
        summary = "Shadow canary applies only to shadow mode with live binance_spot input."
        reason_codes = ["not_shadow_live_runtime"]
    else:
        reason_codes = []
        if not rows:
            reason_codes.append("no_sessions")
        if failed_count > 0:
            reason_codes.append("failed_sessions_present")
        if interrupted_count > 0:
            reason_codes.append("interrupted_sessions_present")
        if blocked_count > 0:
            reason_codes.append("blocked_sessions_present")
        if skipped_stale_count > 0:
            reason_codes.append("stale_feed_sessions_present")
        if skipped_degraded_count > 0:
            reason_codes.append("degraded_feed_sessions_present")
        if skipped_unavailable_count > 0:
            reason_codes.append("unavailable_feed_sessions_present")
        if executed_count != len(rows):
            reason_codes.append("not_all_sessions_executed")
        if not all_expected_evidence_present:
            reason_codes.append("missing_shadow_evidence")

        if reason_codes:
            state = "fail"
            summary = (
                f"Shadow canary failed: {executed_count} of {len(rows)} sessions executed with "
                "expected evidence."
            )
        else:
            state = "pass"
            summary = (
                f"Shadow canary passed: all {len(rows)} sessions executed with expected evidence."
            )

    return ForwardPaperShadowCanaryEvaluation(
        runtime_id=runtime_id,
        generated_at=generated_at,
        execution_mode=execution_mode,
        market_source=market_source,
        applicable=applicable,
        state=state,
        summary=summary,
        reason_codes=reason_codes,
        session_count=len(rows),
        completed_session_count=len(completed_rows),
        executed_session_count=executed_count,
        blocked_session_count=blocked_count,
        skipped_stale_feed_session_count=skipped_stale_count,
        skipped_degraded_feed_session_count=skipped_degraded_count,
        skipped_unavailable_feed_session_count=skipped_unavailable_count,
        failed_session_count=failed_count,
        interrupted_session_count=interrupted_count,
        request_artifact_count=request_artifact_count,
        result_artifact_count=result_artifact_count,
        status_artifact_count=status_artifact_count,
        skip_evidence_count=skip_evidence_count,
        all_expected_evidence_present=all_expected_evidence_present,
        rows=rows,
    )
