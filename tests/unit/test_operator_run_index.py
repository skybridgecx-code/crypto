from __future__ import annotations

import json
from pathlib import Path

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.cli.matrix import run_paper_replay_matrix
from crypto_agent.config import load_settings
from crypto_agent.evaluation.models import OperatorRunIndex

FIXTURES_DIR = Path("tests/fixtures")


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


def test_run_paper_replay_writes_top_level_operator_run_index(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="direct-breakout-paper-run",
    )

    index_path = settings.paths.runs_dir / "operator_run_index.json"
    index = OperatorRunIndex.model_validate(json.loads(index_path.read_text(encoding="utf-8")))

    assert index_path.exists()
    assert index.index_path == str(index_path)
    assert index.single_run_count == 1
    assert index.matrix_run_count == 0
    assert not index.matrix_runs

    entry = index.single_runs[0]
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))

    assert entry.artifact_type == "single_run"
    assert entry.order == 0
    assert entry.run_id == "direct-breakout-paper-run"
    assert entry.journal_path == str(result.journal_path)
    assert entry.summary_path == str(result.summary_path)
    assert entry.report_path == str(result.report_path)
    assert entry.trade_ledger_path == str(result.trade_ledger_path)
    assert entry.paths_exist == {
        "journal_path": True,
        "summary_path": True,
        "report_path": True,
        "trade_ledger_path": True,
    }
    assert entry.all_paths_exist is True
    assert summary["run_id"] == entry.run_id
    assert summary["journal_path"] == entry.journal_path
    assert summary["trade_ledger_path"] == entry.trade_ledger_path


def test_matrix_run_updates_operator_run_index_and_reconciles_existing_artifacts(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    direct_result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_mean_reversion_short.jsonl",
        settings=settings,
        run_id="direct-mean-reversion-paper-run",
    )
    manifest = run_paper_replay_matrix(
        settings=settings,
        matrix_run_id="paper-run-matrix-demo",
    )

    index_path = settings.paths.runs_dir / "operator_run_index.json"
    index = OperatorRunIndex.model_validate(json.loads(index_path.read_text(encoding="utf-8")))

    single_run_ids = [entry.run_id for entry in index.single_runs]
    matrix_run_ids = [entry.matrix_run_id for entry in index.matrix_runs]

    assert index_path.exists()
    assert index.single_run_count == 6
    assert index.matrix_run_count == 1
    assert single_run_ids == sorted(single_run_ids)
    assert matrix_run_ids == ["paper-run-matrix-demo"]
    assert index.single_runs[0].order == 0
    assert index.single_runs[-1].order == 5
    assert index.matrix_runs[0].order == 0

    direct_entry = next(
        entry for entry in index.single_runs if entry.run_id == direct_result.run_id
    )
    direct_summary = json.loads(Path(direct_entry.summary_path).read_text(encoding="utf-8"))
    assert direct_entry.paths_exist == {
        "journal_path": True,
        "summary_path": True,
        "report_path": True,
        "trade_ledger_path": True,
    }
    assert direct_summary["run_id"] == direct_entry.run_id
    assert direct_summary["journal_path"] == direct_entry.journal_path

    for entry in index.single_runs:
        summary = json.loads(Path(entry.summary_path).read_text(encoding="utf-8"))
        assert entry.artifact_type == "single_run"
        assert entry.all_paths_exist is True
        assert summary["run_id"] == entry.run_id
        assert summary["journal_path"] == entry.journal_path
        assert summary["trade_ledger_path"] == entry.trade_ledger_path

    matrix_entry = index.matrix_runs[0]
    manifest_payload = json.loads(Path(matrix_entry.manifest_path).read_text(encoding="utf-8"))

    assert matrix_entry.artifact_type == "matrix_run"
    assert matrix_entry.matrix_run_id == manifest.matrix_run_id
    assert matrix_entry.manifest_path == manifest.manifest_path
    assert matrix_entry.matrix_comparison_path == manifest.matrix_comparison_path
    assert matrix_entry.matrix_trade_ledger_path == manifest.matrix_trade_ledger_path
    assert matrix_entry.report_path == str(Path(manifest.manifest_path).with_name("report.md"))
    assert matrix_entry.paths_exist == {
        "manifest_path": True,
        "report_path": True,
        "matrix_trade_ledger_path": True,
        "matrix_comparison_path": True,
    }
    assert matrix_entry.all_paths_exist is True
    assert manifest_payload["matrix_run_id"] == matrix_entry.matrix_run_id
    assert manifest_payload["manifest_path"] == matrix_entry.manifest_path
    assert manifest_payload["matrix_comparison_path"] == matrix_entry.matrix_comparison_path
    assert manifest_payload["matrix_trade_ledger_path"] == matrix_entry.matrix_trade_ledger_path
