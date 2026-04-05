from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, Literal
from urllib.parse import urlencode
from urllib.request import urlopen

from crypto_agent.market_data.live_models import LiveFeedHealth, LiveMarketState
from crypto_agent.market_data.models import BookLevel, Candle, OrderBookSnapshot
from crypto_agent.market_data.venue_constraints import (
    VenueConstraintRegistry,
    VenueSymbolConstraints,
)


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _from_millis(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1000, tz=UTC)


class LiveMarketDataUnavailableError(RuntimeError):
    pass


class BinanceSpotLiveMarketDataAdapter:
    def __init__(
        self,
        *,
        base_url: str = "https://api.binance.com",
        timeout_seconds: float = 5.0,
        fetch_json: Callable[[str, dict[str, str]], Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._fetch_json = fetch_json or self._default_fetch_json
        self._constraints_by_symbol: dict[str, VenueSymbolConstraints] = {}
        self._last_market_state: dict[tuple[str, str], LiveMarketState] = {}
        self._last_success_at: dict[tuple[str, str], datetime] = {}
        self._consecutive_failures: dict[tuple[str, str], int] = {}

    @property
    def name(self) -> str:
        return "binance_spot"

    def _default_fetch_json(self, endpoint: str, params: dict[str, str]) -> Any:
        query = urlencode(params)
        url = f"{self.base_url}{endpoint}?{query}" if query else f"{self.base_url}{endpoint}"
        with urlopen(url, timeout=self.timeout_seconds) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))

    def load_venue_constraints(
        self,
        *,
        symbol: str,
        now: datetime | None = None,
    ) -> VenueConstraintRegistry:
        normalized_symbol = symbol.strip().upper()
        payload = self._fetch_json("/api/v3/exchangeInfo", {"symbol": normalized_symbol})
        symbols = payload.get("symbols", [])
        if len(symbols) != 1:
            raise LiveMarketDataUnavailableError(
                f"Venue metadata unavailable for symbol {normalized_symbol}"
            )

        raw_symbol = symbols[0]
        filters = {
            str(raw_filter["filterType"]): {
                str(key): str(value) for key, value in raw_filter.items()
            }
            for raw_filter in raw_symbol.get("filters", [])
        }
        price_filter = filters.get("PRICE_FILTER")
        lot_size_filter = filters.get("LOT_SIZE")
        min_notional_filter = filters.get("MIN_NOTIONAL")
        if price_filter is None or lot_size_filter is None or min_notional_filter is None:
            raise LiveMarketDataUnavailableError(
                f"Incomplete venue filters for symbol {normalized_symbol}"
            )

        constraints = VenueSymbolConstraints(
            venue=self.name,
            symbol=normalized_symbol,
            status=str(raw_symbol["status"]),
            base_asset=str(raw_symbol["baseAsset"]),
            quote_asset=str(raw_symbol["quoteAsset"]),
            tick_size=float(price_filter["tickSize"]),
            step_size=float(lot_size_filter["stepSize"]),
            min_quantity=float(lot_size_filter["minQty"]),
            min_notional=float(min_notional_filter["minNotional"]),
            raw_filters=filters,
        )
        self._constraints_by_symbol[normalized_symbol] = constraints
        return VenueConstraintRegistry(
            venue=self.name,
            updated_at=now or _utc_now(),
            symbol_constraints=[constraints],
        )

    def poll_market_state(
        self,
        *,
        symbol: str,
        interval: str,
        lookback_candles: int,
        stale_after_seconds: int,
        now: datetime | None = None,
    ) -> LiveMarketState:
        normalized_symbol = symbol.strip().upper()
        observed_at = now or _utc_now()
        key = (normalized_symbol, interval)

        try:
            registry = self.load_venue_constraints(symbol=normalized_symbol, now=observed_at)
            constraints = registry.get(normalized_symbol)
            klines = self._fetch_json(
                "/api/v3/klines",
                {
                    "symbol": normalized_symbol,
                    "interval": interval,
                    "limit": str(lookback_candles + 1),
                },
            )
            book_ticker = self._fetch_json(
                "/api/v3/ticker/bookTicker",
                {"symbol": normalized_symbol},
            )
            candles = self._normalize_klines(
                klines=klines,
                symbol=normalized_symbol,
                interval=interval,
                now=observed_at,
                lookback_candles=lookback_candles,
            )
            order_book = OrderBookSnapshot(
                venue=self.name,
                symbol=normalized_symbol,
                timestamp=observed_at,
                bids=[
                    BookLevel(
                        price=float(book_ticker["bidPrice"]),
                        quantity=float(book_ticker["bidQty"]),
                    )
                ],
                asks=[
                    BookLevel(
                        price=float(book_ticker["askPrice"]),
                        quantity=float(book_ticker["askQty"]),
                    )
                ],
            )
            latest_close = candles[-1].close_time
            feed_health = self._healthy_feed_health(
                observed_at=observed_at,
                latest_close=latest_close,
                stale_after_seconds=stale_after_seconds,
                recovered=self._consecutive_failures.get(key, 0) > 0,
            )
            market_state = LiveMarketState(
                venue=self.name,
                symbol=normalized_symbol,
                interval=interval,
                polled_at=observed_at,
                candles=candles,
                order_book=order_book,
                constraints=constraints,
                constraint_registry=registry,
                feed_health=feed_health,
            )
            self._last_market_state[key] = market_state
            self._last_success_at[key] = observed_at
            self._consecutive_failures[key] = 0
            return market_state
        except Exception as exc:
            failure_count = self._consecutive_failures.get(key, 0) + 1
            self._consecutive_failures[key] = failure_count
            cached_state = self._last_market_state.get(key)
            if cached_state is None:
                raise LiveMarketDataUnavailableError(str(exc)) from exc
            last_close = cached_state.candles[-1].close_time
            health_status: Literal["stale", "degraded"] = (
                "stale"
                if (observed_at - last_close).total_seconds() > stale_after_seconds
                else "degraded"
            )
            return cached_state.model_copy(
                update={
                    "polled_at": observed_at,
                    "feed_health": LiveFeedHealth(
                        status=health_status,
                        observed_at=observed_at,
                        last_success_at=self._last_success_at.get(key),
                        last_candle_close_time=last_close,
                        consecutive_failure_count=failure_count,
                        stale_after_seconds=stale_after_seconds,
                        message=str(exc),
                    ),
                }
            )

    def _normalize_klines(
        self,
        *,
        klines: Any,
        symbol: str,
        interval: str,
        now: datetime,
        lookback_candles: int,
    ) -> list[Candle]:
        if not isinstance(klines, list):
            raise LiveMarketDataUnavailableError("Venue kline response must be a list")
        candles: list[Candle] = []
        for raw_kline in klines:
            if not isinstance(raw_kline, list) or len(raw_kline) < 7:
                raise LiveMarketDataUnavailableError("Venue kline response contained invalid rows")
            candle = Candle(
                venue=self.name,
                symbol=symbol,
                interval=interval,
                open_time=_from_millis(int(raw_kline[0])),
                close_time=_from_millis(int(raw_kline[6])),
                open=float(raw_kline[1]),
                high=float(raw_kline[2]),
                low=float(raw_kline[3]),
                close=float(raw_kline[4]),
                volume=float(raw_kline[5]),
                closed=True,
            )
            if candle.close_time <= now:
                candles.append(candle)

        if len(candles) < lookback_candles:
            raise LiveMarketDataUnavailableError("Not enough closed venue candles available")
        return candles[-lookback_candles:]

    def _healthy_feed_health(
        self,
        *,
        observed_at: datetime,
        latest_close: datetime,
        stale_after_seconds: int,
        recovered: bool,
    ) -> LiveFeedHealth:
        status: Literal["healthy", "stale"] = (
            "stale"
            if (observed_at - latest_close).total_seconds() > stale_after_seconds
            else "healthy"
        )
        message = "recovered_after_failure" if recovered else None
        return LiveFeedHealth(
            status=status,
            observed_at=observed_at,
            last_success_at=observed_at,
            last_candle_close_time=latest_close,
            consecutive_failure_count=0,
            stale_after_seconds=stale_after_seconds,
            message=message,
            recovered=recovered,
        )
