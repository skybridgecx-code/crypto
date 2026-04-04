from __future__ import annotations

from pathlib import Path

from crypto_agent.evaluation.models import ReplayResult
from crypto_agent.evaluation.scorecard import build_scorecard
from crypto_agent.events.journal import AppendOnlyJournal


def replay_journal(path: str | Path) -> ReplayResult:
    journal = AppendOnlyJournal(path)
    events = journal.read_all()
    return ReplayResult(events=events, scorecard=build_scorecard(events))
