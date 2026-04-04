from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from crypto_agent.types import ScalarValue


def _normalize_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamp fields must be timezone-aware")
    return value.astimezone(UTC)


class BookLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float = Field(gt=0)
    quantity: float = Field(gt=0)


class Candle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str = "paper"
    symbol: str
    interval: str
    open_time: datetime
    close_time: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)
    volume: float = Field(ge=0)
    closed: bool = True

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("open_time", "close_time")
    @classmethod
    def normalize_datetimes(cls, value: datetime) -> datetime:
        return _normalize_timestamp(value)

    @model_validator(mode="after")
    def validate_price_shape(self) -> Candle:
        if self.open_time >= self.close_time:
            raise ValueError("open_time must be earlier than close_time")
        if self.high < max(self.open, self.close):
            raise ValueError("high must be at least max(open, close)")
        if self.low > min(self.open, self.close):
            raise ValueError("low must be at most min(open, close)")
        if self.low > self.high:
            raise ValueError("low cannot exceed high")
        return self


class TradeTick(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str = "paper"
    symbol: str
    timestamp: datetime
    price: float = Field(gt=0)
    quantity: float = Field(gt=0)
    side: str

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_timestamp(value)


class OrderBookSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    venue: str = "paper"
    symbol: str
    timestamp: datetime
    bids: list[BookLevel]
    asks: list[BookLevel]

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_timestamp(value)

    @model_validator(mode="after")
    def validate_book_shape(self) -> OrderBookSnapshot:
        if not self.bids:
            raise ValueError("bids cannot be empty")
        if not self.asks:
            raise ValueError("asks cannot be empty")
        best_bid = self.bids[0].price
        best_ask = self.asks[0].price
        if best_bid >= best_ask:
            raise ValueError("best bid must be lower than best ask")
        return self


class DataQualityIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    symbol: str
    observed_at: datetime
    details: dict[str, ScalarValue] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return _normalize_timestamp(value)


class ReplayBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candles: list[Candle] = Field(default_factory=list)
    quality_issues: list[DataQualityIssue] = Field(default_factory=list)
