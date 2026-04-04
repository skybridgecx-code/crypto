from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.policy.kill_switch import KillSwitchContext, evaluate_kill_switch
from crypto_agent.portfolio.positions import PortfolioState, Position
from crypto_agent.regime.rules import classify_regime
from crypto_agent.risk.checks import evaluate_trade_proposal
from crypto_agent.signals.breakout import generate_breakout_proposal

FIXTURES_DIR = Path("tests/fixtures")


def _paper_settings():
    return load_settings(Path("config/paper.yaml"))


def _breakout_proposal():
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_breakout_long.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)
    regime = classify_regime(features)
    proposal = generate_breakout_proposal(candles, features, regime)
    assert proposal is not None
    return proposal


def test_evaluate_trade_proposal_allows_within_limits() -> None:
    settings = _paper_settings()
    portfolio = PortfolioState(
        equity_usd=100_000.0,
        available_cash_usd=100_000.0,
        daily_realized_pnl_usd=0.0,
    )

    result = evaluate_trade_proposal(_breakout_proposal(), portfolio, settings)

    assert result.decision.action.value == "allow"
    assert result.sizing is not None
    assert result.sizing.quantity > 0


def test_evaluate_trade_proposal_denies_daily_loss_breach() -> None:
    settings = _paper_settings()
    portfolio = PortfolioState(
        equity_usd=100_000.0,
        available_cash_usd=100_000.0,
        daily_realized_pnl_usd=-2_000.0,
    )

    result = evaluate_trade_proposal(_breakout_proposal(), portfolio, settings)

    assert result.decision.action.value == "deny"
    assert "daily_loss_limit_breached" in result.rejection_reasons


def test_evaluate_trade_proposal_denies_symbol_exposure_limit() -> None:
    settings = _paper_settings()
    portfolio = PortfolioState(
        equity_usd=100_000.0,
        available_cash_usd=10_000.0,
        positions=[
            Position(
                symbol="BTCUSDT",
                quantity=0.60,
                entry_price=68_000.0,
                mark_price=68_000.0,
            )
        ],
    )

    result = evaluate_trade_proposal(_breakout_proposal(), portfolio, settings)

    assert result.decision.action.value == "deny"
    assert "symbol_exposure_limit_reached" in result.rejection_reasons


def test_evaluate_trade_proposal_halts_when_kill_switch_active() -> None:
    settings = _paper_settings()
    portfolio = PortfolioState(
        equity_usd=100_000.0,
        available_cash_usd=100_000.0,
    )
    kill_switch_context = KillSwitchContext(manual_halt=True)

    result = evaluate_trade_proposal(
        _breakout_proposal(),
        portfolio,
        settings,
        kill_switch_context=kill_switch_context,
    )

    assert result.decision.action.value == "halt"
    assert "kill_switch_active" in result.rejection_reasons


def test_kill_switch_detects_repeated_rejects() -> None:
    settings = _paper_settings()

    state = evaluate_kill_switch(
        KillSwitchContext(consecutive_order_rejects=3),
        settings,
    )

    assert state.active is True
    assert "repeated_order_rejects" in state.reason_codes


def test_research_only_mode_denies_orders() -> None:
    settings = load_settings(Path("config/default.yaml"))
    portfolio = PortfolioState(
        equity_usd=100_000.0,
        available_cash_usd=100_000.0,
    )

    result = evaluate_trade_proposal(_breakout_proposal(), portfolio, settings)

    assert result.decision.action.value == "deny"
    assert "mode_research_only" in result.rejection_reasons
