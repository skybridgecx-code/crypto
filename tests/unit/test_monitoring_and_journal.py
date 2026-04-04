from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.events.journal import (
    AppendOnlyJournal,
    build_execution_events,
    build_review_packet,
)
from crypto_agent.execution.models import PaperExecutionConfig
from crypto_agent.execution.simulator import PaperExecutionSimulator
from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.monitoring.alerts import generate_execution_alerts
from crypto_agent.monitoring.health import build_health_snapshot
from crypto_agent.regime.rules import classify_regime
from crypto_agent.risk.checks import evaluate_trade_proposal
from crypto_agent.signals.breakout import generate_breakout_proposal

FIXTURES_DIR = Path("tests/fixtures")


def _approved_breakout_flow():
    settings = load_settings(Path("config/paper.yaml"))
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_breakout_long.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)
    regime = classify_regime(features)
    proposal = generate_breakout_proposal(candles, features, regime)
    assert proposal is not None
    from crypto_agent.portfolio.positions import PortfolioState

    portfolio = PortfolioState(
        equity_usd=100_000.0,
        available_cash_usd=100_000.0,
        daily_realized_pnl_usd=0.0,
    )
    risk_result = evaluate_trade_proposal(proposal, portfolio, settings)
    assert risk_result.decision.action.value == "allow"
    return proposal, risk_result


def test_generate_execution_alerts_for_partial_fill_and_slippage() -> None:
    proposal, risk_result = _approved_breakout_flow()
    simulator = PaperExecutionSimulator(
        PaperExecutionConfig(partial_fill_notional_threshold=1_000.0)
    )
    report = simulator.submit(risk_result)

    alerts = generate_execution_alerts(report, slippage_alert_bps=0.5)

    codes = {alert.code for alert in alerts}
    assert "partial_fill_detected" in codes
    assert "slippage_above_threshold" in codes
    assert report.intent.symbol == proposal.symbol


def test_generate_execution_alerts_for_reject_path() -> None:
    _, risk_result = _approved_breakout_flow()
    simulator = PaperExecutionSimulator(PaperExecutionConfig(min_notional_usd=1_000_000.0))
    report = simulator.submit(risk_result)

    alerts = generate_execution_alerts(report)

    assert report.rejected is True
    assert any(alert.code == "order_rejected" for alert in alerts)


def test_append_only_journal_round_trips_complete_fill_sequence(tmp_path: Path) -> None:
    proposal, risk_result = _approved_breakout_flow()
    simulator = PaperExecutionSimulator(
        PaperExecutionConfig(partial_fill_notional_threshold=1_000.0)
    )
    report = simulator.submit(risk_result)
    events = build_execution_events("run-123", proposal, risk_result, report)
    journal = AppendOnlyJournal(tmp_path / "journal.jsonl")

    journal.append_many(events)
    read_back = journal.read_all()
    summary = build_review_packet(read_back)
    health = build_health_snapshot("run-123", read_back, [report])

    assert [event.event_type.value for event in read_back] == [
        "trade.proposal.created",
        "risk.check.completed",
        "policy.decision.made",
        "order.intent.created",
        "order.submitted",
        "order.filled",
        "order.filled",
    ]
    assert summary["filled_event_count"] == 2
    assert health.partial_fill_events == 1


def test_append_only_journal_records_reject_event(tmp_path: Path) -> None:
    proposal, risk_result = _approved_breakout_flow()
    simulator = PaperExecutionSimulator(PaperExecutionConfig(min_notional_usd=1_000_000.0))
    report = simulator.submit(risk_result)
    events = build_execution_events("run-456", proposal, risk_result, report)
    journal = AppendOnlyJournal(tmp_path / "rejects.jsonl")

    for event in events:
        journal.append(event)

    read_back = journal.read_all()
    summary = build_review_packet(read_back)

    assert any(event.event_type.value == "order.rejected" for event in read_back)
    assert summary["rejected_event_count"] == 1
