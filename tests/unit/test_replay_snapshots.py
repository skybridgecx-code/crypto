from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import pytest

from crypto_agent.evaluation.replay import replay_journal

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


def _build_replay_snapshot(fixture_name: str) -> dict[str, object]:
    replay_result = replay_journal(FIXTURES_DIR / fixture_name)
    event_type_counts = dict(
        sorted(Counter(event.event_type.value for event in replay_result.events).items())
    )
    return {
        "fixture": fixture_name,
        "scorecard": replay_result.scorecard.model_dump(mode="json"),
        "event_type_counts": event_type_counts,
    }


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    snapshot_path = SNAPSHOTS_DIR / snapshot_name
    return json.loads(snapshot_path.read_text(encoding="utf-8"))


@pytest.mark.parametrize(
    ("fixture_name", "snapshot_name"),
    [
        (
            "replay_incident_mixed_recovery.jsonl",
            "replay_incident_mixed_recovery.snapshot.json",
        ),
        (
            "replay_incident_mixed_interleaved.jsonl",
            "replay_incident_mixed_interleaved.snapshot.json",
        ),
        (
            "replay_incident_multi_run_suite.jsonl",
            "replay_incident_multi_run_suite.snapshot.json",
        ),
        (
            "replay_incident_multi_run_interleaved.jsonl",
            "replay_incident_multi_run_interleaved.snapshot.json",
        ),
    ],
)
def test_replay_scorecard_and_event_count_snapshots(
    fixture_name: str,
    snapshot_name: str,
) -> None:
    assert _build_replay_snapshot(fixture_name) == _load_snapshot(snapshot_name)
