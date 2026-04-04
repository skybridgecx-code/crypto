from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.evaluation.scorecard import build_scorecard
from crypto_agent.events.journal import AppendOnlyJournal, build_execution_events
from crypto_agent.execution.models import PaperExecutionConfig
from crypto_agent.execution.simulator import PaperExecutionSimulator
from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.portfolio.positions import PortfolioState
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
    portfolio = PortfolioState(
        equity_usd=100_000.0,
        available_cash_usd=100_000.0,
        daily_realized_pnl_usd=0.0,
    )
    risk_result = evaluate_trade_proposal(proposal, portfolio, settings)
    assert risk_result.decision.action.value == "allow"
    return proposal, risk_result


def test_build_scorecard_counts_fill_sequence_correctly() -> None:
    proposal, risk_result = _approved_breakout_flow()
    simulator = PaperExecutionSimulator(
        PaperExecutionConfig(partial_fill_notional_threshold=1_000.0)
    )
    report = simulator.submit(risk_result)
    events = build_execution_events("run-scorecard", proposal, risk_result, report)

    scorecard = build_scorecard(events)

    assert scorecard.proposal_count == 1
    assert scorecard.approval_count == 1
    assert scorecard.order_intent_count == 1
    assert scorecard.orders_submitted_count == 1
    assert scorecard.fill_event_count == 2
    assert scorecard.partial_fill_intent_count == 1
    assert scorecard.complete_execution_count == 1
    assert scorecard.incomplete_execution_count == 0


def test_replay_journal_round_trips_order_and_scorecard(tmp_path: Path) -> None:
    proposal, risk_result = _approved_breakout_flow()
    simulator = PaperExecutionSimulator(
        PaperExecutionConfig(partial_fill_notional_threshold=1_000.0)
    )
    report = simulator.submit(risk_result)
    events = build_execution_events("run-replay", proposal, risk_result, report)
    journal_path = tmp_path / "replay.jsonl"
    journal = AppendOnlyJournal(journal_path)
    journal.append_many(events)

    replay_result = replay_journal(journal_path)

    assert [event.event_id for event in replay_result.events] == [
        event.event_id for event in events
    ]
    assert replay_result.scorecard.run_id == "run-replay"
    assert replay_result.scorecard.fill_event_count == 2


def test_build_scorecard_counts_reject_sequence_correctly() -> None:
    proposal, risk_result = _approved_breakout_flow()
    simulator = PaperExecutionSimulator(PaperExecutionConfig(min_notional_usd=1_000_000.0))
    report = simulator.submit(risk_result)
    events = build_execution_events("run-reject", proposal, risk_result, report)

    scorecard = build_scorecard(events)

    assert scorecard.proposal_count == 1
    assert scorecard.approval_count == 1
    assert scorecard.order_reject_count == 1
    assert scorecard.fill_event_count == 0
    assert scorecard.complete_execution_count == 1
    assert scorecard.incomplete_execution_count == 0
