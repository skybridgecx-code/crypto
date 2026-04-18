from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from crypto_agent.types import FillEvent, OrderIntent


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class PaperExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min_notional_usd: float = Field(default=10.0, ge=0)
    quantity_step: float = Field(default=0.000001, gt=0)
    price_tick: float = Field(default=0.01, gt=0)
    fee_bps: float = Field(default=2.0, ge=0)
    base_slippage_bps: float = Field(default=0.5, ge=0)
    partial_fill_notional_threshold: float = Field(default=10_000.0, gt=0)
    partial_fill_fraction: float = Field(default=0.6, gt=0, lt=1)


class ExecutionReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: OrderIntent
    fills: list[FillEvent] = Field(default_factory=list)
    rejected: bool = False
    reject_reason: str | None = None
    estimated_slippage_bps: float = Field(default=0.0, ge=0)


class VenueOrderRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    client_order_id: str
    venue: str
    execution_mode: Literal["shadow", "sandbox"]
    sandbox: bool
    proposal_id: str
    intent_id: str
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    reference_price: float = Field(gt=0)
    estimated_notional_usd: float = Field(gt=0)
    min_notional_usd: float = Field(ge=0)
    normalization_status: Literal["ready", "rejected"]
    normalization_reject_reason: str | None = None


class VenueExecutionAck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    client_order_id: str
    venue: str
    execution_mode: Literal["shadow", "sandbox"]
    sandbox: bool
    intent_id: str
    status: Literal["would_send", "accepted", "rejected", "duplicate"]
    venue_order_id: str | None = None
    reject_reason: str | None = None
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class VenueOrderState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    client_order_id: str
    venue: str
    execution_mode: Literal["shadow", "sandbox"]
    sandbox: bool
    intent_id: str
    venue_order_id: str | None = None
    state: Literal[
        "shadow_only",
        "accepted",
        "open",
        "partially_filled",
        "filled",
        "canceled",
        "rejected",
    ]
    terminal: bool
    filled_quantity: float = Field(default=0.0, ge=0)
    average_fill_price: float | None = Field(default=None, gt=0)
    fee_usd: float = Field(default=0.0, ge=0)
    updated_at: datetime

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class ExecutionRequestArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    execution_mode: Literal["shadow", "sandbox"]
    request_count: int = Field(ge=0)
    rejected_request_count: int = Field(ge=0)
    requests: list[VenueOrderRequest] = Field(default_factory=list)


class ExecutionResultArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    execution_mode: Literal["shadow", "sandbox"]
    result_count: int = Field(ge=0)
    results: list[VenueExecutionAck] = Field(default_factory=list)


class ExecutionStatusArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    session_id: str
    execution_mode: Literal["shadow", "sandbox"]
    status_count: int = Field(ge=0)
    terminal_status_count: int = Field(ge=0)
    statuses: list[VenueOrderState] = Field(default_factory=list)


class LiveTransmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    client_order_id: str
    venue: str
    proposal_id: str
    intent_id: str
    symbol: str
    side: str
    order_type: str
    time_in_force: str
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    reference_price: float = Field(gt=0)
    estimated_notional_usd: float = Field(gt=0)
    min_notional_usd: float = Field(ge=0)
    normalization_status: Literal["ready", "rejected"]
    normalization_reject_reason: str | None = None


class LiveTransmissionRequestArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    run_id: str
    generated_at: datetime
    request_count: int = Field(ge=0)
    rejected_request_count: int = Field(ge=0)
    requests: list[LiveTransmissionRequest] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveTransmissionResultArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    run_id: str
    generated_at: datetime
    adapter_call_attempted: bool = False
    submission_status: Literal["not_submitted"] = "not_submitted"
    summary: str
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)


class LiveTransmissionStateArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_id: str
    session_id: str
    run_id: str
    generated_at: datetime
    state: Literal["not_submitted_terminal_blocked"] = "not_submitted_terminal_blocked"
    terminal: bool = True
    submission_present: bool = False
    summary: str
    reason_codes: list[str] = Field(default_factory=list)

    @field_validator("generated_at")
    @classmethod
    def normalize_generated_at(cls, value: datetime) -> datetime:
        return _normalize_datetime(value)
