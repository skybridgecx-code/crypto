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


@pytest.mark.parametrize(
    (
        "fixture_name",
        "run_id",
        "snapshot_name",
        "equity_usd",
        "policy_overrides",
        "expected_event_types",
        "expected_order_reject_count",
        "expected_halt_count",
        "expected_alert_count",
        "expected_partial_fill_count",
    ),
    [
        (
            "paper_candles_high_volatility.jsonl",
            "high-vol-no-signal-paper-run",
            "paper_run_high_vol_no_signal.replay_artifacts.snapshot.json",
            100_000.0,
            None,
            [],
            0,
            0,
            0,
            0,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-reject-low-equity-paper-run",
            "paper_run_breakout_reject_low_equity.replay_artifacts.snapshot.json",
            1.0,
            None,
            [
                "trade.proposal.created",
                "risk.check.completed",
                "policy.decision.made",
                "order.intent.created",
                "order.submitted",
                "order.rejected",
                "alert.raised",
            ],
            1,
            0,
            1,
            0,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-halt-drawdown-zero-paper-run",
            "paper_run_breakout_halt_drawdown_zero.replay_artifacts.snapshot.json",
            100_000.0,
            {"max_drawdown_fraction": 0.0},
            [
                "trade.proposal.created",
                "risk.check.completed",
                "policy.decision.made",
                "kill_switch.activated",
                "alert.raised",
            ],
            0,
            1,
            1,
            0,
        ),
    ],
)
def test_harness_generated_adverse_journal_replay_artifact_snapshots(
    tmp_path: Path,
    fixture_name: str,
    run_id: str,
    snapshot_name: str,
    equity_usd: float,
    policy_overrides: dict[str, object] | None,
    expected_event_types: list[str],
    expected_order_reject_count: int,
    expected_halt_count: int,
    expected_alert_count: int,
    expected_partial_fill_count: int,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / fixture_name,
        settings=_paper_settings_for(tmp_path, policy_overrides=policy_overrides),
        run_id=run_id,
        equity_usd=equity_usd,
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
    assert review_packet["event_types"] == expected_event_types
    assert scorecard["order_reject_count"] == expected_order_reject_count
    assert scorecard["halt_count"] == expected_halt_count
    assert operator_summary["alert_count"] == expected_alert_count
    assert scorecard["partial_fill_intent_count"] == expected_partial_fill_count


@pytest.mark.parametrize(
    ("fixture_name", "run_id"),
    [
        ("paper_candles_breakout_long.jsonl", "breakout-partial-fill-paper-run"),
        ("paper_candles_mean_reversion_short.jsonl", "mean-reversion-partial-fill-paper-run"),
    ],
)
def test_harness_replay_artifacts_preserve_partial_fill_alert_paths(
    tmp_path: Path,
    fixture_name: str,
    run_id: str,
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

    assert scorecard["partial_fill_intent_count"] == 1
    assert scorecard["order_reject_count"] == 0
    assert scorecard["halt_count"] == 0
    assert operator_summary["alert_count"] == 1
    assert review_packet["event_types"][-1] == "alert.raised"
    assert operator_summary == result.operator_summary
