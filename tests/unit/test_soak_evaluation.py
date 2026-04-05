from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.policy.readiness import LiveReadinessStatus
from crypto_agent.runtime.loop import run_forward_paper_runtime

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


def _tick(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_forward_runtime_writes_multi_session_soak_evaluation(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id="forward-soak-demo",
        session_interval_seconds=60,
        max_sessions=3,
        tick_times=[
            _tick(2026, 4, 5, 9, 0),
            _tick(2026, 4, 5, 9, 1),
            _tick(2026, 4, 5, 9, 2),
        ],
        readiness_status=LiveReadinessStatus(
            runtime_id="forward-soak-demo",
            updated_at=_tick(2026, 4, 5, 8, 59),
            status="ready",
            limited_live_gate_status="ready_for_review",
        ),
    )

    soak = json.loads(result.soak_evaluation_path.read_text(encoding="utf-8"))
    gate = json.loads(result.live_gate_decision_path.read_text(encoding="utf-8"))
    report = result.live_gate_report_path.read_text(encoding="utf-8")

    assert result.soak_evaluation_path.exists()
    assert soak["runtime_id"] == "forward-soak-demo"
    assert soak["session_count"] == 3
    assert soak["completed_session_count"] == 3
    assert soak["executed_session_count"] == 3
    assert soak["blocked_session_count"] == 0
    assert soak["failed_session_count"] == 0
    assert soak["interrupted_session_count"] == 0
    assert [row["session_id"] for row in soak["rows"]] == [
        "session-0001",
        "session-0002",
        "session-0003",
    ]
    assert all(row["session_outcome"] == "executed" for row in soak["rows"])
    assert gate["state"] == "not_ready"
    assert "insufficient_shadow_sessions" in gate["reason_codes"]
    assert "# Forward Paper Live Gate" in report
    assert "## Soak Summary" in report
