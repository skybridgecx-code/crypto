from __future__ import annotations

import json
from pathlib import Path

import pytest
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


def test_matrix_comparison_snapshot_and_reconciliation(tmp_path: Path) -> None:
    manifest = run_paper_replay_matrix(
        settings=_paper_settings_for(tmp_path),
        matrix_run_id="paper-run-matrix-demo",
    )

    manifest_payload = json.loads(Path(manifest.manifest_path).read_text(encoding="utf-8"))
    comparison_path = Path(manifest.matrix_comparison_path)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))

    assert comparison_path.exists()
    assert comparison == _load_snapshot("paper_run_matrix_default.comparison.snapshot.json")

    rows = comparison["rows"]
    aggregate = comparison["aggregate"]
    rankings = comparison["rankings"]
    expected_run_ids = [str(entry["run_id"]) for entry in manifest_payload["entries"]]
    assert [str(row["run_id"]) for row in rows] == expected_run_ids

    total_starting_equity_usd = 0.0
    total_net_realized_pnl_usd = 0.0
    total_ending_unrealized_pnl_usd = 0.0
    total_ending_equity_usd = 0.0
    total_proposal_count = 0
    total_halt_count = 0
    total_order_reject_count = 0
    total_fill_event_count = 0
    total_partial_fill_intent_count = 0
    total_alert_count = 0
    total_ledger_row_count = 0

    best_return_row: dict[str, object] | None = None
    worst_return_row: dict[str, object] | None = None
    highest_equity_row: dict[str, object] | None = None
    lowest_equity_row: dict[str, object] | None = None

    for row, raw_entry in zip(rows, manifest_payload["entries"], strict=True):
        entry = dict(raw_entry)
        summary = json.loads(Path(str(entry["summary_path"])).read_text(encoding="utf-8"))
        single_run_ledger = json.loads(
            Path(str(summary["trade_ledger_path"])).read_text(encoding="utf-8")
        )
        replay_result = replay_journal(
            str(entry["journal_path"]),
            replay_path=str(summary["replay_path"]),
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        replay_pnl = replay_result.pnl
        assert replay_pnl is not None

        assert row["run_id"] == entry["run_id"]
        assert row["fixture"] == entry["fixture"]
        assert row["proposal_count"] == entry["outcome_counts"]["proposal_count"]
        assert row["halt_count"] == entry["outcome_counts"]["halt_count"]
        assert row["order_reject_count"] == entry["outcome_counts"]["order_reject_count"]
        assert row["fill_event_count"] == entry["outcome_counts"]["fill_event_count"]
        assert (
            row["partial_fill_intent_count"] == entry["outcome_counts"]["partial_fill_intent_count"]
        )
        assert row["alert_count"] == entry["outcome_counts"]["alert_count"]
        assert row["ledger_row_count"] == single_run_ledger["row_count"]
        assert row["starting_equity_usd"] == pytest.approx(replay_pnl.starting_equity_usd)
        assert row["net_realized_pnl_usd"] == pytest.approx(replay_pnl.net_realized_pnl_usd)
        assert row["ending_unrealized_pnl_usd"] == pytest.approx(
            replay_pnl.ending_unrealized_pnl_usd
        )
        assert row["ending_equity_usd"] == pytest.approx(replay_pnl.ending_equity_usd)
        assert row["return_fraction"] == pytest.approx(replay_pnl.return_fraction)

        total_proposal_count += int(row["proposal_count"])
        total_halt_count += int(row["halt_count"])
        total_order_reject_count += int(row["order_reject_count"])
        total_fill_event_count += int(row["fill_event_count"])
        total_partial_fill_intent_count += int(row["partial_fill_intent_count"])
        total_alert_count += int(row["alert_count"])
        total_ledger_row_count += int(row["ledger_row_count"])
        total_starting_equity_usd += float(row["starting_equity_usd"])
        total_net_realized_pnl_usd += float(row["net_realized_pnl_usd"])
        total_ending_unrealized_pnl_usd += float(row["ending_unrealized_pnl_usd"])
        total_ending_equity_usd += float(row["ending_equity_usd"])

        if best_return_row is None or (
            float(row["return_fraction"]),
            str(row["run_id"]),
        ) > (
            float(best_return_row["return_fraction"]),
            str(best_return_row["run_id"]),
        ):
            best_return_row = row
        if worst_return_row is None or (
            float(row["return_fraction"]),
            str(row["run_id"]),
        ) < (
            float(worst_return_row["return_fraction"]),
            str(worst_return_row["run_id"]),
        ):
            worst_return_row = row
        if highest_equity_row is None or (
            float(row["ending_equity_usd"]),
            str(row["run_id"]),
        ) > (
            float(highest_equity_row["ending_equity_usd"]),
            str(highest_equity_row["run_id"]),
        ):
            highest_equity_row = row
        if lowest_equity_row is None or (
            float(row["ending_equity_usd"]),
            str(row["run_id"]),
        ) < (
            float(lowest_equity_row["ending_equity_usd"]),
            str(lowest_equity_row["run_id"]),
        ):
            lowest_equity_row = row

    assert aggregate["run_count"] == comparison["row_count"]
    assert aggregate["total_proposal_count"] == total_proposal_count
    assert aggregate["total_halt_count"] == total_halt_count
    assert aggregate["total_order_reject_count"] == total_order_reject_count
    assert aggregate["total_fill_event_count"] == total_fill_event_count
    assert aggregate["total_partial_fill_intent_count"] == total_partial_fill_intent_count
    assert aggregate["total_alert_count"] == total_alert_count
    assert aggregate["total_ledger_row_count"] == total_ledger_row_count
    assert aggregate["total_starting_equity_usd"] == pytest.approx(total_starting_equity_usd)
    assert aggregate["total_net_realized_pnl_usd"] == pytest.approx(total_net_realized_pnl_usd)
    assert aggregate["total_ending_unrealized_pnl_usd"] == pytest.approx(
        total_ending_unrealized_pnl_usd
    )
    assert aggregate["total_ending_equity_usd"] == pytest.approx(total_ending_equity_usd)

    expected_aggregate_return_fraction = (
        (total_ending_equity_usd - total_starting_equity_usd) / total_starting_equity_usd
        if total_starting_equity_usd > 0
        else 0.0
    )
    assert aggregate["aggregate_return_fraction"] == pytest.approx(
        expected_aggregate_return_fraction
    )

    assert rankings["best_return_run_id"] == best_return_row["run_id"]
    assert rankings["worst_return_run_id"] == worst_return_row["run_id"]
    assert rankings["highest_ending_equity_run_id"] == highest_equity_row["run_id"]
    assert rankings["lowest_ending_equity_run_id"] == lowest_equity_row["run_id"]
