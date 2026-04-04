from __future__ import annotations

from crypto_agent.config import Settings
from crypto_agent.enums import Mode, PolicyAction
from crypto_agent.policy.kill_switch import KillSwitchState
from crypto_agent.types import PolicyDecision, TradeProposal


def apply_policy_guardrails(
    proposal: TradeProposal,
    settings: Settings,
    kill_switch: KillSwitchState,
    approved_notional_usd: float | None,
) -> PolicyDecision | None:
    if kill_switch.active:
        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            action=PolicyAction.HALT,
            reason_codes=["kill_switch_active", *kill_switch.reason_codes],
            summary="Kill switch active. New trade decisions are halted.",
            mode=settings.mode,
        )

    if settings.mode is Mode.RESEARCH_ONLY:
        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            action=PolicyAction.DENY,
            reason_codes=["mode_research_only"],
            summary="Research-only mode does not permit order approval.",
            mode=settings.mode,
        )

    if settings.mode is Mode.HALTED:
        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            action=PolicyAction.HALT,
            reason_codes=["mode_halted"],
            summary="System mode is halted. New trade decisions are blocked.",
            mode=settings.mode,
        )

    if settings.mode is Mode.LIMITED_LIVE and not settings.policy.allow_live_orders:
        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            action=PolicyAction.DENY,
            reason_codes=["live_orders_disabled"],
            summary="Limited live mode is configured but live orders are disabled.",
            mode=settings.mode,
        )

    if (
        settings.mode is Mode.LIMITED_LIVE
        and approved_notional_usd is not None
        and approved_notional_usd > settings.policy.require_manual_approval_above_notional_usd
        and settings.policy.require_manual_approval_above_notional_usd > 0
    ):
        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            action=PolicyAction.DENY,
            reason_codes=["manual_approval_required"],
            summary="Proposal exceeds notional threshold requiring manual approval.",
            mode=settings.mode,
        )

    if approved_notional_usd is not None and approved_notional_usd <= 0:
        return PolicyDecision(
            proposal_id=proposal.proposal_id,
            action=PolicyAction.DENY,
            reason_codes=["non_positive_approved_notional"],
            summary="Approved notional must be positive.",
            mode=settings.mode,
        )
    return None
