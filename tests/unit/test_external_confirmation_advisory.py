from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.enums import EventType
from crypto_agent.events.journal import AppendOnlyJournal

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


def _write_external_confirmation(
    tmp_path: Path,
    *,
    asset: str,
    directional_bias: str,
    confidence_adjustment: float,
    veto_trade: bool,
) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "external_confirmation.json"
    payload = {
        "artifact_kind": "external_confirmation_advisory_v1",
        "source_system": "omega-polymarket-fusion",
        "asset": asset,
        "directional_bias": directional_bias,
        "confidence_adjustment": confidence_adjustment,
        "veto_trade": veto_trade,
        "rationale": "Deterministic fused external advisory context.",
        "supporting_tags": ["fused", "cross_market"],
        "observed_at_epoch_ns": 1700000000000000123,
        "correlation_id": "theme_ctx_strong.analysis_success_export",
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _first_proposal_confidence(journal_path: Path) -> float:
    events = AppendOnlyJournal(journal_path).read_all()
    proposal_events = [
        event for event in events if event.event_type is EventType.TRADE_PROPOSAL_CREATED
    ]
    assert proposal_events
    return float(proposal_events[0].payload["confidence"])


def _external_confirmation_events(journal_path: Path) -> list[dict[str, object]]:
    events = AppendOnlyJournal(journal_path).read_all()
    return [
        event.payload
        for event in events
        if event.source == "external_confirmation" and event.event_type is EventType.ALERT_RAISED
    ]


def _proposal_pipeline(result) -> dict[str, object]:
    payload = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))
    return payload["proposal_pipeline"]


def test_no_external_confirmation_artifact_keeps_baseline_behavior(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)

    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-none",
    )

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    assert "external_confirmation" not in summary
    assert result.scorecard.proposal_count == 1
    assert _external_confirmation_events(result.journal_path) == []


def test_external_confirmation_confirmation_boosts_confidence_bounded(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    baseline = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-baseline",
    )
    baseline_confidence = _first_proposal_confidence(baseline.journal_path)

    artifact_path = _write_external_confirmation(
        tmp_path,
        asset="BTCUSDT",
        directional_bias="buy",
        confidence_adjustment=0.2,
        veto_trade=False,
    )
    boosted = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-boosted",
        external_confirmation_path=artifact_path,
    )

    boosted_confidence = _first_proposal_confidence(boosted.journal_path)
    assert boosted_confidence == pytest.approx(min(1.0, baseline_confidence + 0.2))
    external_events = _external_confirmation_events(boosted.journal_path)
    assert len(external_events) == 1
    assert external_events[0]["status"] == "boosted_confirmation"


def test_external_confirmation_conflict_penalty_and_veto(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    baseline = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-baseline-conflict",
    )
    baseline_confidence = _first_proposal_confidence(baseline.journal_path)

    penalty_path = _write_external_confirmation(
        tmp_path,
        asset="BTCUSDT",
        directional_bias="sell",
        confidence_adjustment=0.12,
        veto_trade=False,
    )
    penalized = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-penalized",
        external_confirmation_path=penalty_path,
    )
    penalized_confidence = _first_proposal_confidence(penalized.journal_path)
    assert penalized_confidence == pytest.approx(max(0.0, baseline_confidence - 0.12))
    penalty_events = _external_confirmation_events(penalized.journal_path)
    assert len(penalty_events) == 1
    assert penalty_events[0]["status"] == "penalized_conflict"
    assert penalized.scorecard.proposal_count == 1
    assert penalized.scorecard.orders_submitted_count == 1

    veto_path = _write_external_confirmation(
        tmp_path,
        asset="BTCUSDT",
        directional_bias="sell",
        confidence_adjustment=0.12,
        veto_trade=True,
    )
    vetoed = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-vetoed",
        external_confirmation_path=veto_path,
    )
    veto_events = _external_confirmation_events(vetoed.journal_path)
    assert len(veto_events) == 1
    assert veto_events[0]["status"] == "vetoed_conflict"
    assert vetoed.scorecard.proposal_count == 0


def test_conservative_impact_policy_blocks_penalized_conflict_before_order_submission(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    penalty_path = _write_external_confirmation(
        tmp_path,
        asset="BTCUSDT",
        directional_bias="sell",
        confidence_adjustment=0.12,
        veto_trade=False,
    )

    blocked = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-penalized-conservative",
        external_confirmation_path=penalty_path,
        external_confirmation_impact_policy="conservative",
    )

    summary = json.loads(blocked.summary_path.read_text(encoding="utf-8"))
    report = blocked.report_path.read_text(encoding="utf-8")
    pipeline = _proposal_pipeline(blocked)
    penalty_events = _external_confirmation_events(blocked.journal_path)

    assert penalty_events[0]["status"] == "penalized_conflict"
    assert blocked.scorecard.proposal_count == 0
    assert blocked.scorecard.orders_submitted_count == 0
    assert pipeline["external_confirmation_impact_policy"] == "conservative"
    assert pipeline["emitted_proposal_count"] == 1
    assert pipeline["dropped_by_external_confirmation_count"] == 1
    assert summary["external_confirmation"]["impact_policy"] == "conservative"
    assert summary["external_confirmation"]["decision_status_counts"] == {
        "penalized_conflict": 1
    }
    assert "impact_policy: conservative" in report


def test_conservative_impact_policy_does_not_block_boosted_or_mismatched_advisory(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    boosted_path = _write_external_confirmation(
        tmp_path / "boosted",
        asset="BTCUSDT",
        directional_bias="buy",
        confidence_adjustment=0.12,
        veto_trade=False,
    )
    mismatch_path = _write_external_confirmation(
        tmp_path / "mismatch",
        asset="ETHUSDT",
        directional_bias="buy",
        confidence_adjustment=0.12,
        veto_trade=False,
    )

    boosted = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-boosted-conservative",
        external_confirmation_path=boosted_path,
        external_confirmation_impact_policy="conservative",
    )
    mismatch = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-mismatch-conservative",
        external_confirmation_path=mismatch_path,
        external_confirmation_impact_policy="conservative",
    )

    assert _external_confirmation_events(boosted.journal_path)[0]["status"] == (
        "boosted_confirmation"
    )
    assert boosted.scorecard.proposal_count == 1
    assert boosted.scorecard.orders_submitted_count == 1
    assert _proposal_pipeline(boosted)["dropped_by_external_confirmation_count"] == 0

    assert _external_confirmation_events(mismatch.journal_path)[0]["status"] == (
        "ignored_asset_mismatch"
    )
    assert mismatch.scorecard.proposal_count == 1
    assert mismatch.scorecard.orders_submitted_count == 1
    assert _proposal_pipeline(mismatch)["dropped_by_external_confirmation_count"] == 0


def test_conservative_impact_policy_preserves_veto_blocking(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    veto_path = _write_external_confirmation(
        tmp_path,
        asset="BTCUSDT",
        directional_bias="sell",
        confidence_adjustment=0.12,
        veto_trade=True,
    )

    vetoed = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-vetoed-conservative",
        external_confirmation_path=veto_path,
        external_confirmation_impact_policy="conservative",
    )

    assert _external_confirmation_events(vetoed.journal_path)[0]["status"] == "vetoed_conflict"
    assert vetoed.scorecard.proposal_count == 0
    assert vetoed.scorecard.orders_submitted_count == 0
    assert _proposal_pipeline(vetoed)["dropped_by_external_confirmation_count"] == 1


def test_external_confirmation_malformed_artifact_fails_with_deterministic_error(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    bad_path = tmp_path / "external_confirmation_bad.json"
    bad_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(ValueError, match="external_confirmation_artifact_invalid_json:"):
        run_paper_replay(
            FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
            settings=settings,
            run_id="external-bad-json",
            external_confirmation_path=bad_path,
        )


def test_external_confirmation_asset_mismatch_is_ignored(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    baseline = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-baseline-mismatch",
    )
    baseline_confidence = _first_proposal_confidence(baseline.journal_path)

    artifact_path = _write_external_confirmation(
        tmp_path,
        asset="ETHUSDT",
        directional_bias="buy",
        confidence_adjustment=0.2,
        veto_trade=False,
    )
    mismatch = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        run_id="external-mismatch",
        external_confirmation_path=artifact_path,
    )

    mismatch_confidence = _first_proposal_confidence(mismatch.journal_path)
    assert mismatch_confidence == pytest.approx(baseline_confidence)
    mismatch_events = _external_confirmation_events(mismatch.journal_path)
    assert len(mismatch_events) == 1
    assert mismatch_events[0]["status"] == "ignored_asset_mismatch"
