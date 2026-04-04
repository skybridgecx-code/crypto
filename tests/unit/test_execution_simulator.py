from pathlib import Path

import pytest
from crypto_agent.config import load_settings
from crypto_agent.execution.models import PaperExecutionConfig
from crypto_agent.execution.order_normalizer import normalize_order_intent
from crypto_agent.execution.router import ExecutionRouter
from crypto_agent.execution.simulator import PaperExecutionSimulator
from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.portfolio.positions import PortfolioState
from crypto_agent.regime.rules import classify_regime
from crypto_agent.risk.checks import evaluate_trade_proposal
from crypto_agent.signals.breakout import generate_breakout_proposal

FIXTURES_DIR = Path("tests/fixtures")


def _approved_breakout_risk_result():
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
    result = evaluate_trade_proposal(proposal, portfolio, settings)
    assert result.decision.action.value == "allow"
    assert result.sizing is not None
    return result


def test_normalize_order_intent_uses_deterministic_intent_id() -> None:
    risk_result = _approved_breakout_risk_result()

    first = normalize_order_intent(risk_result)
    second = normalize_order_intent(risk_result)

    assert first.intent_id == second.intent_id
    assert first.quantity == second.quantity
    assert first.proposal_id == risk_result.proposal.proposal_id


def test_paper_execution_simulator_returns_full_fill_for_small_order() -> None:
    risk_result = _approved_breakout_risk_result()
    simulator = PaperExecutionSimulator(
        PaperExecutionConfig(partial_fill_notional_threshold=1_000_000.0)
    )

    report = simulator.submit(risk_result)

    assert report.rejected is False
    assert len(report.fills) == 1
    assert report.fills[0].status.value == "filled"


def test_paper_execution_simulator_returns_partial_fill_for_large_order() -> None:
    risk_result = _approved_breakout_risk_result()
    simulator = PaperExecutionSimulator(
        PaperExecutionConfig(partial_fill_notional_threshold=1_000.0, partial_fill_fraction=0.6)
    )

    report = simulator.submit(risk_result)

    assert report.rejected is False
    assert len(report.fills) == 2
    assert report.fills[0].status.value == "partially_filled"
    assert report.fills[1].status.value == "filled"
    assert pytest.approx(sum(fill.quantity for fill in report.fills)) == report.intent.quantity


def test_paper_execution_simulator_is_idempotent() -> None:
    risk_result = _approved_breakout_risk_result()
    simulator = PaperExecutionSimulator()

    first = simulator.submit(risk_result)
    second = simulator.submit(risk_result)

    assert first == second
    assert first.intent.intent_id == second.intent.intent_id


def test_paper_execution_simulator_rejects_when_min_notional_not_met() -> None:
    risk_result = _approved_breakout_risk_result()
    simulator = PaperExecutionSimulator(PaperExecutionConfig(min_notional_usd=1_000_000.0))

    report = simulator.submit(risk_result)

    assert report.rejected is True
    assert report.reject_reason == "min_notional_not_met"
    assert report.fills == []


def test_paper_execution_simulator_rejects_when_slippage_limit_too_low() -> None:
    risk_result = _approved_breakout_risk_result()
    risk_result.proposal.execution_constraints.max_slippage_bps = 0.1
    simulator = PaperExecutionSimulator()

    report = simulator.submit(risk_result)

    assert report.rejected is True
    assert report.reject_reason == "slippage_limit_exceeded"


def test_execution_router_allows_paper_mode_only() -> None:
    risk_result = _approved_breakout_risk_result()
    router = ExecutionRouter()

    report = router.execute(risk_result)

    assert report.rejected is False
    assert report.intent.mode.value == "paper"
