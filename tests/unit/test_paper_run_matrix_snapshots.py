from __future__ import annotations

import json
from pathlib import Path

from crypto_agent.cli.matrix import run_paper_replay_matrix
from crypto_agent.config import load_settings

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


def _normalize_manifest(manifest: dict[str, object]) -> dict[str, object]:
    normalized = dict(manifest)
    matrix_run_id = str(normalized["matrix_run_id"])
    normalized["manifest_path"] = f"runs/{matrix_run_id}/manifest.json"
    normalized["matrix_comparison_path"] = f"runs/{matrix_run_id}/matrix_comparison.json"
    normalized["matrix_trade_ledger_path"] = f"runs/{matrix_run_id}/matrix_trade_ledger.json"
    normalized_entries: list[dict[str, object]] = []
    for raw_entry in manifest["entries"]:
        entry = dict(raw_entry)
        run_id = str(entry["run_id"])
        entry["journal_path"] = f"journals/{run_id}.jsonl"
        entry["summary_path"] = f"runs/{run_id}/summary.json"
        normalized_entries.append(entry)
    normalized["entries"] = normalized_entries
    return normalized


def test_matrix_manifest_snapshot_and_consistency(tmp_path: Path) -> None:
    manifest = run_paper_replay_matrix(
        settings=_paper_settings_for(tmp_path),
        matrix_run_id="paper-run-matrix-demo",
    )

    manifest_path = Path(manifest.manifest_path)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert manifest_path.exists()
    assert _normalize_manifest(manifest_payload) == _load_snapshot(
        "paper_run_matrix_default.manifest.snapshot.json"
    )

    aggregate_counts = {
        "event_count": 0,
        "proposal_count": 0,
        "approval_count": 0,
        "denial_count": 0,
        "halt_count": 0,
        "order_reject_count": 0,
        "fill_event_count": 0,
        "partial_fill_intent_count": 0,
        "alert_count": 0,
    }

    for entry in manifest.entries:
        journal_path = Path(entry.journal_path)
        summary_path = Path(entry.summary_path)
        summary = json.loads(summary_path.read_text(encoding="utf-8"))

        assert journal_path.exists()
        assert summary_path.exists()
        assert entry.journal_path == str(journal_path)
        assert entry.summary_path == str(summary_path)
        assert entry.run_id == str(summary["run_id"])
        assert entry.fixture == Path(str(summary["replay_path"])).name
        assert entry.outcome_counts["event_count"] == int(summary["scorecard"]["event_count"])
        assert entry.outcome_counts["proposal_count"] == int(summary["scorecard"]["proposal_count"])
        assert entry.outcome_counts["approval_count"] == int(summary["scorecard"]["approval_count"])
        assert entry.outcome_counts["denial_count"] == int(summary["scorecard"]["denial_count"])
        assert entry.outcome_counts["halt_count"] == int(summary["scorecard"]["halt_count"])
        assert entry.outcome_counts["order_reject_count"] == int(
            summary["scorecard"]["order_reject_count"]
        )
        assert entry.outcome_counts["fill_event_count"] == int(
            summary["scorecard"]["fill_event_count"]
        )
        assert entry.outcome_counts["partial_fill_intent_count"] == int(
            summary["scorecard"]["partial_fill_intent_count"]
        )
        assert entry.outcome_counts["alert_count"] == int(
            summary["operator_summary"]["alert_count"]
        )

        for key in aggregate_counts:
            aggregate_counts[key] += entry.outcome_counts[key]

    assert manifest.aggregate_counts == aggregate_counts
