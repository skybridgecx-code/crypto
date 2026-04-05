from __future__ import annotations

import json
from datetime import datetime
from math import fsum
from pathlib import Path

from crypto_agent.runtime.models import (
    ForwardPaperSessionSummary,
    ForwardPaperSoakEvaluation,
    ForwardPaperSoakSessionRow,
)


def load_runtime_session_summaries(sessions_dir: Path) -> list[ForwardPaperSessionSummary]:
    session_paths = sorted(sessions_dir.glob("session-[0-9][0-9][0-9][0-9].json"))
    sessions = [
        ForwardPaperSessionSummary.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for path in session_paths
    ]
    return sorted(sessions, key=lambda session: session.session_number)


def build_forward_paper_soak_evaluation(
    *,
    runtime_id: str,
    sessions: list[ForwardPaperSessionSummary],
    generated_at: datetime,
) -> ForwardPaperSoakEvaluation:
    rows = [
        ForwardPaperSoakSessionRow(
            session_id=session.session_id,
            session_number=session.session_number,
            status=session.status,
            session_outcome=session.session_outcome,
            execution_mode=session.execution_mode,
            run_id=session.run_id,
            return_fraction=session.pnl.return_fraction if session.pnl is not None else None,
            ending_equity_usd=session.pnl.ending_equity_usd if session.pnl is not None else None,
            control_action=session.control_action,
            control_reason_codes=session.control_reason_codes,
        )
        for session in sessions
    ]
    completed_sessions = [session for session in sessions if session.status == "completed"]
    executed_sessions = [
        session
        for session in completed_sessions
        if session.session_outcome == "executed" and session.pnl is not None
    ]
    executed_pnls = [session.pnl for session in executed_sessions if session.pnl is not None]
    return_fractions = [pnl.return_fraction for pnl in executed_pnls]
    return ForwardPaperSoakEvaluation(
        runtime_id=runtime_id,
        generated_at=generated_at,
        session_count=len(sessions),
        completed_session_count=len(completed_sessions),
        executed_session_count=sum(
            1 for session in completed_sessions if session.session_outcome == "executed"
        ),
        blocked_session_count=sum(
            1 for session in completed_sessions if session.session_outcome == "blocked_controls"
        ),
        skipped_session_count=sum(
            1
            for session in completed_sessions
            if session.session_outcome
            in {
                "skipped_stale_feed",
                "skipped_degraded_feed",
                "skipped_unavailable_feed",
            }
        ),
        failed_session_count=sum(1 for session in sessions if session.status == "failed"),
        interrupted_session_count=sum(1 for session in sessions if session.status == "interrupted"),
        cumulative_net_realized_pnl_usd=fsum(pnl.net_realized_pnl_usd for pnl in executed_pnls),
        latest_ending_equity_usd=executed_pnls[-1].ending_equity_usd if executed_pnls else None,
        average_return_fraction=fsum(return_fractions) / len(return_fractions)
        if return_fractions
        else 0.0,
        worst_session_return_fraction=min(return_fractions) if return_fractions else None,
        best_session_return_fraction=max(return_fractions) if return_fractions else None,
        rows=rows,
    )
