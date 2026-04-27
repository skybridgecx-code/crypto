from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from crypto_agent.enums import Side
from crypto_agent.external_signals.models import (
    ExternalConfirmationArtifact,
    ExternalConfirmationDecision,
)
from crypto_agent.types import TradeProposal

_DEFAULT_CONFLICT_PENALTY = 0.1


def load_external_confirmation_artifact(
    path: str | Path | None,
) -> ExternalConfirmationArtifact | None:
    if path is None:
        return None
    artifact_path = Path(path).resolve()
    if not artifact_path.is_file():
        raise ValueError(f"external_confirmation_artifact_missing:{artifact_path}")
    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"external_confirmation_artifact_invalid_json:{artifact_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"external_confirmation_artifact_invalid_object:{artifact_path}")
    try:
        return ExternalConfirmationArtifact.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"external_confirmation_artifact_invalid_shape:{exc}") from exc


def apply_external_confirmation_to_proposal(
    *,
    proposal: TradeProposal,
    artifact: ExternalConfirmationArtifact,
) -> tuple[TradeProposal | None, ExternalConfirmationDecision]:
    proposal_symbol = proposal.symbol.upper()
    artifact_asset = artifact.asset.upper()
    proposal_side: Literal["buy", "sell"] = "buy" if proposal.side is Side.BUY else "sell"
    confidence_before = proposal.confidence

    if artifact_asset != proposal_symbol:
        decision = ExternalConfirmationDecision(
            status="ignored_asset_mismatch",
            source_system=artifact.source_system,
            asset=artifact_asset,
            proposal_symbol=proposal_symbol,
            proposal_side=proposal_side,
            directional_bias=artifact.directional_bias,
            confidence_before=confidence_before,
            confidence_after=confidence_before,
            applied_confidence_delta=0.0,
            veto_trade=artifact.veto_trade,
            rationale=artifact.rationale,
            supporting_tags=artifact.supporting_tags,
            observed_at_epoch_ns=artifact.observed_at_epoch_ns,
            correlation_id=artifact.correlation_id,
        )
        return proposal, decision

    if artifact.directional_bias == "neutral":
        if artifact.veto_trade:
            decision = ExternalConfirmationDecision(
                status="vetoed_neutral",
                source_system=artifact.source_system,
                asset=artifact_asset,
                proposal_symbol=proposal_symbol,
                proposal_side=proposal_side,
                directional_bias=artifact.directional_bias,
                confidence_before=confidence_before,
                confidence_after=0.0,
                applied_confidence_delta=-confidence_before,
                veto_trade=True,
                rationale=artifact.rationale,
                supporting_tags=artifact.supporting_tags,
                observed_at_epoch_ns=artifact.observed_at_epoch_ns,
                correlation_id=artifact.correlation_id,
            )
            return None, decision
        decision = ExternalConfirmationDecision(
            status="ignored_neutral",
            source_system=artifact.source_system,
            asset=artifact_asset,
            proposal_symbol=proposal_symbol,
            proposal_side=proposal_side,
            directional_bias=artifact.directional_bias,
            confidence_before=confidence_before,
            confidence_after=confidence_before,
            applied_confidence_delta=0.0,
            veto_trade=False,
            rationale=artifact.rationale,
            supporting_tags=artifact.supporting_tags,
            observed_at_epoch_ns=artifact.observed_at_epoch_ns,
            correlation_id=artifact.correlation_id,
        )
        return proposal, decision

    confirms_direction = (artifact.directional_bias == "buy" and proposal.side is Side.BUY) or (
        artifact.directional_bias == "sell" and proposal.side is Side.SELL
    )

    if confirms_direction:
        boost = max(0.0, artifact.confidence_adjustment)
        boosted_confidence = min(1.0, confidence_before + boost)
        applied_delta = boosted_confidence - confidence_before
        decision = ExternalConfirmationDecision(
            status="boosted_confirmation",
            source_system=artifact.source_system,
            asset=artifact_asset,
            proposal_symbol=proposal_symbol,
            proposal_side=proposal_side,
            directional_bias=artifact.directional_bias,
            confidence_before=confidence_before,
            confidence_after=boosted_confidence,
            applied_confidence_delta=applied_delta,
            veto_trade=False,
            rationale=artifact.rationale,
            supporting_tags=artifact.supporting_tags,
            observed_at_epoch_ns=artifact.observed_at_epoch_ns,
            correlation_id=artifact.correlation_id,
        )
        return _proposal_with_external_decision(proposal=proposal, decision=decision), decision

    if artifact.veto_trade:
        decision = ExternalConfirmationDecision(
            status="vetoed_conflict",
            source_system=artifact.source_system,
            asset=artifact_asset,
            proposal_symbol=proposal_symbol,
            proposal_side=proposal_side,
            directional_bias=artifact.directional_bias,
            confidence_before=confidence_before,
            confidence_after=0.0,
            applied_confidence_delta=-confidence_before,
            veto_trade=True,
            rationale=artifact.rationale,
            supporting_tags=artifact.supporting_tags,
            observed_at_epoch_ns=artifact.observed_at_epoch_ns,
            correlation_id=artifact.correlation_id,
        )
        return None, decision

    penalty = max(abs(artifact.confidence_adjustment), _DEFAULT_CONFLICT_PENALTY)
    penalized_confidence = max(0.0, confidence_before - penalty)
    applied_delta = penalized_confidence - confidence_before
    decision = ExternalConfirmationDecision(
        status="penalized_conflict",
        source_system=artifact.source_system,
        asset=artifact_asset,
        proposal_symbol=proposal_symbol,
        proposal_side=proposal_side,
        directional_bias=artifact.directional_bias,
        confidence_before=confidence_before,
        confidence_after=penalized_confidence,
        applied_confidence_delta=applied_delta,
        veto_trade=False,
        rationale=artifact.rationale,
        supporting_tags=artifact.supporting_tags,
        observed_at_epoch_ns=artifact.observed_at_epoch_ns,
        correlation_id=artifact.correlation_id,
    )
    return _proposal_with_external_decision(proposal=proposal, decision=decision), decision


def _proposal_with_external_decision(
    *,
    proposal: TradeProposal,
    decision: ExternalConfirmationDecision,
) -> TradeProposal:
    supporting_features = dict(proposal.supporting_features)
    supporting_features.update(
        {
            "external_confirmation_applied": True,
            "external_confirmation_status": decision.status,
            "external_confirmation_source_system": decision.source_system,
            "external_confirmation_asset": decision.asset,
            "external_confirmation_confidence_delta": decision.applied_confidence_delta,
            "external_confirmation_veto_trade": decision.veto_trade,
            "external_confirmation_observed_at_epoch_ns": decision.observed_at_epoch_ns,
            "external_confirmation_rationale": decision.rationale,
            "external_confirmation_supporting_tags": ",".join(decision.supporting_tags),
            "external_confirmation_correlation_id": decision.correlation_id or "",
        }
    )
    regime_context = dict(proposal.regime_context)
    regime_context["external_confirmation_status"] = decision.status
    regime_context["external_confirmation_source_system"] = decision.source_system
    return proposal.model_copy(
        update={
            "confidence": decision.confidence_after,
            "supporting_features": supporting_features,
            "regime_context": regime_context,
        }
    )
