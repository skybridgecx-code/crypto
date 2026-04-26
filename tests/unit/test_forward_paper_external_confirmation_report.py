from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_agent.cli.forward_paper_external_confirmation_report import main


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_session_fixture(
    *,
    runs_dir: Path,
    journals_dir: Path,
    run_id: str,
    session_number: int,
    external_confirmation: dict[str, object] | None,
    pipeline: dict[str, object],
    scorecard: dict[str, object],
    journal_statuses: list[str],
) -> None:
    session_id = f"session-{session_number:04d}"
    runtime_session_path = runs_dir / run_id / "sessions" / f"{session_id}.json"
    summary_path = runs_dir / f"{run_id}-{session_id}" / "summary.json"
    journal_path = journals_dir / f"{run_id}-{session_id}.jsonl"
    session_payload = {
        "runtime_id": run_id,
        "session_id": session_id,
        "session_number": session_number,
        "run_id": f"{run_id}-{session_id}",
        "journal_path": str(journal_path),
        "summary_path": str(summary_path),
        "scorecard": scorecard,
    }
    _write_json(runtime_session_path, session_payload)

    summary_payload: dict[str, object] = {
        "run_id": f"{run_id}-{session_id}",
        "scorecard": scorecard,
    }
    if external_confirmation is not None:
        summary_payload["external_confirmation"] = external_confirmation
    _write_json(summary_path, summary_payload)

    _write_json(
        runs_dir / run_id / "sessions" / f"{session_id}.proposal_generation_summary.json",
        {
            "artifact_kind": "forward_paper_proposal_generation_summary_v1",
            "proposal_generation": {
                "artifact_kind": "proposal_generation_summary_v1",
                "proposal_pipeline": pipeline,
            },
        },
    )

    journal_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        json.dumps(
            {
                "event_type": "alert.raised",
                "payload": {
                    "decision_kind": "external_confirmation_decision_v1",
                    "status": status,
                },
                "source": "external_confirmation",
            },
            sort_keys=True,
        )
        for status in journal_statuses
    ]
    journal_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def test_forward_paper_external_confirmation_report_aggregates_bridge_impact(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    journals_dir = tmp_path / "journals"
    run_id = "poly-xrp-bridge-impact-policy-1"

    _write_session_fixture(
        runs_dir=runs_dir,
        journals_dir=journals_dir,
        run_id=run_id,
        session_number=1,
        external_confirmation={
            "artifact_loaded": True,
            "asset": "XRPUSD",
            "decision_count": 2,
            "decision_status_counts": {
                "boosted_confirmation": 1,
                "penalized_conflict": 1,
            },
            "impact_policy": "conservative",
            "source_system": "polymarket-arb",
        },
        pipeline={
            "dropped_by_external_confirmation_count": 1,
            "external_confirmation_impact_policy": "conservative",
        },
        scorecard={
            "proposal_count": 1,
            "orders_submitted_count": 1,
            "fill_event_count": 2,
        },
        journal_statuses=["boosted_confirmation", "penalized_conflict"],
    )
    _write_session_fixture(
        runs_dir=runs_dir,
        journals_dir=journals_dir,
        run_id=run_id,
        session_number=2,
        external_confirmation={
            "artifact_loaded": True,
            "asset": "XRPUSD",
            "decision_count": 2,
            "decision_status_counts": {
                "ignored_asset_mismatch": 1,
                "vetoed_neutral": 1,
            },
            "impact_policy": "conservative",
            "source_system": "polymarket-arb",
        },
        pipeline={
            "dropped_by_external_confirmation_count": 1,
            "external_confirmation_impact_policy": "conservative",
        },
        scorecard={
            "proposal_count": 0,
            "orders_submitted_count": 0,
            "fill_event_count": 0,
        },
        journal_statuses=["ignored_asset_mismatch", "vetoed_neutral"],
    )

    assert (
        main(
            [
                "--run-id",
                run_id,
                "--runs-dir",
                str(runs_dir),
                "--journals-dir",
                str(journals_dir),
            ]
        )
        == 0
    )

    output_dir = runs_dir / "external_confirmation_reports"
    json_path = output_dir / f"{run_id}.external_confirmation_impact.json"
    report_path = output_dir / f"{run_id}.external_confirmation_impact.md"
    assert json_path.exists()
    assert report_path.exists()

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "forward_paper_external_confirmation_impact_report_v1"
    run_payload = payload["run"]
    assert run_payload["run_id"] == run_id
    assert run_payload["session_count"] == 2
    assert run_payload["artifact_loaded_status"] == "loaded_all_sessions"
    assert run_payload["artifact_loaded_counts"] == {"loaded": 2}
    assert run_payload["source_system_counts"] == {"polymarket-arb": 2}
    assert run_payload["asset_counts"] == {"XRPUSD": 2}
    assert run_payload["external_confirmation_impact_policy_counts"] == {"conservative": 2}
    assert run_payload["decision_status_counts"] == {
        "boosted_confirmation": 1,
        "ignored_asset_mismatch": 1,
        "penalized_conflict": 1,
        "vetoed_conflict": 0,
        "vetoed_neutral": 1,
    }
    assert run_payload["journal_decision_status_counts"] == run_payload["decision_status_counts"]
    assert run_payload["totals"] == {
        "dropped_by_external_confirmation_count": 2,
        "fill_event_count": 2,
        "orders_submitted_count": 1,
        "proposal_count": 1,
    }
    assert [entry["session_id"] for entry in run_payload["sessions"]] == [
        "session-0001",
        "session-0002",
    ]
    assert run_payload["sessions"][0]["dropped_by_external_confirmation_count"] == 1
    assert run_payload["sessions"][0]["orders_submitted_count"] == 1

    report = report_path.read_text(encoding="utf-8")
    assert "# Forward-Paper External Confirmation Impact Report" in report
    assert f"- run_id: `{run_id}`" in report
    assert "penalized_conflict:1" in report
    assert "dropped_by_external_confirmation_count: 2" in report


def test_forward_paper_external_confirmation_report_handles_absent_markers(
    tmp_path: Path,
) -> None:
    runs_dir = tmp_path / "runs"
    journals_dir = tmp_path / "journals"
    run_id = "coinbase-xrp-control-no-advisory"

    _write_session_fixture(
        runs_dir=runs_dir,
        journals_dir=journals_dir,
        run_id=run_id,
        session_number=1,
        external_confirmation=None,
        pipeline={"dropped_by_external_confirmation_count": 0},
        scorecard={
            "proposal_count": 1,
            "orders_submitted_count": 1,
            "fill_event_count": 2,
        },
        journal_statuses=[],
    )

    assert main(["--run-id", run_id, "--runs-dir", str(runs_dir)]) == 0

    payload = json.loads(
        (
            runs_dir
            / "external_confirmation_reports"
            / f"{run_id}.external_confirmation_impact.json"
        ).read_text(encoding="utf-8")
    )
    run_payload = payload["run"]
    assert run_payload["artifact_loaded_status"] == "absent"
    assert run_payload["artifact_loaded_counts"] == {"missing": 1}
    assert run_payload["decision_status_counts"] == {
        "boosted_confirmation": 0,
        "ignored_asset_mismatch": 0,
        "penalized_conflict": 0,
        "vetoed_conflict": 0,
        "vetoed_neutral": 0,
    }
    assert run_payload["totals"]["proposal_count"] == 1
    assert run_payload["sessions"][0]["external_confirmation_impact_policy"] is None


def test_forward_paper_external_confirmation_report_missing_run_is_deterministic_error(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="forward_paper_external_confirmation_missing_run_dir:"):
        main(
            [
                "--run-id",
                "poly-xrp-bridge-impact-policy-1",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
