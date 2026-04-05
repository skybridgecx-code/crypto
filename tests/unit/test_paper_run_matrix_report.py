from __future__ import annotations

import json
from collections import Counter
from math import fsum
from pathlib import Path

from crypto_agent.cli.matrix import (
    MANIFEST_COUNT_KEYS,
    REPLAY_PNL_KEYS,
    REPLAY_TOTAL_KEYS,
    run_paper_replay_matrix,
)
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal


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


def test_matrix_report_artifact_shape_and_reconciliation(tmp_path: Path) -> None:
    manifest = run_paper_replay_matrix(
        settings=_paper_settings_for(tmp_path),
        matrix_run_id="paper-run-matrix-demo",
    )
    manifest_payload = json.loads(Path(manifest.manifest_path).read_text(encoding="utf-8"))
    report_path = Path(manifest.manifest_path).with_name("report.md")
    report = report_path.read_text(encoding="utf-8")

    assert report_path.exists()
    assert report.startswith("# Paper Run Matrix Operator Report\n")
    assert "## Aggregate Manifest Counts" in report
    assert "## Aggregate Replay Totals" in report
    assert "## Aggregate Replay PnL" in report
    assert "## Per-Run Details" in report
    assert f"matrix_run_id: {manifest.matrix_run_id}" in report
    assert f"entry_count: {manifest.entry_count}" in report
    assert f"manifest_path: runs/{manifest.matrix_run_id}/manifest.json" in report
    assert (
        f"matrix_trade_ledger_path: runs/{manifest.matrix_run_id}/matrix_trade_ledger.json"
        in report
    )
    assert f"report_path: runs/{manifest.matrix_run_id}/report.md" in report

    aggregate_manifest = _section_key_values(report, "## Aggregate Manifest Counts")
    for key in MANIFEST_COUNT_KEYS:
        assert aggregate_manifest[key] == str(manifest.aggregate_counts[key])

    run_sections = _run_sections(report)
    assert len(run_sections) == int(manifest_payload["entry_count"])

    replay_totals = {key: 0 for key in REPLAY_TOTAL_KEYS}
    total_fill_notionals: list[float] = []
    total_fees: list[float] = []
    max_slippages: list[float] = []
    replay_pnl_totals = {key: 0.0 for key in REPLAY_PNL_KEYS}
    for entry in manifest_payload["entries"]:
        section = run_sections[str(entry["run_id"])]
        summary = json.loads(Path(str(entry["summary_path"])).read_text(encoding="utf-8"))
        replay_result = replay_journal(
            str(entry["journal_path"]),
            replay_path=str(summary["replay_path"]),
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        scorecard = replay_result.scorecard
        pnl = replay_result.pnl
        event_type_counts = Counter(event.event_type.value for event in replay_result.events)

        assert section["fixture"] == str(entry["fixture"])
        assert section["journal_path"] == f"journals/{entry['run_id']}.jsonl"
        assert section["summary_path"] == f"runs/{entry['run_id']}/summary.json"
        assert section["manifest_event_count"] == str(entry["outcome_counts"]["event_count"])
        assert section["manifest_proposal_count"] == str(entry["outcome_counts"]["proposal_count"])
        assert section["manifest_approval_count"] == str(entry["outcome_counts"]["approval_count"])
        assert section["manifest_denial_count"] == str(entry["outcome_counts"]["denial_count"])
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

        assert section["replay_run_id"] == scorecard.run_id
        assert section["replay_event_count"] == str(scorecard.event_count)
        assert section["replay_proposal_count"] == str(scorecard.proposal_count)
        assert section["replay_approval_count"] == str(scorecard.approval_count)
        assert section["replay_denial_count"] == str(scorecard.denial_count)
        assert section["replay_halt_count"] == str(scorecard.halt_count)
        assert section["replay_order_intent_count"] == str(scorecard.order_intent_count)
        assert section["replay_orders_submitted_count"] == str(scorecard.orders_submitted_count)
        assert section["replay_order_reject_count"] == str(scorecard.order_reject_count)
        assert section["replay_fill_event_count"] == str(scorecard.fill_event_count)
        assert section["replay_filled_intent_count"] == str(scorecard.filled_intent_count)
        assert section["replay_partial_fill_intent_count"] == str(
            scorecard.partial_fill_intent_count
        )
        assert section["replay_complete_execution_count"] == str(scorecard.complete_execution_count)
        assert section["replay_incomplete_execution_count"] == str(
            scorecard.incomplete_execution_count
        )
        assert section["replay_alert_count"] == str(event_type_counts["alert.raised"])
        assert section["replay_kill_switch_activations"] == str(
            event_type_counts["kill_switch.activated"]
        )
        assert section["replay_average_slippage_bps"] == _format_float(
            scorecard.average_slippage_bps
        )
        assert section["replay_max_slippage_bps"] == _format_float(scorecard.max_slippage_bps)
        assert section["replay_total_fill_notional_usd"] == _format_float(
            scorecard.total_fill_notional_usd
        )
        assert section["replay_total_fee_usd"] == _format_float(scorecard.total_fee_usd)
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

        replay_totals["event_count"] += scorecard.event_count
        replay_totals["proposal_count"] += scorecard.proposal_count
        replay_totals["approval_count"] += scorecard.approval_count
        replay_totals["denial_count"] += scorecard.denial_count
        replay_totals["halt_count"] += scorecard.halt_count
        replay_totals["order_intent_count"] += scorecard.order_intent_count
        replay_totals["orders_submitted_count"] += scorecard.orders_submitted_count
        replay_totals["order_reject_count"] += scorecard.order_reject_count
        replay_totals["fill_event_count"] += scorecard.fill_event_count
        replay_totals["filled_intent_count"] += scorecard.filled_intent_count
        replay_totals["partial_fill_intent_count"] += scorecard.partial_fill_intent_count
        replay_totals["complete_execution_count"] += scorecard.complete_execution_count
        replay_totals["incomplete_execution_count"] += scorecard.incomplete_execution_count
        replay_totals["alert_count"] += int(event_type_counts["alert.raised"])
        replay_totals["kill_switch_activations"] += int(event_type_counts["kill_switch.activated"])
        if scorecard.run_id == "empty":
            replay_totals["empty_replay_scorecard_count"] += 1
        total_fill_notionals.append(scorecard.total_fill_notional_usd)
        total_fees.append(scorecard.total_fee_usd)
        max_slippages.append(scorecard.max_slippage_bps)
        replay_pnl_totals["starting_equity_usd"] += pnl.starting_equity_usd
        replay_pnl_totals["gross_realized_pnl_usd"] += pnl.gross_realized_pnl_usd
        replay_pnl_totals["total_fee_usd"] += pnl.total_fee_usd
        replay_pnl_totals["net_realized_pnl_usd"] += pnl.net_realized_pnl_usd
        replay_pnl_totals["ending_unrealized_pnl_usd"] += pnl.ending_unrealized_pnl_usd
        replay_pnl_totals["ending_equity_usd"] += pnl.ending_equity_usd

    aggregate_replay = _section_key_values(report, "## Aggregate Replay Totals")
    for key in REPLAY_TOTAL_KEYS:
        assert aggregate_replay[key] == str(replay_totals[key])

    if replay_pnl_totals["starting_equity_usd"] > 0:
        replay_pnl_totals["return_fraction"] = (
            replay_pnl_totals["ending_equity_usd"] - replay_pnl_totals["starting_equity_usd"]
        ) / replay_pnl_totals["starting_equity_usd"]

    assert aggregate_replay["total_fill_notional_usd"] == _format_float(fsum(total_fill_notionals))
    assert aggregate_replay["total_fee_usd"] == _format_float(fsum(total_fees))
    assert aggregate_replay["max_slippage_bps"] == _format_float(max(max_slippages, default=0.0))

    aggregate_pnl = _section_key_values(report, "## Aggregate Replay PnL")
    for key in REPLAY_PNL_KEYS:
        assert aggregate_pnl[key] == _format_float(replay_pnl_totals[key])
