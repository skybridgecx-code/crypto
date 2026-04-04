from __future__ import annotations

from crypto_agent.market_data.base import MarketDataAdapter


class MarketDataRouter:
    def __init__(self) -> None:
        self._adapters: dict[str, MarketDataAdapter] = {}

    def register(self, adapter: MarketDataAdapter) -> None:
        self._adapters[adapter.name] = adapter

    def get(self, name: str) -> MarketDataAdapter:
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise KeyError(f"No market data adapter registered for '{name}'") from exc
