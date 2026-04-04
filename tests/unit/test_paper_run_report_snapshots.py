from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


def _paper_settings_for(
    tmp_path: Path,
    *,
    policy_overrides: dict[str, object] | None = None,
):
    settings = load_settings(Path("config/paper.yaml"))
    policy = settings.policy
    if policy_overrides is not None:
        policy = policy.model_copy(update=policy_overrides)
    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "runs_dir": tmp_path / "runs",
                    "journals_dir": tmp_path / "journals",
                }
            ),
            "policy": policy,
        }
    )


def _load_report_snapshot(snapshot_name: str) -> str:
    return (SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8").rstrip("\n")


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


def _format_float(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def _event_type_sequence(event_types: list[str]) -> str:
    return ", ".join(event_types) if event_types else "<none>"


@pytest.mark.parametrize(
    (
        "fixture_name",
        "run_id",
        "snapshot_name",
        "equity_usd",
        "policy_overrides",
        "expected_event_count",
        "expected_alert_count",
        "expected_halt_count",
        "expected_order_reject_count",
        "expected_fill_event_count",
        "expected_partial_fill_count",
    ),
    [
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-paper-run",
            "paper_run_breakout_long.report.snapshot.md",
            100_000.0,
            None,
            8,
            1,
            0,
            0,
            2,
            1,
        ),
        (
            "paper_candles_high_volatility.jsonl",
            "high-vol-no-signal-paper-run",
            "paper_run_high_vol_no_signal.report.snapshot.md",
            100_000.0,
            None,
            0,
            0,
            0,
            0,
            0,
            0,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-reject-low-equity-paper-run",
            "paper_run_breakout_reject_low_equity.report.snapshot.md",
            1.0,
            None,
            7,
            1,
            0,
            1,
            0,
            0,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-halt-drawdown-zero-paper-run",
            "paper_run_breakout_halt_drawdown_zero.report.snapshot.md",
            100_000.0,
            {"max_drawdown_fraction": 0.0},
            5,
            1,
            1,
            0,
            0,
            0,
        ),
    ],
)
def test_single_run_report_snapshots_and_reconciliation(
    tmp_path: Path,
    fixture_name: str,
    run_id: str,
    snapshot_name: str,
    equity_usd: float,
    policy_overrides: dict[str, object] | None,
    expected_event_count: int,
    expected_alert_count: int,
    expected_halt_count: int,
    expected_order_reject_count: int,
    expected_fill_event_count: int,
    expected_partial_fill_count: int,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / fixture_name,
        settings=_paper_settings_for(tmp_path, policy_overrides=policy_overrides),
        run_id=run_id,
        equity_usd=equity_usd,
    )
    replay_result = replay_journal(result.journal_path)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    report = result.report_path.read_text(encoding="utf-8")

    assert result.report_path.exists()
    assert report == _load_report_snapshot(snapshot_name)

    overview = _section_key_values(report, "# Paper Run Operator Report")
    event_counts = _section_key_values(report, "## Event Counts")
    scorecard_section = _section_key_values(report, "## Scorecard")
    review_section = _section_key_values(report, "## Review Packet")
    operator_section = _section_key_values(report, "## Operator Summary")

    assert overview["run_id"] == run_id
    assert overview["journal_path"] == f"journals/{run_id}.jsonl"
    assert overview["summary_path"] == f"runs/{run_id}/summary.json"
    assert overview["report_path"] == f"runs/{run_id}/report.md"

    assert event_counts["event_count"] == str(expected_event_count)
    assert event_counts["alert_count"] == str(expected_alert_count)
    assert event_counts["kill_switch_activations"] == str(
        summary["operator_summary"]["kill_switch_activations"]
    )
    assert event_counts["review_rejected_event_count"] == str(
        summary["review_packet"]["rejected_event_count"]
    )
    assert event_counts["review_filled_event_count"] == str(
        summary["review_packet"]["filled_event_count"]
    )
    assert event_counts["first_event_type"] == str(summary["operator_summary"]["first_event_type"])
    assert event_counts["last_event_type"] == str(summary["operator_summary"]["last_event_type"])

    assert scorecard_section["proposal_count"] == str(summary["scorecard"]["proposal_count"])
    assert scorecard_section["approval_count"] == str(summary["scorecard"]["approval_count"])
    assert scorecard_section["denial_count"] == str(summary["scorecard"]["denial_count"])
    assert scorecard_section["halt_count"] == str(expected_halt_count)
    assert scorecard_section["order_intent_count"] == str(
        summary["scorecard"]["order_intent_count"]
    )
    assert scorecard_section["orders_submitted_count"] == str(
        summary["scorecard"]["orders_submitted_count"]
    )
    assert scorecard_section["order_reject_count"] == str(expected_order_reject_count)
    assert scorecard_section["fill_event_count"] == str(expected_fill_event_count)
    assert scorecard_section["filled_intent_count"] == str(
        summary["scorecard"]["filled_intent_count"]
    )
    assert scorecard_section["partial_fill_intent_count"] == str(expected_partial_fill_count)
    assert scorecard_section["complete_execution_count"] == str(
        summary["scorecard"]["complete_execution_count"]
    )
    assert scorecard_section["incomplete_execution_count"] == str(
        summary["scorecard"]["incomplete_execution_count"]
    )
    assert scorecard_section["average_slippage_bps"] == _format_float(
        replay_result.scorecard.average_slippage_bps
    )
    assert scorecard_section["max_slippage_bps"] == _format_float(
        replay_result.scorecard.max_slippage_bps
    )
    assert scorecard_section["total_fill_notional_usd"] == _format_float(
        replay_result.scorecard.total_fill_notional_usd
    )
    assert scorecard_section["total_fee_usd"] == _format_float(
        replay_result.scorecard.total_fee_usd
    )

    assert review_section["event_count"] == str(summary["review_packet"]["event_count"])
    assert review_section["filled_event_count"] == str(
        summary["review_packet"]["filled_event_count"]
    )
    assert review_section["rejected_event_count"] == str(
        summary["review_packet"]["rejected_event_count"]
    )
    assert review_section["event_types"] == _event_type_sequence(
        list(summary["review_packet"]["event_types"])
    )

    assert operator_section["fixture"] == fixture_name
    assert operator_section["run_id"] == run_id
    assert operator_section["event_count"] == str(expected_event_count)
    assert operator_section["proposal_count"] == str(summary["operator_summary"]["proposal_count"])
    assert operator_section["approval_count"] == str(summary["operator_summary"]["approval_count"])
    assert operator_section["denial_count"] == str(summary["operator_summary"]["denial_count"])
    assert operator_section["alert_count"] == str(expected_alert_count)
    assert operator_section["halt_count"] == str(expected_halt_count)
    assert operator_section["order_intent_count"] == str(
        summary["operator_summary"]["order_intent_count"]
    )
    assert operator_section["orders_submitted_count"] == str(
        summary["operator_summary"]["orders_submitted_count"]
    )
    assert operator_section["order_reject_count"] == str(expected_order_reject_count)
    assert operator_section["fill_event_count"] == str(expected_fill_event_count)
    assert operator_section["partial_fill_intent_count"] == str(expected_partial_fill_count)
    assert operator_section["complete_execution_count"] == str(
        summary["operator_summary"]["complete_execution_count"]
    )
    assert operator_section["incomplete_execution_count"] == str(
        summary["operator_summary"]["incomplete_execution_count"]
    )
    assert operator_section["kill_switch_activations"] == str(
        summary["operator_summary"]["kill_switch_activations"]
    )
    assert operator_section["review_rejected_event_count"] == str(
        summary["operator_summary"]["review_rejected_event_count"]
    )
    assert operator_section["review_filled_event_count"] == str(
        summary["operator_summary"]["review_filled_event_count"]
    )
    assert operator_section["first_event_type"] == str(
        summary["operator_summary"]["first_event_type"]
    )
    assert operator_section["last_event_type"] == str(
        summary["operator_summary"]["last_event_type"]
    )
