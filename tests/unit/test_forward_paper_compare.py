from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

import pytest
from crypto_agent.cli.forward_paper_compare import main
from crypto_agent.evaluation.models import EvaluationScorecard, ReplayPnLSummary
from crypto_agent.runtime.models import ForwardPaperSessionSummary


def _session_time() -> datetime:
    return datetime(2026, 4, 22, 12, 0, tzinfo=UTC)


def _write_runtime_status(run_dir: Path, *, runtime_id: str) -> None:
    payload = {
        "runtime_id": runtime_id,
        "status": "idle",
        "control_status": "go",
        "control_block_reasons": [],
    }
    (run_dir / "forward_paper_status.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_session(
    run_dir: Path,
    *,
    runtime_id: str,
    session_number: int,
    proposal_count: int,
    event_count: int,
    execution_request_count: int,
    execution_terminal_count: int,
    control_action: Literal["go", "no_go", "manual_approval_required"] | None,
    control_reason_codes: list[str],
    net_realized_pnl_usd: float,
    include_advisory_marker: bool,
    decision_status_counts: dict[str, int] | None = None,
) -> None:
    session_id = f"session-{session_number:04d}"
    summary_path = run_dir / f"{session_id}-summary.json"
    summary_payload: dict[str, object] = {"run_id": f"{runtime_id}-{session_id}"}
    if include_advisory_marker:
        summary_payload["external_confirmation"] = {
            "artifact_path": str(run_dir / "external_confirmation.json"),
            "artifact_loaded": True,
            "source_system": "omega_fusion_engine",
            "asset": "BTCUSDT",
            "decision_count": sum((decision_status_counts or {}).values()),
            "decision_status_counts": decision_status_counts or {},
        }
    summary_path.write_text(
        json.dumps(summary_payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    session = ForwardPaperSessionSummary(
        runtime_id=runtime_id,
        session_id=session_id,
        session_number=session_number,
        status="completed",
        session_outcome="executed",
        scheduled_at=_session_time(),
        started_at=_session_time(),
        completed_at=_session_time(),
        run_id=f"{runtime_id}-{session_id}",
        summary_path=summary_path,
        control_action=control_action,
        control_reason_codes=control_reason_codes,
        execution_request_count=execution_request_count,
        execution_terminal_count=execution_terminal_count,
        scorecard=EvaluationScorecard(
            run_id=f"{runtime_id}-{session_id}",
            event_count=event_count,
            proposal_count=proposal_count,
        ),
        pnl=ReplayPnLSummary(
            starting_equity_usd=100000.0,
            net_realized_pnl_usd=net_realized_pnl_usd,
            ending_equity_usd=100000.0 + net_realized_pnl_usd,
            total_fee_usd=2.0,
            return_fraction=net_realized_pnl_usd / 100000.0,
        ),
    )
    sessions_dir = run_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    (sessions_dir / f"{session_id}.json").write_text(
        json.dumps(session.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def test_forward_paper_compare_writes_markdown_and_json(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    advisory_run_id = "omega-advisory-btcusdt-us"
    control_run_id = "omega-control-btcusdt-us"
    advisory_dir = runs_dir / advisory_run_id
    control_dir = runs_dir / control_run_id
    advisory_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    _write_runtime_status(advisory_dir, runtime_id=advisory_run_id)
    _write_runtime_status(control_dir, runtime_id=control_run_id)

    _write_session(
        advisory_dir,
        runtime_id=advisory_run_id,
        session_number=1,
        proposal_count=2,
        event_count=10,
        execution_request_count=2,
        execution_terminal_count=2,
        control_action="go",
        control_reason_codes=[],
        net_realized_pnl_usd=12.5,
        include_advisory_marker=True,
        decision_status_counts={"boosted_confirmation": 2},
    )
    _write_session(
        control_dir,
        runtime_id=control_run_id,
        session_number=1,
        proposal_count=1,
        event_count=7,
        execution_request_count=1,
        execution_terminal_count=1,
        control_action="go",
        control_reason_codes=[],
        net_realized_pnl_usd=4.5,
        include_advisory_marker=False,
    )

    assert (
        main(
            [
                "--advisory-run-id",
                advisory_run_id,
                "--control-run-id",
                control_run_id,
                "--runs-dir",
                str(runs_dir),
            ]
        )
        == 0
    )

    output_dir = runs_dir / "comparisons"
    json_path = (
        output_dir
        / f"{advisory_run_id}_vs_{control_run_id}.forward_paper_comparison.json"
    )
    report_path = (
        output_dir / f"{advisory_run_id}_vs_{control_run_id}.forward_paper_comparison.md"
    )
    assert json_path.exists()
    assert report_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["comparison_kind"] == "forward_paper_advisory_control_comparison_v1"
    assert payload["advisory_run"]["proposal_count"] == 2
    assert payload["control_run"]["proposal_count"] == 1
    assert payload["advisory_run"]["event_count"] == 10
    assert payload["control_run"]["event_count"] == 7
    assert payload["advisory_run"]["execution_request_count"] == 2
    assert payload["control_run"]["execution_request_count"] == 1
    assert payload["advisory_run"]["execution_terminal_count"] == 2
    assert payload["control_run"]["execution_terminal_count"] == 1
    assert payload["advisory_run"]["advisory_decision_marker_presence"] == "present"
    assert payload["control_run"]["advisory_decision_marker_presence"] == "absent"
    assert payload["advisory_run"]["advisory_decision_status_counts"] == {
        "boosted_confirmation": 2
    }
    assert payload["control_run"]["advisory_decision_status_counts"] == {}
    assert payload["delta"]["proposal_count"] == 1
    assert payload["delta"]["event_count"] == 3
    assert payload["delta"]["execution_request_count"] == 1
    assert payload["delta"]["execution_terminal_count"] == 1
    assert payload["delta"]["net_realized_pnl_usd_total"] == pytest.approx(8.0)

    report = report_path.read_text(encoding="utf-8")
    assert "# Forward-Paper Advisory vs Control Comparison" in report
    assert "## Advisory Run" in report
    assert "## Control Run" in report
    assert "## Delta (Advisory - Control)" in report
    assert "advisory_markers: `present` (1/1 sessions)" in report
    assert "advisory_markers: `absent` (0/1 sessions)" in report


def test_forward_paper_compare_missing_runtime_is_deterministic_error(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="forward_paper_compare_missing_run_dir:",
    ):
        main(
            [
                "--advisory-run-id",
                "omega-advisory-btcusdt-us",
                "--control-run-id",
                "omega-control-btcusdt-us",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )


def test_forward_paper_compare_ignores_session_sibling_artifacts(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    advisory_run_id = "omega-advisory-btcusdt-us"
    control_run_id = "omega-control-btcusdt-us"
    advisory_dir = runs_dir / advisory_run_id
    control_dir = runs_dir / control_run_id
    advisory_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    _write_runtime_status(advisory_dir, runtime_id=advisory_run_id)
    _write_runtime_status(control_dir, runtime_id=control_run_id)

    _write_session(
        advisory_dir,
        runtime_id=advisory_run_id,
        session_number=1,
        proposal_count=2,
        event_count=10,
        execution_request_count=2,
        execution_terminal_count=2,
        control_action="go",
        control_reason_codes=[],
        net_realized_pnl_usd=12.5,
        include_advisory_marker=True,
        decision_status_counts={"boosted_confirmation": 2},
    )
    _write_session(
        control_dir,
        runtime_id=control_run_id,
        session_number=1,
        proposal_count=1,
        event_count=7,
        execution_request_count=1,
        execution_terminal_count=1,
        control_action="go",
        control_reason_codes=[],
        net_realized_pnl_usd=4.5,
        include_advisory_marker=False,
    )

    advisory_sessions_dir = advisory_dir / "sessions"
    (advisory_sessions_dir / "session-0001.control_decision.json").write_text(
        json.dumps({"artifact_kind": "control_decision"}),
        encoding="utf-8",
    )
    (advisory_sessions_dir / "session-0001.execution_status.json").write_text(
        json.dumps({"artifact_kind": "execution_status"}),
        encoding="utf-8",
    )
    (advisory_sessions_dir / "session-0001.execution_requests.json").write_text(
        json.dumps({"artifact_kind": "execution_requests"}),
        encoding="utf-8",
    )
    (advisory_sessions_dir / "session-0001.live_market_state.json").write_text(
        json.dumps({"artifact_kind": "live_market_state"}),
        encoding="utf-8",
    )

    assert (
        main(
            [
                "--advisory-run-id",
                advisory_run_id,
                "--control-run-id",
                control_run_id,
                "--runs-dir",
                str(runs_dir),
            ]
        )
        == 0
    )

    payload = json.loads(
        (
            runs_dir
            / "comparisons"
            / f"{advisory_run_id}_vs_{control_run_id}.forward_paper_comparison.json"
        ).read_text(encoding="utf-8")
    )
    assert payload["advisory_run"]["session_count"] == 1
    assert payload["advisory_run"]["proposal_count"] == 2
    assert payload["advisory_run"]["event_count"] == 10
