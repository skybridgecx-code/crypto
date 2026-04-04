from datetime import UTC, datetime
from pathlib import Path

import pytest
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.events.journal import AppendOnlyJournal, build_review_packet
from crypto_agent.monitoring.alerts import generate_kill_switch_alerts
from crypto_agent.policy.kill_switch import KillSwitchContext, evaluate_kill_switch

FIXTURES_DIR = Path("tests/fixtures")


def _paper_settings():
    return load_settings(Path("config/paper.yaml"))


@pytest.mark.parametrize(
    ("context", "expected_reason"),
    [
        (KillSwitchContext(manual_halt=True), "manual_halt"),
        (
            KillSwitchContext(missing_market_data_heartbeat=True),
            "missing_market_data_heartbeat",
        ),
        (KillSwitchContext(position_mismatch=True), "position_mismatch"),
        (KillSwitchContext(journal_write_failed=True), "journal_write_failed"),
        (KillSwitchContext(consecutive_order_rejects=3), "repeated_order_rejects"),
        (KillSwitchContext(slippage_breach_count=2), "slippage_breaches"),
        (KillSwitchContext(drawdown_fraction=0.03), "drawdown_breach"),
    ],
)
def test_kill_switch_incident_paths_activate(
    context: KillSwitchContext, expected_reason: str
) -> None:
    state = evaluate_kill_switch(context, _paper_settings())

    assert state.active is True
    assert expected_reason in state.reason_codes


def test_generate_kill_switch_alerts_for_heartbeat_and_journal_failure() -> None:
    alerts = generate_kill_switch_alerts(
        KillSwitchContext(
            missing_market_data_heartbeat=True,
            journal_write_failed=True,
        ),
        _paper_settings(),
        observed_at=datetime(2026, 4, 3, 18, 0, tzinfo=UTC),
    )

    codes = {alert.code for alert in alerts}
    assert "missing_market_data_heartbeat" in codes
    assert "journal_write_failed" in codes


def test_replay_fixture_partial_fill_scorecard_and_journal_completeness() -> None:
    journal = AppendOnlyJournal(FIXTURES_DIR / "replay_incident_partial_fill.jsonl")
    events = journal.read_all()
    scorecard = replay_journal(FIXTURES_DIR / "replay_incident_partial_fill.jsonl").scorecard
    review_packet = build_review_packet(events)

    assert [event.event_type.value for event in events] == [
        "trade.proposal.created",
        "risk.check.completed",
        "policy.decision.made",
        "order.intent.created",
        "order.submitted",
        "alert.raised",
        "order.filled",
        "order.filled",
    ]
    assert scorecard.partial_fill_intent_count == 1
    assert scorecard.fill_event_count == 2
    assert scorecard.max_slippage_bps == 2.6
    assert review_packet["filled_event_count"] == 2


def test_replay_fixture_reject_scorecard_and_alert_coverage() -> None:
    journal = AppendOnlyJournal(FIXTURES_DIR / "replay_incident_reject.jsonl")
    events = journal.read_all()
    replay_result = replay_journal(FIXTURES_DIR / "replay_incident_reject.jsonl")

    alert_codes = [
        str(event.payload["code"]) for event in events if event.event_type.value == "alert.raised"
    ]

    assert replay_result.scorecard.order_reject_count == 1
    assert replay_result.scorecard.fill_event_count == 0
    assert replay_result.scorecard.complete_execution_count == 1
    assert replay_result.scorecard.average_slippage_bps == 0.5
    assert "order_rejected" in alert_codes


def test_replay_fixture_halt_scorecard_and_journal_completeness() -> None:
    journal = AppendOnlyJournal(FIXTURES_DIR / "replay_incident_halt.jsonl")
    events = journal.read_all()
    replay_result = replay_journal(FIXTURES_DIR / "replay_incident_halt.jsonl")

    assert [event.event_type.value for event in events] == [
        "trade.proposal.created",
        "risk.check.completed",
        "policy.decision.made",
        "kill_switch.activated",
        "alert.raised",
        "alert.raised",
    ]
    assert replay_result.scorecard.halt_count == 1
    assert replay_result.scorecard.order_intent_count == 0
    assert replay_result.scorecard.complete_execution_count == 1


def test_replay_fixture_mixed_recovery_scorecard_and_recovery_path() -> None:
    journal = AppendOnlyJournal(FIXTURES_DIR / "replay_incident_mixed_recovery.jsonl")
    events = journal.read_all()
    replay_result = replay_journal(FIXTURES_DIR / "replay_incident_mixed_recovery.jsonl")
    review_packet = build_review_packet(events)

    alert_codes = [
        str(event.payload["code"]) for event in events if event.event_type.value == "alert.raised"
    ]
    policy_actions = [
        str(event.payload["action"])
        for event in events
        if event.event_type.value == "policy.decision.made"
    ]

    assert replay_result.scorecard.event_count == 28
    assert replay_result.scorecard.proposal_count == 4
    assert replay_result.scorecard.approval_count == 3
    assert replay_result.scorecard.halt_count == 1
    assert replay_result.scorecard.order_intent_count == 3
    assert replay_result.scorecard.orders_submitted_count == 3
    assert replay_result.scorecard.order_reject_count == 1
    assert replay_result.scorecard.fill_event_count == 3
    assert replay_result.scorecard.filled_intent_count == 2
    assert replay_result.scorecard.partial_fill_intent_count == 1
    assert replay_result.scorecard.complete_execution_count == 4
    assert replay_result.scorecard.incomplete_execution_count == 0
    assert replay_result.scorecard.average_slippage_bps == pytest.approx(4.6 / 3)
    assert replay_result.scorecard.max_slippage_bps == 2.8
    assert replay_result.scorecard.total_fill_notional_usd == 17000.0
    assert replay_result.scorecard.total_fee_usd == pytest.approx(3.4)
    assert review_packet["event_count"] == 28
    assert review_packet["filled_event_count"] == 3
    assert review_packet["rejected_event_count"] == 1
    assert policy_actions == ["allow", "allow", "halt", "allow"]
    assert alert_codes == [
        "order_rejected",
        "slippage_above_threshold",
        "partial_fill_detected",
        "missing_market_data_heartbeat",
        "journal_write_failed",
    ]
    assert events[-2].event_type.value == "order.submitted"
    assert events[-1].event_type.value == "order.filled"
    assert str(events[-1].payload["intent_id"]) == "intent-recovery"


def test_replay_fixture_mixed_interleaved_scorecard_and_mapping_integrity() -> None:
    journal = AppendOnlyJournal(FIXTURES_DIR / "replay_incident_mixed_interleaved.jsonl")
    events = journal.read_all()
    replay_result = replay_journal(FIXTURES_DIR / "replay_incident_mixed_interleaved.jsonl")

    proposal_ids = [
        str(event.payload["proposal_id"])
        for event in events
        if event.event_type.value == "trade.proposal.created"
    ]
    filled_intent_ids = [
        str(event.payload["intent_id"])
        for event in events
        if event.event_type.value == "order.filled"
    ]
    kill_switch_reasons = [
        list(event.payload["reason_codes"])
        for event in events
        if event.event_type.value == "kill_switch.activated"
    ]

    assert proposal_ids == [
        "proposal-btc-reject",
        "proposal-eth-partial",
        "proposal-btc-halt",
        "proposal-eth-recovery",
    ]
    assert filled_intent_ids == [
        "intent-eth-partial",
        "intent-eth-partial",
        "intent-eth-recovery",
    ]
    assert kill_switch_reasons == [["manual_halt"]]
    assert replay_result.scorecard.event_count == 27
    assert replay_result.scorecard.proposal_count == 4
    assert replay_result.scorecard.approval_count == 3
    assert replay_result.scorecard.halt_count == 1
    assert replay_result.scorecard.order_intent_count == 3
    assert replay_result.scorecard.orders_submitted_count == 3
    assert replay_result.scorecard.order_reject_count == 1
    assert replay_result.scorecard.fill_event_count == 3
    assert replay_result.scorecard.filled_intent_count == 2
    assert replay_result.scorecard.partial_fill_intent_count == 1
    assert replay_result.scorecard.complete_execution_count == 4
    assert replay_result.scorecard.incomplete_execution_count == 0
    assert replay_result.scorecard.average_slippage_bps == pytest.approx(5.5 / 3)
    assert replay_result.scorecard.max_slippage_bps == 3.4
    assert replay_result.scorecard.total_fill_notional_usd == 13700.0
    assert replay_result.scorecard.total_fee_usd == pytest.approx(2.74)
    assert events[-1].event_type.value == "order.filled"
    assert str(events[-1].payload["intent_id"]) == "intent-eth-recovery"
