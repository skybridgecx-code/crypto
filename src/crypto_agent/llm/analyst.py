from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from crypto_agent.evaluation.models import ReplayResult


class LLMOutputError(ValueError):
    """Raised when an advisory model output is malformed or unsafe to trust."""


class AnalystCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    rank: int = Field(ge=1)
    summary: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    invalidation_reason: str = Field(min_length=1)
    evidence_event_types: list[str] = Field(min_length=1)


class AnalystAdvisory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["advisory_only"]
    run_id: str
    overall_summary: str = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    candidates: list[AnalystCandidate] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def build_analyst_context(replay_result: ReplayResult) -> dict[str, Any]:
    return {
        "run_id": replay_result.scorecard.run_id,
        "scorecard": replay_result.scorecard.model_dump(mode="json"),
        "review_packet": {
            "event_count": len(replay_result.events),
            "event_types": [event.event_type.value for event in replay_result.events],
        },
        "proposals": [
            {
                "proposal_id": str(event.payload["proposal_id"]),
                "strategy_id": event.strategy_id,
                "symbol": event.symbol,
                "confidence": event.payload.get("confidence"),
            }
            for event in replay_result.events
            if event.event_type.value == "trade.proposal.created"
        ],
    }


def parse_analyst_output(raw_output: str) -> AnalystAdvisory:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise LLMOutputError("Analyst output is not valid JSON.") from exc

    try:
        advisory = AnalystAdvisory.model_validate(payload)
    except ValidationError as exc:
        raise LLMOutputError("Analyst output failed schema validation.") from exc

    if advisory.authority != "advisory_only":
        raise LLMOutputError("Analyst output attempted to exceed advisory-only authority.")

    return advisory
