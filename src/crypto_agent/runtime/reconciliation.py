from __future__ import annotations

import json
from datetime import datetime
from math import isclose
from pathlib import Path

from crypto_agent.runtime.account_state import build_runtime_account_state
from crypto_agent.runtime.models import (
    ForwardPaperReconciliationReport,
    ForwardPaperRecoveryStatus,
    ForwardPaperRuntimeAccountState,
    ForwardPaperRuntimePaths,
    ForwardPaperRuntimeStatus,
    ForwardPaperSessionSummary,
)

ACCOUNT_TOLERANCE = 1e-9


class RuntimeAccountMismatchError(RuntimeError):
    pass


def load_runtime_account_state(
    path: str | Path,
) -> ForwardPaperRuntimeAccountState | None:
    account_state_path = Path(path)
    if not account_state_path.exists():
        return None
    return ForwardPaperRuntimeAccountState.model_validate(
        json.loads(account_state_path.read_text(encoding="utf-8"))
    )


def write_runtime_account_state(
    path: str | Path,
    account_state: ForwardPaperRuntimeAccountState,
) -> Path:
    account_state_path = Path(path)
    account_state_path.parent.mkdir(parents=True, exist_ok=True)
    account_state_path.write_text(
        json.dumps(account_state.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return account_state_path


def write_reconciliation_report(
    path: str | Path,
    report: ForwardPaperReconciliationReport,
) -> Path:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return report_path


def load_reconciliation_report(
    path: str | Path,
) -> ForwardPaperReconciliationReport:
    report_path = Path(path)
    return ForwardPaperReconciliationReport.model_validate(
        json.loads(report_path.read_text(encoding="utf-8"))
    )


def write_recovery_status(
    path: str | Path,
    recovery_status: ForwardPaperRecoveryStatus,
) -> Path:
    recovery_status_path = Path(path)
    recovery_status_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_status_path.write_text(
        json.dumps(recovery_status.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return recovery_status_path


def load_forward_paper_session_summaries(
    sessions_dir: str | Path,
) -> list[ForwardPaperSessionSummary]:
    session_paths = sorted(Path(sessions_dir).glob("session-[0-9][0-9][0-9][0-9].json"))
    return [
        ForwardPaperSessionSummary.model_validate(
            json.loads(session_path.read_text(encoding="utf-8"))
        )
        for session_path in session_paths
    ]


def _float_difference(
    name: str,
    expected: float,
    actual: float,
    differences: list[str],
) -> None:
    if not isclose(expected, actual, rel_tol=0.0, abs_tol=ACCOUNT_TOLERANCE):
        differences.append(f"{name}: expected={expected} actual={actual}")


def _diff_account_states(
    expected: ForwardPaperRuntimeAccountState,
    actual: ForwardPaperRuntimeAccountState,
) -> list[str]:
    differences: list[str] = []
    if expected.as_of_session_id != actual.as_of_session_id:
        differences.append(
            "as_of_session_id: "
            f"expected={expected.as_of_session_id} actual={actual.as_of_session_id}"
        )
    if expected.as_of_run_id != actual.as_of_run_id:
        differences.append(
            f"as_of_run_id: expected={expected.as_of_run_id} actual={actual.as_of_run_id}"
        )

    for field_name in (
        "starting_equity_usd",
        "cash_balance_usd",
        "gross_position_notional_usd",
        "gross_realized_pnl_usd",
        "total_fee_usd",
        "net_realized_pnl_usd",
        "ending_unrealized_pnl_usd",
        "ending_equity_usd",
        "return_fraction",
    ):
        _float_difference(
            field_name,
            getattr(expected, field_name),
            getattr(actual, field_name),
            differences,
        )

    expected_positions = {position.symbol: position for position in expected.positions}
    actual_positions = {position.symbol: position for position in actual.positions}
    if sorted(expected_positions) != sorted(actual_positions):
        differences.append(
            "positions.symbols: "
            f"expected={sorted(expected_positions)} actual={sorted(actual_positions)}"
        )

    for symbol in sorted(set(expected_positions) & set(actual_positions)):
        expected_position = expected_positions[symbol]
        actual_position = actual_positions[symbol]
        for field_name in (
            "quantity",
            "entry_price",
            "mark_price",
            "market_value_usd",
            "unrealized_pnl_usd",
        ):
            _float_difference(
                f"positions[{symbol}].{field_name}",
                getattr(expected_position, field_name),
                getattr(actual_position, field_name),
                differences,
            )

    return differences


def reconcile_forward_paper_runtime(
    *,
    status: ForwardPaperRuntimeStatus,
    paths: ForwardPaperRuntimePaths,
    reconciled_at: datetime,
    require_local_match: bool = True,
    recovered_session_id: str | None = None,
    recovery_note: str | None = None,
) -> tuple[
    ForwardPaperRuntimeStatus,
    ForwardPaperRuntimeAccountState,
    ForwardPaperReconciliationReport,
    ForwardPaperRecoveryStatus,
]:
    session_summaries = load_forward_paper_session_summaries(paths.sessions_dir)
    executed_sessions = [
        session
        for session in session_summaries
        if session.status == "completed" and session.session_outcome == "executed"
    ]
    expected_account_state = build_runtime_account_state(
        runtime_id=status.runtime_id,
        starting_equity_usd=status.starting_equity_usd,
        session_summaries=session_summaries,
        updated_at=reconciled_at,
    )
    local_account_state = load_runtime_account_state(paths.account_state_path)
    differences = []
    if require_local_match and local_account_state is not None:
        differences = _diff_account_states(expected_account_state, local_account_state)
    report_local_account_state = (
        local_account_state if require_local_match else expected_account_state
    )
    report_local_account_state_present = (
        local_account_state is not None if require_local_match else True
    )
    report = ForwardPaperReconciliationReport(
        runtime_id=status.runtime_id,
        reconciled_at=reconciled_at,
        status="mismatch" if differences else "clean",
        message=(
            "runtime_account_state_mismatch"
            if differences
            else "rebuilt_missing_account_state"
            if require_local_match and local_account_state is None and executed_sessions
            else None
        ),
        checked_session_count=len(session_summaries),
        executed_session_count=len(executed_sessions),
        last_completed_session_id=expected_account_state.as_of_session_id,
        last_completed_run_id=expected_account_state.as_of_run_id,
        local_account_state_present=report_local_account_state_present,
        expected_account_state=expected_account_state,
        local_account_state=report_local_account_state,
        differences=differences,
    )
    write_reconciliation_report(paths.reconciliation_report_path, report)

    if differences:
        recovery_status = ForwardPaperRecoveryStatus(
            runtime_id=status.runtime_id,
            checked_at=reconciled_at,
            status="blocked_mismatch",
            reconciliation_status="mismatch",
            recovered_session_id=recovered_session_id,
            recovery_note=recovery_note,
            account_state_path=paths.account_state_path,
            reconciliation_report_path=paths.reconciliation_report_path,
        )
        write_recovery_status(paths.recovery_status_path, recovery_status)
        updated_status = status.model_copy(
            update={
                "reconciliation_status": "mismatch",
                "mismatch_detected": True,
                "last_reconciled_session_id": expected_account_state.as_of_session_id,
                "last_reconciliation_at": reconciled_at,
                "updated_at": reconciled_at,
            }
        )
        return updated_status, expected_account_state, report, recovery_status

    write_runtime_account_state(paths.account_state_path, expected_account_state)
    recovery_status = ForwardPaperRecoveryStatus(
        runtime_id=status.runtime_id,
        checked_at=reconciled_at,
        status="recovered" if recovered_session_id is not None else "clean",
        reconciliation_status="clean",
        recovered_session_id=recovered_session_id,
        recovery_note=recovery_note,
        account_state_path=paths.account_state_path,
        reconciliation_report_path=paths.reconciliation_report_path,
    )
    write_recovery_status(paths.recovery_status_path, recovery_status)
    updated_status = status.model_copy(
        update={
            "reconciliation_status": "clean",
            "mismatch_detected": False,
            "last_reconciled_session_id": expected_account_state.as_of_session_id,
            "last_reconciliation_at": reconciled_at,
            "updated_at": reconciled_at,
        }
    )
    return updated_status, expected_account_state, report, recovery_status
