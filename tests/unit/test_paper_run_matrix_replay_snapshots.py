from __future__ import annotations

import json
from collections import Counter
from math import fsum
from pathlib import Path

from crypto_agent.cli.matrix import run_paper_replay_matrix
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


def _paper_settings_for(tmp_path: Path):
    settings = load_settings(Path("config/paper.yaml"))
    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "runs_dir": tmp_path / "runs",
                    "journals_dir": tmp_path / "journals",
                }
            )
        }
    )


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    return json.loads((SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8"))


def _normalize_journal_path(journal_path: str, *, run_id: str) -> str:
    return f"journals/{run_id}.jsonl"


def _build_matrix_replay_payload(manifest_payload: dict[str, object]) -> dict[str, object]:
    runs: list[dict[str, object]] = []
    total_fill_notionals: list[float] = []
    total_fees: list[float] = []
    max_slippages: list[float] = []
    aggregate_totals = {
        "event_count": 0,
        "proposal_count": 0,
        "approval_count": 0,
        "denial_count": 0,
        "halt_count": 0,
        "order_intent_count": 0,
        "orders_submitted_count": 0,
        "order_reject_count": 0,
        "fill_event_count": 0,
        "filled_intent_count": 0,
        "partial_fill_intent_count": 0,
        "complete_execution_count": 0,
        "incomplete_execution_count": 0,
        "alert_count": 0,
        "kill_switch_activations": 0,
        "total_fill_notional_usd": 0.0,
        "total_fee_usd": 0.0,
        "max_slippage_bps": 0.0,
        "empty_replay_scorecard_count": 0,
    }
    aggregate_pnl = {
        "starting_equity_usd": 0.0,
        "gross_realized_pnl_usd": 0.0,
        "total_fee_usd": 0.0,
        "net_realized_pnl_usd": 0.0,
        "ending_unrealized_pnl_usd": 0.0,
        "ending_equity_usd": 0.0,
        "return_fraction": 0.0,
    }

    for raw_entry in manifest_payload["entries"]:
        entry = dict(raw_entry)
        journal_path = Path(str(entry["journal_path"]))
        summary_path = Path(str(entry["summary_path"]))
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        replay_result = replay_journal(
            journal_path,
            replay_path=str(summary["replay_path"]),
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        scorecard = replay_result.scorecard.model_dump(mode="json")
        pnl = replay_result.pnl.model_dump(mode="json") if replay_result.pnl is not None else None
        event_type_counts = Counter(event.event_type.value for event in replay_result.events)

        runs.append(
            {
                "fixture": entry["fixture"],
                "manifest_run_id": entry["run_id"],
                "replay_run_id": scorecard["run_id"],
                "journal_path": _normalize_journal_path(
                    str(entry["journal_path"]),
                    run_id=str(entry["run_id"]),
                ),
                "replay_scorecard": scorecard,
                "replay_pnl": pnl,
                "alert_count": event_type_counts["alert.raised"],
                "kill_switch_activations": event_type_counts["kill_switch.activated"],
            }
        )

        aggregate_totals["event_count"] += int(scorecard["event_count"])
        aggregate_totals["proposal_count"] += int(scorecard["proposal_count"])
        aggregate_totals["approval_count"] += int(scorecard["approval_count"])
        aggregate_totals["denial_count"] += int(scorecard["denial_count"])
        aggregate_totals["halt_count"] += int(scorecard["halt_count"])
        aggregate_totals["order_intent_count"] += int(scorecard["order_intent_count"])
        aggregate_totals["orders_submitted_count"] += int(scorecard["orders_submitted_count"])
        aggregate_totals["order_reject_count"] += int(scorecard["order_reject_count"])
        aggregate_totals["fill_event_count"] += int(scorecard["fill_event_count"])
        aggregate_totals["filled_intent_count"] += int(scorecard["filled_intent_count"])
        aggregate_totals["partial_fill_intent_count"] += int(scorecard["partial_fill_intent_count"])
        aggregate_totals["complete_execution_count"] += int(scorecard["complete_execution_count"])
        aggregate_totals["incomplete_execution_count"] += int(
            scorecard["incomplete_execution_count"]
        )
        aggregate_totals["alert_count"] += int(event_type_counts["alert.raised"])
        aggregate_totals["kill_switch_activations"] += int(
            event_type_counts["kill_switch.activated"]
        )
        total_fill_notionals.append(float(scorecard["total_fill_notional_usd"]))
        total_fees.append(float(scorecard["total_fee_usd"]))
        max_slippages.append(float(scorecard["max_slippage_bps"]))
        if str(scorecard["run_id"]) == "empty":
            aggregate_totals["empty_replay_scorecard_count"] += 1

        aggregate_totals["total_fill_notional_usd"] = fsum(total_fill_notionals)
    aggregate_totals["total_fee_usd"] = fsum(total_fees)
    aggregate_totals["max_slippage_bps"] = max(max_slippages, default=0.0)
    for run in runs:
        pnl = run["replay_pnl"]
        assert pnl is not None
        aggregate_pnl["starting_equity_usd"] += float(pnl["starting_equity_usd"])
        aggregate_pnl["gross_realized_pnl_usd"] += float(pnl["gross_realized_pnl_usd"])
        aggregate_pnl["total_fee_usd"] += float(pnl["total_fee_usd"])
        aggregate_pnl["net_realized_pnl_usd"] += float(pnl["net_realized_pnl_usd"])
        aggregate_pnl["ending_unrealized_pnl_usd"] += float(pnl["ending_unrealized_pnl_usd"])
        aggregate_pnl["ending_equity_usd"] += float(pnl["ending_equity_usd"])
    if aggregate_pnl["starting_equity_usd"] > 0:
        aggregate_pnl["return_fraction"] = (
            aggregate_pnl["ending_equity_usd"] - aggregate_pnl["starting_equity_usd"]
        ) / aggregate_pnl["starting_equity_usd"]

    return {
        "matrix_run_id": manifest_payload["matrix_run_id"],
        "entry_count": manifest_payload["entry_count"],
        "runs": runs,
        "aggregate_totals": aggregate_totals,
        "aggregate_pnl": aggregate_pnl,
    }


def test_matrix_manifest_replay_aggregate_snapshot_and_reconciliation(tmp_path: Path) -> None:
    manifest = run_paper_replay_matrix(
        settings=_paper_settings_for(tmp_path),
        matrix_run_id="paper-run-matrix-demo",
    )
    manifest_payload = json.loads(Path(manifest.manifest_path).read_text(encoding="utf-8"))
    replay_payload = _build_matrix_replay_payload(manifest_payload)

    assert replay_payload == _load_snapshot(
        "paper_run_matrix_default.replay_aggregate.snapshot.json"
    )

    runs_by_manifest_run_id = {run["manifest_run_id"]: run for run in replay_payload["runs"]}
    for entry in manifest_payload["entries"]:
        run = runs_by_manifest_run_id[str(entry["run_id"])]
        scorecard = run["replay_scorecard"]

        assert run["fixture"] == entry["fixture"]
        assert run["journal_path"] == f"journals/{entry['run_id']}.jsonl"
        assert int(entry["outcome_counts"]["event_count"]) == int(scorecard["event_count"])
        assert int(entry["outcome_counts"]["proposal_count"]) == int(scorecard["proposal_count"])
        assert int(entry["outcome_counts"]["approval_count"]) == int(scorecard["approval_count"])
        assert int(entry["outcome_counts"]["denial_count"]) == int(scorecard["denial_count"])
        assert int(entry["outcome_counts"]["halt_count"]) == int(scorecard["halt_count"])
        assert int(entry["outcome_counts"]["order_reject_count"]) == int(
            scorecard["order_reject_count"]
        )
        assert int(entry["outcome_counts"]["fill_event_count"]) == int(
            scorecard["fill_event_count"]
        )
        assert int(entry["outcome_counts"]["partial_fill_intent_count"]) == int(
            scorecard["partial_fill_intent_count"]
        )
        assert int(entry["outcome_counts"]["alert_count"]) == int(run["alert_count"])
