from __future__ import annotations

import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from crypto_agent.market_data.models import Candle, DataQualityIssue

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_jsonl(path: str | Path, model: type[ModelT]) -> list[ModelT]:
    replay_path = Path(path)
    records: list[ModelT] = []

    with replay_path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            content = line.strip()
            if not content:
                continue
            try:
                raw = json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON on line {line_number} in replay file {replay_path}"
                ) from exc
            records.append(model.model_validate(raw))

    return records


def load_candle_replay(path: str | Path) -> list[Candle]:
    return load_jsonl(path, Candle)


def assess_candle_quality(
    candles: list[Candle],
    expected_interval_seconds: int,
) -> list[DataQualityIssue]:
    issues: list[DataQualityIssue] = []

    if expected_interval_seconds <= 0:
        raise ValueError("expected_interval_seconds must be positive")

    previous: Candle | None = None
    for candle in candles:
        if previous is None:
            previous = candle
            continue

        open_delta = (candle.open_time - previous.open_time).total_seconds()
        if open_delta <= 0:
            issues.append(
                DataQualityIssue(
                    code="non_monotonic_timestamp",
                    message="Candle open_time must increase strictly across replay records.",
                    symbol=candle.symbol,
                    observed_at=candle.open_time,
                    details={
                        "previous_open_time": previous.open_time.isoformat(),
                        "current_open_time": candle.open_time.isoformat(),
                    },
                )
            )
        elif open_delta > expected_interval_seconds:
            issues.append(
                DataQualityIssue(
                    code="gap_detected",
                    message="Gap detected between consecutive candles.",
                    symbol=candle.symbol,
                    observed_at=candle.open_time,
                    details={
                        "expected_interval_seconds": expected_interval_seconds,
                        "observed_interval_seconds": open_delta,
                    },
                )
            )

        previous = candle

    return issues
