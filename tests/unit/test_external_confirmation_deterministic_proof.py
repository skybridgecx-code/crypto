from __future__ import annotations

from pathlib import Path

import pytest

from crypto_agent.cli.main import _boosted_external_confirmation_size_multiplier
from crypto_agent.config import load_settings
from crypto_agent.enums import Side
from crypto_agent.execution.simulator import PaperExecutionSimulator
from crypto_agent.external_signals.loader import (
    apply_external_confirmation_to_proposal,
    load_external_confirmation_artifact,
)
from crypto_agent.external_signals.models import ExternalConfirmationArtifact
from crypto_agent.portfolio.positions import PortfolioState
from crypto_agent.risk.checks import evaluate_trade_proposal
from crypto_agent.risk.sizing import size_trade_proposal
from crypto_agent.types import ExecutionConstraints, TradeProposal

FIXTURES_DIR = Path("tests/fixtures")


def _base_proposal() -> TradeProposal:
    return TradeProposal(
        proposal_id="proposal-deterministic-proof",
        strategy_id="breakout_v1",
        symbol="BTCUSDT",
        side=Side.BUY,
        confidence=0.6,
        thesis="Deterministic proposal for advisory proof.",
        entry_reference=100.0,
        stop_price=95.0,
        take_profit_price=110.0,
        expected_holding_period="2h",
        invalidation_reason="Momentum break invalidates setup.",
        supporting_features={"baseline_metric": 1.0},
        regime_context={"label": "TREND", "confidence": 0.8},
        execution_constraints=ExecutionConstraints(max_slippage_bps=15.0, max_spread_bps=10.0),
    )


def _xrp_mean_reversion_proposal() -> TradeProposal:
    return TradeProposal(
        proposal_id="proposal-xrp-mean-reversion-proof",
        strategy_id="mean_reversion_v1",
        symbol="XRPUSD",
        side=Side.BUY,
        confidence=0.55,
        thesis="XRP range mean-reversion deterministic proof proposal.",
        entry_reference=0.60,
        stop_price=0.57,
        take_profit_price=0.63,
        expected_holding_period="2h",
        invalidation_reason="Range breakdown invalidates setup.",
        supporting_features={
            "average_dollar_volume": 250_000.0,
            "atr_pct": 0.0018,
            "realized_volatility": 0.0015,
        },
        regime_context={"label": "RANGE", "confidence": 0.8},
        execution_constraints=ExecutionConstraints(
            max_slippage_bps=10.0,
            max_spread_bps=8.0,
            min_notional_usd=10.0,
        ),
    )


def _paper_settings_with_xrp_allowlist():
    base = load_settings(Path("config/paper.yaml"))
    return base.model_copy(
        update={
            "venue": base.venue.model_copy(update={"allowed_symbols": ["XRPUSD"]}),
            "risk": base.risk.model_copy(update={"min_average_dollar_volume_usd": 150_000.0}),
        }
    )


def _artifact(
    *,
    asset: str,
    directional_bias: str,
    confidence_adjustment: float,
    veto_trade: bool,
) -> ExternalConfirmationArtifact:
    return ExternalConfirmationArtifact(
        source_system="omega_fusion_engine",
        asset=asset,
        directional_bias=directional_bias,  # type: ignore[arg-type]
        confidence_adjustment=confidence_adjustment,
        veto_trade=veto_trade,
        rationale="Deterministic advisory proof artifact.",
        supporting_tags=["proof", "deterministic"],
        observed_at_epoch_ns=1700000000000000123,
        correlation_id="omega_fused_proof",
    )


def test_no_advisory_leaves_proposal_unchanged() -> None:
    proposal = _base_proposal()
    # No advisory path: proposal is evaluated unchanged.
    assert proposal.confidence == 0.6
    assert proposal.supporting_features == {"baseline_metric": 1.0}
    assert proposal.regime_context == {"label": "TREND", "confidence": 0.8}


def test_confirming_advisory_applies_bounded_confidence_increase_and_observability() -> None:
    proposal = _base_proposal()
    adjusted, decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="BTCUSDT",
            directional_bias="buy",
            confidence_adjustment=0.2,
            veto_trade=False,
        ),
    )

    assert adjusted is not None
    assert decision.status == "boosted_confirmation"
    assert decision.proposal_symbol == "BTCUSDT"
    assert decision.source_system == "omega_fusion_engine"
    assert decision.observed_at_epoch_ns == 1700000000000000123
    assert adjusted.confidence == pytest.approx(0.8)
    assert adjusted.supporting_features["external_confirmation_status"] == "boosted_confirmation"
    assert adjusted.regime_context["external_confirmation_status"] == "boosted_confirmation"


def test_conflicting_advisory_applies_penalty_and_observability() -> None:
    proposal = _base_proposal()
    adjusted, decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="BTCUSDT",
            directional_bias="sell",
            confidence_adjustment=0.15,
            veto_trade=False,
        ),
    )

    assert adjusted is not None
    assert decision.status == "penalized_conflict"
    assert decision.proposal_symbol == "BTCUSDT"
    assert decision.source_system == "omega_fusion_engine"
    assert adjusted.confidence == pytest.approx(0.45)
    assert adjusted.supporting_features["external_confirmation_status"] == "penalized_conflict"
    assert adjusted.regime_context["external_confirmation_status"] == "penalized_conflict"


def test_veto_advisory_drops_proposal_and_records_veto_decision() -> None:
    proposal = _base_proposal()
    adjusted, decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="BTCUSDT",
            directional_bias="sell",
            confidence_adjustment=0.1,
            veto_trade=True,
        ),
    )

    assert adjusted is None
    assert decision.status == "vetoed_conflict"
    assert decision.veto_trade is True
    assert decision.proposal_symbol == "BTCUSDT"
    assert decision.source_system == "omega_fusion_engine"


def test_asset_mismatch_is_ignored_with_decision_and_no_proposal_mutation() -> None:
    proposal = _base_proposal()
    adjusted, decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="ETHUSDT",
            directional_bias="buy",
            confidence_adjustment=0.2,
            veto_trade=False,
        ),
    )

    assert adjusted is proposal
    assert decision.status == "ignored_asset_mismatch"
    assert decision.proposal_symbol == "BTCUSDT"
    assert decision.source_system == "omega_fusion_engine"
    assert adjusted.confidence == 0.6
    assert "external_confirmation_status" not in adjusted.supporting_features
    assert "external_confirmation_status" not in adjusted.regime_context


def test_omega_fixture_loader_to_proposal_seam_proof() -> None:
    proposal = _base_proposal()
    artifact = load_external_confirmation_artifact(
        FIXTURES_DIR / "external_confirmation_omega_emitted_btc_buy.json"
    )

    assert artifact is not None
    assert artifact.artifact_kind == "external_confirmation_advisory_v1"
    assert artifact.asset == "BTCUSDT"
    assert artifact.directional_bias == "buy"
    assert artifact.confidence_adjustment == pytest.approx(0.18)
    assert artifact.veto_trade is False
    assert artifact.source_system == "omega_fusion_engine"
    assert artifact.supporting_tags == [
        "omega",
        "advisory_only",
        "posture:strong_long",
        "venue:binance",
        "directional_bias:buy",
        "cross_venue_confirmed",
        "exogenous_net:risk_on",
    ]

    adjusted, decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=artifact,
    )

    assert adjusted is not None
    assert decision.status == "boosted_confirmation"
    assert adjusted.confidence == pytest.approx(0.78)
    assert decision.asset == "BTCUSDT"
    assert decision.directional_bias == "buy"
    assert decision.applied_confidence_delta == pytest.approx(0.18)
    assert decision.veto_trade is False
    assert decision.source_system == "omega_fusion_engine"
    assert decision.supporting_tags == artifact.supporting_tags
    assert (
        adjusted.supporting_features["external_confirmation_source_system"] == "omega_fusion_engine"
    )
    assert adjusted.supporting_features["external_confirmation_supporting_tags"] == ",".join(
        artifact.supporting_tags
    )


def test_boosted_confirmation_is_execution_neutral_for_xrp_style_mean_reversion() -> None:
    settings = _paper_settings_with_xrp_allowlist()
    portfolio = PortfolioState(equity_usd=100_000.0, available_cash_usd=100_000.0)
    proposal = _xrp_mean_reversion_proposal()
    boosted_proposal, external_decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="XRPUSD",
            directional_bias="buy",
            confidence_adjustment=0.2,
            veto_trade=False,
        ),
    )

    assert boosted_proposal is not None
    assert external_decision.status == "boosted_confirmation"
    assert boosted_proposal.confidence == pytest.approx(0.75)
    assert proposal.confidence == pytest.approx(0.55)

    baseline_risk = evaluate_trade_proposal(proposal, portfolio, settings)
    boosted_risk = evaluate_trade_proposal(boosted_proposal, portfolio, settings)
    assert baseline_risk.decision.action == boosted_risk.decision.action
    assert baseline_risk.decision.reason_codes == boosted_risk.decision.reason_codes
    assert baseline_risk.sizing is not None
    assert boosted_risk.sizing is not None
    assert baseline_risk.sizing.approved_notional_usd == pytest.approx(
        boosted_risk.sizing.approved_notional_usd
    )
    assert baseline_risk.sizing.quantity == pytest.approx(boosted_risk.sizing.quantity)

    baseline_report = PaperExecutionSimulator().submit(baseline_risk)
    boosted_report = PaperExecutionSimulator().submit(boosted_risk)
    assert baseline_report.rejected == boosted_report.rejected
    assert baseline_report.reject_reason == boosted_report.reject_reason
    assert len(baseline_report.fills) == len(boosted_report.fills)
    assert sum(fill.notional_usd for fill in baseline_report.fills) == pytest.approx(
        sum(fill.notional_usd for fill in boosted_report.fills)
    )


def test_boosted_size_multiplier_deterministically_increases_only_boosted_sizing() -> None:
    settings = _paper_settings_with_xrp_allowlist()
    portfolio = PortfolioState(equity_usd=100_000.0, available_cash_usd=100_000.0)
    proposal = _xrp_mean_reversion_proposal()
    baseline_risk = evaluate_trade_proposal(proposal, portfolio, settings)
    assert baseline_risk.sizing is not None

    boosted_proposal, boosted_decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="XRPUSD",
            directional_bias="buy",
            confidence_adjustment=0.2,
            veto_trade=False,
        ),
    )
    assert boosted_proposal is not None
    assert boosted_decision.status == "boosted_confirmation"

    boosted_1x_risk = evaluate_trade_proposal(
        boosted_proposal,
        portfolio,
        settings,
        sizing_notional_multiplier=_boosted_external_confirmation_size_multiplier(
            proposal=boosted_proposal,
            configured_multiplier=1.0,
        ),
    )
    boosted_125x_risk = evaluate_trade_proposal(
        boosted_proposal,
        portfolio,
        settings,
        sizing_notional_multiplier=_boosted_external_confirmation_size_multiplier(
            proposal=boosted_proposal,
            configured_multiplier=1.25,
        ),
    )
    assert boosted_1x_risk.sizing is not None
    assert boosted_125x_risk.sizing is not None
    assert boosted_1x_risk.sizing.approved_notional_usd == pytest.approx(
        baseline_risk.sizing.approved_notional_usd
    )
    assert boosted_1x_risk.sizing.quantity == pytest.approx(baseline_risk.sizing.quantity)
    assert boosted_125x_risk.sizing.approved_notional_usd == pytest.approx(
        baseline_risk.sizing.approved_notional_usd * 1.25
    )
    assert boosted_125x_risk.sizing.quantity == pytest.approx(baseline_risk.sizing.quantity * 1.25)

    penalized_proposal, penalized_decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="XRPUSD",
            directional_bias="sell",
            confidence_adjustment=0.2,
            veto_trade=False,
        ),
    )
    assert penalized_proposal is not None
    assert penalized_decision.status == "penalized_conflict"
    penalized_risk = evaluate_trade_proposal(
        penalized_proposal,
        portfolio,
        settings,
        sizing_notional_multiplier=_boosted_external_confirmation_size_multiplier(
            proposal=penalized_proposal,
            configured_multiplier=1.25,
        ),
    )
    assert penalized_risk.sizing is not None
    assert penalized_risk.sizing.approved_notional_usd == pytest.approx(
        baseline_risk.sizing.approved_notional_usd
    )
    assert penalized_risk.sizing.quantity == pytest.approx(baseline_risk.sizing.quantity)

    mismatched_proposal, mismatch_decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="BTCUSD",
            directional_bias="buy",
            confidence_adjustment=0.2,
            veto_trade=False,
        ),
    )
    assert mismatched_proposal is not None
    assert mismatch_decision.status == "ignored_asset_mismatch"
    mismatch_risk = evaluate_trade_proposal(
        mismatched_proposal,
        portfolio,
        settings,
        sizing_notional_multiplier=_boosted_external_confirmation_size_multiplier(
            proposal=mismatched_proposal,
            configured_multiplier=1.25,
        ),
    )
    assert mismatch_risk.sizing is not None
    assert mismatch_risk.sizing.approved_notional_usd == pytest.approx(
        baseline_risk.sizing.approved_notional_usd
    )
    assert mismatch_risk.sizing.quantity == pytest.approx(baseline_risk.sizing.quantity)

    vetoed_proposal, veto_decision = apply_external_confirmation_to_proposal(
        proposal=proposal,
        artifact=_artifact(
            asset="XRPUSD",
            directional_bias="sell",
            confidence_adjustment=0.2,
            veto_trade=True,
        ),
    )
    assert vetoed_proposal is None
    assert veto_decision.status == "vetoed_conflict"


def test_boosted_size_multiplier_is_bounded_to_safe_range() -> None:
    settings = _paper_settings_with_xrp_allowlist()
    portfolio = PortfolioState(equity_usd=100_000.0, available_cash_usd=100_000.0)
    proposal = _xrp_mean_reversion_proposal()

    assert (
        size_trade_proposal(
            proposal,
            portfolio,
            settings,
            notional_multiplier=1.0,
        ).approved_notional_usd
        > 0
    )
    assert (
        size_trade_proposal(
            proposal,
            portfolio,
            settings,
            notional_multiplier=1.5,
        ).approved_notional_usd
        > 0
    )
    with pytest.raises(ValueError, match="between 1.0 and 1.5"):
        size_trade_proposal(proposal, portfolio, settings, notional_multiplier=0.99)
    with pytest.raises(ValueError, match="between 1.0 and 1.5"):
        size_trade_proposal(proposal, portfolio, settings, notional_multiplier=1.51)
