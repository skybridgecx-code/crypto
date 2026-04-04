from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.config import Settings
from crypto_agent.enums import PolicyAction
from crypto_agent.policy.guardrails import apply_policy_guardrails
from crypto_agent.policy.kill_switch import KillSwitchContext, evaluate_kill_switch
from crypto_agent.portfolio.positions import PortfolioState
from crypto_agent.risk.limits import collect_limit_breaches
from crypto_agent.risk.sizing import SizingResult, size_trade_proposal
from crypto_agent.types import PolicyDecision, TradeProposal


class RiskCheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal: TradeProposal
    decision: PolicyDecision
    sizing: SizingResult | None = None
    rejection_reasons: list[str] = Field(default_factory=list)


def evaluate_trade_proposal(
    proposal: TradeProposal,
    portfolio: PortfolioState,
    settings: Settings,
    kill_switch_context: KillSwitchContext | None = None,
) -> RiskCheckResult:
    kill_switch = evaluate_kill_switch(kill_switch_context or KillSwitchContext(), settings)
    guardrail_decision = apply_policy_guardrails(proposal, settings, kill_switch, None)
    if guardrail_decision is not None:
        return RiskCheckResult(
            proposal=proposal,
            decision=guardrail_decision,
            rejection_reasons=guardrail_decision.reason_codes,
        )

    limit_breaches = collect_limit_breaches(proposal, portfolio, settings)
    if limit_breaches:
        decision = PolicyDecision(
            proposal_id=proposal.proposal_id,
            action=PolicyAction.DENY,
            reason_codes=limit_breaches,
            summary="Proposal rejected by deterministic hard limits.",
            mode=settings.mode,
        )
        return RiskCheckResult(
            proposal=proposal,
            decision=decision,
            rejection_reasons=limit_breaches,
        )

    try:
        sizing = size_trade_proposal(proposal, portfolio, settings)
    except ValueError as exc:
        decision = PolicyDecision(
            proposal_id=proposal.proposal_id,
            action=PolicyAction.DENY,
            reason_codes=["no_risk_capacity"],
            summary=str(exc),
            mode=settings.mode,
        )
        return RiskCheckResult(
            proposal=proposal,
            decision=decision,
            rejection_reasons=["no_risk_capacity"],
        )

    guardrail_decision = apply_policy_guardrails(
        proposal,
        settings,
        kill_switch,
        sizing.approved_notional_usd,
    )
    if guardrail_decision is not None:
        return RiskCheckResult(
            proposal=proposal,
            decision=guardrail_decision,
            sizing=sizing,
            rejection_reasons=guardrail_decision.reason_codes,
        )

    decision = PolicyDecision(
        proposal_id=proposal.proposal_id,
        action=PolicyAction.ALLOW,
        reason_codes=["within_limits"],
        summary="Proposal approved within current risk and policy bounds.",
        mode=settings.mode,
        approved_notional_usd=sizing.approved_notional_usd,
    )
    return RiskCheckResult(proposal=proposal, decision=decision, sizing=sizing)
