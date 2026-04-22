from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ExternalDirectionalBias = Literal["buy", "sell", "neutral"]


class ExternalConfirmationArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_kind: Literal["external_confirmation_advisory_v1"] = (
        "external_confirmation_advisory_v1"
    )
    source_system: str = Field(min_length=1)
    asset: str = Field(min_length=1)
    directional_bias: ExternalDirectionalBias
    confidence_adjustment: float = Field(ge=-0.5, le=0.5)
    veto_trade: bool = False
    rationale: str = Field(min_length=1)
    supporting_tags: list[str] = Field(default_factory=list)
    observed_at_epoch_ns: int = Field(ge=0)
    correlation_id: str | None = None

    @field_validator("source_system", "asset", "rationale", mode="before")
    @classmethod
    def _normalize_required_text(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("must_be_string")
        normalized = value.strip()
        if not normalized:
            raise ValueError("must_be_non_empty")
        return normalized

    @field_validator("supporting_tags", mode="before")
    @classmethod
    def _normalize_supporting_tags(cls, value: object) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValueError("supporting_tags_must_be_list")
        normalized: list[str] = []
        for raw in value:
            if not isinstance(raw, str):
                raise ValueError("supporting_tags_must_be_string")
            token = raw.strip()
            if not token or token in normalized:
                continue
            normalized.append(token)
        return normalized


class ExternalConfirmationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision_kind: Literal["external_confirmation_decision_v1"] = (
        "external_confirmation_decision_v1"
    )
    status: Literal[
        "no_artifact",
        "ignored_asset_mismatch",
        "ignored_neutral",
        "boosted_confirmation",
        "penalized_conflict",
        "vetoed_conflict",
        "vetoed_neutral",
    ]
    source_system: str
    asset: str
    proposal_symbol: str
    proposal_side: Literal["buy", "sell"]
    directional_bias: ExternalDirectionalBias
    confidence_before: float = Field(ge=0, le=1)
    confidence_after: float = Field(ge=0, le=1)
    applied_confidence_delta: float = Field(ge=-1, le=1)
    veto_trade: bool
    rationale: str
    supporting_tags: list[str] = Field(default_factory=list)
    observed_at_epoch_ns: int = Field(ge=0)
    correlation_id: str | None = None
