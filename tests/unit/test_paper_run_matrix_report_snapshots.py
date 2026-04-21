from __future__ import annotations

import json
from collections import Counter
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


def _load_report_snapshot(snapshot_name: str) -> str:
    return (SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8")


def _section_key_values(report: str, heading: str) -> dict[str, str]:
    lines = report.splitlines()
    start_index = lines.index(heading) + 1
    values: dict[str, str] = {}
    for line in lines[start_index:]:
        if line.startswith("## "):
            break
        if not line.strip():
            continue
        key, value = line.split(": ", maxsplit=1)
        values[key] = value
    return values


def _run_sections(report: str) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    current_run_id: str | None = None
    current_values: dict[str, str] = {}

    for line in report.splitlines():
        if line.startswith("### run_id: "):
            if current_run_id is not None:
                sections[current_run_id] = current_values
            current_run_id = line.removeprefix("### run_id: ")
            current_values = {}
            continue
        if current_run_id is None or not line.strip() or line.startswith("## "):
            continue
        key, value = line.split(": ", maxsplit=1)
        current_values[key] = value

    if current_run_id is not None:
        sections[current_run_id] = current_values
    return sections


def _format_float(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def test_matrix_report_snapshot_and_reconciliation(tmp_path: Path) -> None:
    manifest = run_paper_replay_matrix(
        settings=_paper_settings_for(tmp_path),
        matrix_run_id="paper-run-matrix-demo",
    )
    manifest_payload = json.loads(Path(manifest.manifest_path).read_text(encoding="utf-8"))
    report_path = Path(manifest.manifest_path).with_name("report.md")
    report = report_path.read_text(encoding="utf-8")

    assert report_path.exists()
    assert report == _load_report_snapshot("paper_run_matrix_default.report.snapshot.md")

    aggregate_manifest = _section_key_values(report, "## Aggregate Manifest Counts")
    for key, value in manifest.aggregate_counts.items():
        assert aggregate_manifest[key] == str(value)
    aggregate_pnl = _section_key_values(report, "## Aggregate Replay PnL")
    assert float(aggregate_pnl["starting_equity_usd"]) > 0
    robustness = _section_key_values(report, "## Matrix Cost/Slippage Robustness Gate")
    assert robustness["baseline_robustness_verdict"] in {"pass", "fail"}
    assert robustness["robustness_verdict"] in {"pass", "fail"}
    assert robustness["first_fail_scenario_id"] in {
        "baseline",
        "cost_slippage_plus_5bps",
        "cost_slippage_plus_10bps",
        "None",
    }

    run_sections = _run_sections(report)
    expected_run_ids = [str(entry["run_id"]) for entry in manifest_payload["entries"]]
    assert list(run_sections.keys()) == expected_run_ids

    for entry in manifest_payload["entries"]:
        run_id = str(entry["run_id"])
        section = run_sections[run_id]
        summary = json.loads(Path(str(entry["summary_path"])).read_text(encoding="utf-8"))
        replay_result = replay_journal(
            str(entry["journal_path"]),
            replay_path=str(summary["replay_path"]),
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        scorecard = replay_result.scorecard
        pnl = replay_result.pnl
        event_type_counts = Counter(event.event_type.value for event in replay_result.events)

        assert section["manifest_event_count"] == str(entry["outcome_counts"]["event_count"])
        assert section["manifest_halt_count"] == str(entry["outcome_counts"]["halt_count"])
        assert section["manifest_order_reject_count"] == str(
            entry["outcome_counts"]["order_reject_count"]
        )
        assert section["manifest_fill_event_count"] == str(
            entry["outcome_counts"]["fill_event_count"]
        )
        assert section["manifest_partial_fill_intent_count"] == str(
            entry["outcome_counts"]["partial_fill_intent_count"]
        )
        assert section["manifest_alert_count"] == str(entry["outcome_counts"]["alert_count"])
        assert section["replay_event_count"] == str(scorecard.event_count)
        assert section["replay_halt_count"] == str(scorecard.halt_count)
        assert section["replay_order_reject_count"] == str(scorecard.order_reject_count)
        assert section["replay_fill_event_count"] == str(scorecard.fill_event_count)
        assert section["replay_partial_fill_intent_count"] == str(
            scorecard.partial_fill_intent_count
        )
        assert section["replay_alert_count"] == str(event_type_counts["alert.raised"])
        assert pnl is not None
        assert section["replay_starting_equity_usd"] == _format_float(pnl.starting_equity_usd)
        assert section["replay_gross_realized_pnl_usd"] == _format_float(pnl.gross_realized_pnl_usd)
        assert section["replay_pnl_total_fee_usd"] == _format_float(pnl.total_fee_usd)
        assert section["replay_net_realized_pnl_usd"] == _format_float(pnl.net_realized_pnl_usd)
        assert section["replay_ending_unrealized_pnl_usd"] == _format_float(
            pnl.ending_unrealized_pnl_usd
        )
        assert section["replay_ending_equity_usd"] == _format_float(pnl.ending_equity_usd)
        assert section["replay_return_fraction"] == _format_float(pnl.return_fraction)
        assert section["baseline_robustness_verdict"] in {"pass", "fail"}
        assert section["robustness_verdict"] in {"pass", "fail"}
        assert section["first_fail_scenario_id"] in {
            "baseline",
            "cost_slippage_plus_5bps",
            "cost_slippage_plus_10bps",
            "None",
        }
        assert "stress_cost_slippage_plus_5bps_verdict" in section
        assert "stress_cost_slippage_plus_10bps_verdict" in section
