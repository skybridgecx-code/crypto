from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.events.journal import build_review_packet

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    snapshot_path = SNAPSHOTS_DIR / snapshot_name
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


def _build_review_packet_snapshot(fixture_name: str) -> dict[str, object]:
    replay_result = replay_journal(FIXTURES_DIR / fixture_name)
    return {
        "fixture": fixture_name,
        "review_packet": build_review_packet(replay_result.events),
    }


def _build_operator_summary_snapshot(fixture_name: str) -> dict[str, object]:
    replay_result = replay_journal(FIXTURES_DIR / fixture_name)
    review_packet = build_review_packet(replay_result.events)
    event_type_counts = Counter(event.event_type.value for event in replay_result.events)
    scorecard = replay_result.scorecard

    return {
        "fixture": fixture_name,
        "run_id": scorecard.run_id,
        "event_count": scorecard.event_count,
        "proposal_count": scorecard.proposal_count,
        "approval_count": scorecard.approval_count,
        "denial_count": scorecard.denial_count,
        "halt_count": scorecard.halt_count,
        "order_intent_count": scorecard.order_intent_count,
        "orders_submitted_count": scorecard.orders_submitted_count,
        "order_reject_count": scorecard.order_reject_count,
        "fill_event_count": scorecard.fill_event_count,
        "partial_fill_intent_count": scorecard.partial_fill_intent_count,
        "complete_execution_count": scorecard.complete_execution_count,
        "incomplete_execution_count": scorecard.incomplete_execution_count,
        "alert_count": event_type_counts["alert.raised"],
        "kill_switch_activations": event_type_counts["kill_switch.activated"],
        "first_event_type": replay_result.events[0].event_type.value,
        "last_event_type": replay_result.events[-1].event_type.value,
        "review_rejected_event_count": review_packet["rejected_event_count"],
        "review_filled_event_count": review_packet["filled_event_count"],
    }


@pytest.mark.parametrize(
    ("fixture_name", "snapshot_name"),
    [
        (
            "replay_incident_mixed_recovery.jsonl",
            "replay_incident_mixed_recovery.review_packet.snapshot.json",
        ),
        (
            "replay_incident_multi_run_suite.jsonl",
            "replay_incident_multi_run_suite.review_packet.snapshot.json",
        ),
        (
            "replay_incident_multi_run_interleaved.jsonl",
            "replay_incident_multi_run_interleaved.review_packet.snapshot.json",
        ),
    ],
)
def test_review_packet_snapshots(fixture_name: str, snapshot_name: str) -> None:
    assert _build_review_packet_snapshot(fixture_name) == _load_snapshot(snapshot_name)


@pytest.mark.parametrize(
    ("fixture_name", "snapshot_name"),
    [
        (
            "replay_incident_mixed_recovery.jsonl",
            "replay_incident_mixed_recovery.operator_summary.snapshot.json",
        ),
        (
            "replay_incident_multi_run_suite.jsonl",
            "replay_incident_multi_run_suite.operator_summary.snapshot.json",
        ),
        (
            "replay_incident_multi_run_interleaved.jsonl",
            "replay_incident_multi_run_interleaved.operator_summary.snapshot.json",
        ),
    ],
)
def test_operator_summary_snapshots(fixture_name: str, snapshot_name: str) -> None:
    assert _build_operator_summary_snapshot(fixture_name) == _load_snapshot(snapshot_name)
