from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from crypto_agent.llm.analyst import LLMOutputError


class ReviewFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Literal["process", "slippage", "regime", "journaling", "execution"]
    severity: Literal["low", "medium", "high"]
    message: str = Field(min_length=1)
    evidence_event_types: list[str] = Field(min_length=1)


class ReviewSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    authority: Literal["advisory_only"]
    run_id: str
    summary: str = Field(min_length=1)
    findings: list[ReviewFinding] = Field(default_factory=list)
    policy_violations: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)


def parse_review_output(raw_output: str) -> ReviewSummary:
    try:
        payload = json.loads(raw_output)
    except json.JSONDecodeError as exc:
        raise LLMOutputError("Review output is not valid JSON.") from exc

    try:
        review = ReviewSummary.model_validate(payload)
    except ValidationError as exc:
        raise LLMOutputError("Review output failed schema validation.") from exc

    if review.authority != "advisory_only":
        raise LLMOutputError("Review output attempted to exceed advisory-only authority.")

    return review
