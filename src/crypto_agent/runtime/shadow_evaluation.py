from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from crypto_agent.execution.models import (
    ExecutionRequestArtifact,
    ExecutionResultArtifact,
    ExecutionStatusArtifact,
)
from crypto_agent.runtime.models import (
    ForwardPaperSessionSummary,
    ForwardPaperShadowEvaluation,
    ForwardPaperShadowEvaluationRow,
)


def _load_request_artifact(path: Path) -> ExecutionRequestArtifact:
    return ExecutionRequestArtifact.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_result_artifact(path: Path) -> ExecutionResultArtifact:
    return ExecutionResultArtifact.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_status_artifact(path: Path) -> ExecutionStatusArtifact:
    return ExecutionStatusArtifact.model_validate(json.loads(path.read_text(encoding="utf-8")))


def build_forward_paper_shadow_evaluation(
    *,
    runtime_id: str,
    sessions: list[ForwardPaperSessionSummary],
    generated_at: datetime,
) -> ForwardPaperShadowEvaluation:
    shadow_sessions = [session for session in sessions if session.execution_mode == "shadow"]
    rows: list[ForwardPaperShadowEvaluationRow] = []
    missing_request_artifact_count = 0
    missing_result_artifact_count = 0
    missing_status_artifact_count = 0

    for session in shadow_sessions:
        request_artifact = None
        result_artifact = None
        status_artifact = None
        if (
            session.execution_request_path is not None
            and Path(session.execution_request_path).exists()
        ):
            request_artifact = _load_request_artifact(Path(session.execution_request_path))
        else:
            missing_request_artifact_count += 1
        if (
            session.execution_result_path is not None
            and Path(session.execution_result_path).exists()
        ):
            result_artifact = _load_result_artifact(Path(session.execution_result_path))
        elif session.execution_result_path is None:
            missing_result_artifact_count += 1
        else:
            missing_result_artifact_count += 1
        if (
            session.execution_status_path is not None
            and Path(session.execution_status_path).exists()
        ):
            status_artifact = _load_status_artifact(Path(session.execution_status_path))
        elif session.execution_status_path is None:
            missing_status_artifact_count += 1
        else:
            missing_status_artifact_count += 1

        rows.append(
            ForwardPaperShadowEvaluationRow(
                session_id=session.session_id,
                session_number=session.session_number,
                run_id=session.run_id,
                session_outcome=session.session_outcome,
                control_action=session.control_action,
                request_count=(0 if request_artifact is None else request_artifact.request_count),
                rejected_request_count=(
                    0 if request_artifact is None else request_artifact.rejected_request_count
                ),
                would_send_count=(
                    0
                    if result_artifact is None
                    else sum(
                        1 for result in result_artifact.results if result.status == "would_send"
                    )
                ),
                duplicate_count=(
                    0
                    if result_artifact is None
                    else sum(
                        1 for result in result_artifact.results if result.status == "duplicate"
                    )
                ),
                accepted_count=(
                    0
                    if result_artifact is None
                    else sum(1 for result in result_artifact.results if result.status == "accepted")
                ),
                rejected_count=(
                    0
                    if result_artifact is None
                    else sum(1 for result in result_artifact.results if result.status == "rejected")
                ),
                status_count=0 if status_artifact is None else status_artifact.status_count,
                terminal_status_count=(
                    0 if status_artifact is None else status_artifact.terminal_status_count
                ),
                filled_status_count=(
                    0
                    if status_artifact is None
                    else sum(1 for state in status_artifact.statuses if state.state == "filled")
                ),
                canceled_status_count=(
                    0
                    if status_artifact is None
                    else sum(1 for state in status_artifact.statuses if state.state == "canceled")
                ),
                all_artifacts_present=all(
                    artifact is not None
                    for artifact in (request_artifact, result_artifact, status_artifact)
                ),
            )
        )

    return ForwardPaperShadowEvaluation(
        runtime_id=runtime_id,
        generated_at=generated_at,
        shadow_session_count=len(shadow_sessions),
        shadow_executed_session_count=sum(
            1 for session in shadow_sessions if session.session_outcome == "executed"
        ),
        request_count=sum(row.request_count for row in rows),
        rejected_request_count=sum(row.rejected_request_count for row in rows),
        would_send_count=sum(row.would_send_count for row in rows),
        duplicate_count=sum(row.duplicate_count for row in rows),
        accepted_count=sum(row.accepted_count for row in rows),
        rejected_count=sum(row.rejected_count for row in rows),
        status_count=sum(row.status_count for row in rows),
        terminal_status_count=sum(row.terminal_status_count for row in rows),
        filled_status_count=sum(row.filled_status_count for row in rows),
        canceled_status_count=sum(row.canceled_status_count for row in rows),
        missing_request_artifact_count=missing_request_artifact_count,
        missing_result_artifact_count=missing_result_artifact_count,
        missing_status_artifact_count=missing_status_artifact_count,
        all_shadow_artifacts_present=all(row.all_artifacts_present for row in rows),
        rows=rows,
    )
