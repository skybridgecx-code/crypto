from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.forward_paper_proposal_generation_report import main


def _write_session_proposal_summary(
    run_dir: Path,
    *,
    session_number: int,
    breakout_non_emit_reason: str,
    mean_reversion_non_emit_reason: str,
    blocked_reason_counts: dict[str, int],
    dropped_external_count: int = 0,
    breakout_emitted: int = 0,
    mean_reversion_emitted: int = 0,
    allowed_count: int = 0,
) -> None:
    session_id = f"session-{session_number:04d}"
    sessions_dir = run_dir / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    path = sessions_dir / f"{session_id}.proposal_generation_summary.json"
    payload = {
        "artifact_kind": "forward_paper_proposal_generation_summary_v1",
        "session_id": session_id,
        "run_id": f"{run_dir.name}-{session_id}",
        "proposal_generation": {
            "artifact_kind": "proposal_generation_summary_v1",
            "run_id": f"{run_dir.name}-{session_id}",
            "replay_path": str(sessions_dir / f"{session_id}.live_input.jsonl"),
            "candle_count": 8,
            "breakout": {
                "strategy_id": "breakout_v1",
                "required_lookback_candles": 4,
                "considered_window_count": 5,
                "insufficient_lookback_count": 3,
                "emitted_proposal_count": breakout_emitted,
                "emitted_side_counts": {"buy": breakout_emitted} if breakout_emitted > 0 else {},
                "non_emit_reason_counts": {breakout_non_emit_reason: max(0, 5 - breakout_emitted)},
                "last_outcome_status": "not_emitted",
                "last_outcome_reason": breakout_non_emit_reason,
            },
            "mean_reversion": {
                "strategy_id": "mean_reversion_v1",
                "required_lookback_candles": 5,
                "considered_window_count": 4,
                "insufficient_lookback_count": 4,
                "emitted_proposal_count": mean_reversion_emitted,
                "emitted_side_counts": (
                    {"sell": mean_reversion_emitted} if mean_reversion_emitted > 0 else {}
                ),
                "non_emit_reason_counts": {
                    mean_reversion_non_emit_reason: max(0, 4 - mean_reversion_emitted)
                },
                "last_outcome_status": "not_emitted",
                "last_outcome_reason": mean_reversion_non_emit_reason,
            },
            "proposal_pipeline": {
                "emitted_proposal_count": breakout_emitted + mean_reversion_emitted,
                "dropped_by_external_confirmation_count": dropped_external_count,
                "blocked_by_risk_or_policy_count": sum(blocked_reason_counts.values()),
                "blocked_reason_counts": blocked_reason_counts,
                "allowed_for_execution_count": allowed_count,
            },
        },
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_forward_paper_proposal_generation_report_aggregates_counts(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    run_id = "omega-btc-evidence-4-btcusdt-advisory"
    run_dir = runs_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    _write_session_proposal_summary(
        run_dir,
        session_number=2,
        breakout_non_emit_reason="regime_not_trend",
        mean_reversion_non_emit_reason="regime_not_range",
        blocked_reason_counts={"max_open_positions_reached": 1},
        dropped_external_count=0,
        breakout_emitted=0,
        mean_reversion_emitted=0,
        allowed_count=0,
    )
    _write_session_proposal_summary(
        run_dir,
        session_number=1,
        breakout_non_emit_reason="regime_not_trend",
        mean_reversion_non_emit_reason="zscore_below_entry_threshold",
        blocked_reason_counts={"max_open_positions_reached": 1, "symbol_not_allowed": 2},
        dropped_external_count=1,
        breakout_emitted=1,
        mean_reversion_emitted=0,
        allowed_count=1,
    )
    # sibling artifact should be ignored by strict filename rule
    (run_dir / "sessions" / "session-0001.execution_status.json").write_text(
        json.dumps({"artifact_kind": "execution_status"}), encoding="utf-8"
    )

    assert main(["--run-id", run_id, "--runs-dir", str(runs_dir)]) == 0

    output_dir = runs_dir / "proposal_generation_reports"
    base_name = run_id
    json_path = output_dir / f"{base_name}.proposal_generation_aggregate.json"
    report_path = output_dir / f"{base_name}.proposal_generation_aggregate.md"
    assert json_path.exists()
    assert report_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "forward_paper_proposal_generation_aggregate_v1"
    assert payload["run_count"] == 1
    run_payload = payload["runs"][0]
    assert run_payload["run_id"] == run_id
    assert run_payload["session_count"] == 2

    breakout = run_payload["strategy_aggregates"]["breakout"]
    assert breakout["total_considered_window_count"] == 10
    assert breakout["total_insufficient_lookback_count"] == 6
    assert breakout["total_emitted_proposal_count"] == 1
    assert breakout["emitted_side_counts"] == {"buy": 1}
    assert breakout["non_emit_reason_counts"] == {"regime_not_trend": 9}
    assert [entry["session_id"] for entry in breakout["session_last_outcomes"]] == [
        "session-0001",
        "session-0002",
    ]

    mean_reversion = run_payload["strategy_aggregates"]["mean_reversion"]
    assert mean_reversion["total_considered_window_count"] == 8
    assert mean_reversion["total_insufficient_lookback_count"] == 8
    assert mean_reversion["non_emit_reason_counts"] == {
        "regime_not_range": 4,
        "zscore_below_entry_threshold": 4,
    }

    pipeline = run_payload["pipeline_aggregate"]
    assert pipeline["emitted_proposal_count"] == 1
    assert pipeline["dropped_by_external_confirmation_count"] == 1
    assert pipeline["blocked_by_risk_or_policy_count"] == 4
    assert pipeline["blocked_reason_counts"] == {
        "max_open_positions_reached": 2,
        "symbol_not_allowed": 2,
    }
    assert pipeline["allowed_for_execution_count"] == 1

    report = report_path.read_text(encoding="utf-8")
    assert "# Forward-Paper Proposal-Generation Aggregate Report" in report
    assert f"## {run_id}" in report
    assert "### Breakout" in report
    assert "### Mean Reversion" in report
    assert "### Pipeline" in report


def test_forward_paper_proposal_generation_report_supports_multiple_run_ids(tmp_path: Path) -> None:
    runs_dir = tmp_path / "runs"
    advisory_id = "omega-btc-evidence-4-btcusdt-advisory"
    control_id = "omega-btc-evidence-4-btcusdt-control"

    advisory_dir = runs_dir / advisory_id
    control_dir = runs_dir / control_id
    advisory_dir.mkdir(parents=True, exist_ok=True)
    control_dir.mkdir(parents=True, exist_ok=True)

    _write_session_proposal_summary(
        advisory_dir,
        session_number=1,
        breakout_non_emit_reason="regime_not_trend",
        mean_reversion_non_emit_reason="regime_not_range",
        blocked_reason_counts={},
    )
    _write_session_proposal_summary(
        control_dir,
        session_number=1,
        breakout_non_emit_reason="regime_not_trend",
        mean_reversion_non_emit_reason="regime_not_range",
        blocked_reason_counts={},
    )

    assert (
        main(
            [
                "--run-id",
                advisory_id,
                "--run-id",
                control_id,
                "--runs-dir",
                str(runs_dir),
            ]
        )
        == 0
    )

    output_dir = runs_dir / "proposal_generation_reports"
    base_name = f"{advisory_id}__{control_id}"
    json_path = output_dir / f"{base_name}.proposal_generation_aggregate.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["run_count"] == 2
    assert [entry["run_id"] for entry in payload["runs"]] == [advisory_id, control_id]


def test_forward_paper_proposal_generation_report_missing_run_is_deterministic_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="forward_paper_proposal_generation_missing_run_dir:"):
        main(
            [
                "--run-id",
                "omega-btc-evidence-4-btcusdt-advisory",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
