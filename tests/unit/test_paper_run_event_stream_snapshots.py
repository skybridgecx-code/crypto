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


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    return json.loads((SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8"))


def _event_stream_payload(
    *,
    fixture_name: str,
    event_type_sequence: list[str],
) -> dict[str, object]:
    return {
        "fixture": fixture_name,
        "event_type_counts": {
            event_type: count for event_type, count in sorted(Counter(event_type_sequence).items())
        },
        "event_type_sequence": event_type_sequence,
    }


@pytest.mark.parametrize(
    ("fixture_name", "run_id", "snapshot_name", "equity_usd", "policy_overrides"),
    [
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-paper-run",
            "paper_run_breakout_long.event_stream.snapshot.json",
            100_000.0,
            None,
        ),
        (
            "paper_candles_mean_reversion_short.jsonl",
            "mean-reversion-paper-run",
            "paper_run_mean_reversion.event_stream.snapshot.json",
            100_000.0,
            None,
        ),
        (
            "paper_candles_high_volatility.jsonl",
            "high-vol-no-signal-paper-run",
            "paper_run_high_vol_no_signal.event_stream.snapshot.json",
            100_000.0,
            None,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-reject-low-equity-paper-run",
            "paper_run_breakout_reject_low_equity.event_stream.snapshot.json",
            1.0,
            None,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-halt-drawdown-zero-paper-run",
            "paper_run_breakout_halt_drawdown_zero.event_stream.snapshot.json",
            100_000.0,
            {"max_drawdown_fraction": 0.0},
        ),
    ],
)
def test_harness_generated_event_stream_snapshots(
    tmp_path: Path,
    fixture_name: str,
    run_id: str,
    snapshot_name: str,
    equity_usd: float,
    policy_overrides: dict[str, object] | None,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / fixture_name,
        settings=_paper_settings_for(tmp_path, policy_overrides=policy_overrides),
        run_id=run_id,
        equity_usd=equity_usd,
    )

    replay_result = replay_journal(result.journal_path)
    review_packet = build_review_packet(replay_result.events)
    event_type_sequence = [event.event_type.value for event in replay_result.events]
    payload = _event_stream_payload(
        fixture_name=fixture_name,
        event_type_sequence=event_type_sequence,
    )

    assert payload == _load_snapshot(snapshot_name)
    assert payload["event_type_sequence"] == review_packet["event_types"]
    assert sum(int(count) for count in payload["event_type_counts"].values()) == len(
        event_type_sequence
    )
