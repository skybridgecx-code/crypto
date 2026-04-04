from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from crypto_agent.enums import Mode


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "crypto-agent"
    environment: str = "local"
    timezone: str = "UTC"


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: Path = Field(default=Path("data"))
    runs_dir: Path = Field(default=Path("runs"))
    journals_dir: Path = Field(default=Path("journals"))
    schemas_dir: Path = Field(default=Path("schemas"))


class VenueConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_venue: str = "paper"
    allowed_symbols: list[str] = Field(default_factory=lambda: ["BTCUSDT", "ETHUSDT"])
    quote_currency: str = "USDT"


class RiskLimitsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_portfolio_gross_exposure: float = Field(default=1.0, ge=0)
    max_symbol_gross_exposure: float = Field(default=0.5, ge=0)
    max_daily_realized_loss: float = Field(default=0.02, ge=0, le=1)
    max_open_positions: int = Field(default=3, ge=0)
    max_leverage: float = Field(default=1.0, gt=0)
    max_spread_bps: float = Field(default=15.0, ge=0)
    max_expected_slippage_bps: float = Field(default=20.0, ge=0)
    min_24h_quote_volume_usd: float = Field(default=50_000_000.0, ge=0)


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    allow_live_orders: bool = False
    require_manual_approval_above_notional_usd: float = Field(default=0.0, ge=0)
    kill_switch_enabled: bool = True


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Mode = Mode.RESEARCH_ONLY
    app: AppConfig = Field(default_factory=AppConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)
    venue: VenueConfig = Field(default_factory=VenueConfig)
    risk: RiskLimitsConfig = Field(default_factory=RiskLimitsConfig)
    policy: PolicyConfig = Field(default_factory=PolicyConfig)

    @model_validator(mode="after")
    def validate_mode_policy_alignment(self) -> Settings:
        if self.policy.allow_live_orders and self.mode is not Mode.LIMITED_LIVE:
            raise ValueError("allow_live_orders can only be enabled in limited_live mode")
        return self


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}

    if not isinstance(raw_config, dict):
        raise TypeError("Configuration file must deserialize into a mapping.")

    return Settings.model_validate(raw_config)


def dump_settings(settings: Settings) -> dict[str, Any]:
    return settings.model_dump(mode="json")
