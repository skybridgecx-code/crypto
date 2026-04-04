from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "crypto-agent"
    environment: str = "local"


class PathsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_dir: Path = Field(default=Path("data"))
    runs_dir: Path = Field(default=Path("runs"))
    journals_dir: Path = Field(default=Path("journals"))


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str = "research_only"
    app: AppConfig = Field(default_factory=AppConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)


def load_settings(path: str | Path) -> Settings:
    config_path = Path(path)
    with config_path.open("r", encoding="utf-8") as handle:
        raw_config = yaml.safe_load(handle) or {}

    if not isinstance(raw_config, dict):
        raise TypeError("Configuration file must deserialize into a mapping.")

    return Settings.model_validate(raw_config)


def dump_settings(settings: Settings) -> dict[str, Any]:
    return settings.model_dump(mode="python")
