from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.events.journal import build_review_packet

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


def _operator_summary(
    *,
    fixture_name: str,
    scorecard: dict[str, object],
    review_packet: dict[str, object],
) -> dict[str, object]:
    event_types = [str(event_type) for event_type in review_packet["event_types"]]
    event_type_counts = Counter(event_types)
    return {
        "fixture": fixture_name,
        "run_id": scorecard["run_id"],
        "event_count": scorecard["event_count"],
        "proposal_count": scorecard["proposal_count"],
        "approval_count": scorecard["approval_count"],
        "denial_count": scorecard["denial_count"],
        "halt_count": scorecard["halt_count"],
        "order_intent_count": scorecard["order_intent_count"],
        "orders_submitted_count": scorecard["orders_submitted_count"],
        "order_reject_count": scorecard["order_reject_count"],
        "fill_event_count": scorecard["fill_event_count"],
        "partial_fill_intent_count": scorecard["partial_fill_intent_count"],
        "complete_execution_count": scorecard["complete_execution_count"],
        "incomplete_execution_count": scorecard["incomplete_execution_count"],
        "alert_count": event_type_counts["alert.raised"],
        "kill_switch_activations": event_type_counts["kill_switch.activated"],
        "review_rejected_event_count": review_packet["rejected_event_count"],
        "review_filled_event_count": review_packet["filled_event_count"],
        "first_event_type": event_types[0] if event_types else None,
        "last_event_type": event_types[-1] if event_types else None,
    }


@pytest.mark.parametrize(
    ("fixture_name", "run_id", "snapshot_name"),
    [
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-paper-run",
            "paper_run_breakout_long.replay_artifacts.snapshot.json",
        ),
        (
            "paper_candles_mean_reversion_short.jsonl",
            "mean-reversion-paper-run",
            "paper_run_mean_reversion.replay_artifacts.snapshot.json",
        ),
    ],
)
def test_harness_generated_journal_replay_artifact_snapshots(
    tmp_path: Path,
    fixture_name: str,
    run_id: str,
    snapshot_name: str,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / fixture_name,
        settings=_paper_settings_for(tmp_path),
        run_id=run_id,
    )

    replay_result = replay_journal(result.journal_path)
    scorecard = replay_result.scorecard.model_dump(mode="json")
    review_packet = build_review_packet(replay_result.events)
    operator_summary = _operator_summary(
        fixture_name=fixture_name,
        scorecard=scorecard,
        review_packet=review_packet,
    )

    assert {
        "fixture": fixture_name,
        "scorecard": scorecard,
        "review_packet": review_packet,
        "operator_summary": operator_summary,
    } == _load_snapshot(snapshot_name)
    assert scorecard == result.scorecard.model_dump(mode="json")
    assert review_packet == result.review_packet
    assert operator_summary == result.operator_summary
