from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from crypto_agent.market_data.models import ReplayBatch


class MarketDataAdapter(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def load_candles(self, path: str | Path, expected_interval_seconds: int) -> ReplayBatch:
        raise NotImplementedError
