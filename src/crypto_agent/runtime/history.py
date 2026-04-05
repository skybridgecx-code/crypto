from __future__ import annotations

import json
from pathlib import Path

from crypto_agent.runtime.models import ForwardPaperHistoryEvent


def append_forward_paper_history(path: str | Path, event: ForwardPaperHistoryEvent) -> None:
    history_path = Path(path)
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n")


def read_forward_paper_history(path: str | Path) -> list[ForwardPaperHistoryEvent]:
    history_path = Path(path)
    if not history_path.exists():
        return []

    events: list[ForwardPaperHistoryEvent] = []
    with history_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            content = line.strip()
            if not content:
                continue
            events.append(ForwardPaperHistoryEvent.model_validate(json.loads(content)))
    return events
