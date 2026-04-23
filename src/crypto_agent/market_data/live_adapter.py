from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
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


def _to_millis(value: datetime) -> int:
    return int(value.timestamp() * 1000)


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


class CoinbaseSpotLiveMarketDataAdapter:
    _GRANULARITY_SECONDS: dict[str, int] = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "6h": 21600,
        "1d": 86400,
    }

    def __init__(
        self,
        *,
        base_url: str = "https://api.coinbase.com",
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
        return "coinbase_spot"

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
        product_id = self._to_product_id(symbol)
        payload = self._fetch_json(
            f"/api/v3/brokerage/products/{product_id}",
            {},
        )
        product = (
            payload.get("product")
            if isinstance(payload, dict) and "product" in payload
            else payload
        )
        if not isinstance(product, dict):
            raise LiveMarketDataUnavailableError(
                f"Venue metadata unavailable for symbol {symbol.strip().upper()}"
            )

        base_currency = str(product.get("base_currency_id", "")).strip().upper()
        quote_currency = str(product.get("quote_currency_id", "")).strip().upper()
        if not base_currency or not quote_currency:
            raise LiveMarketDataUnavailableError(
                f"Incomplete venue metadata for symbol {product_id}"
            )
        normalized_symbol = f"{base_currency}{quote_currency}"
        quote_increment = self._as_positive_float(product.get("quote_increment"), "quote_increment")
        base_increment = self._as_positive_float(product.get("base_increment"), "base_increment")
        min_size = self._as_nonnegative_float(product.get("base_min_size"), "base_min_size")
        min_market_funds = self._as_nonnegative_float(
            product.get("quote_min_size"),
            "quote_min_size",
        )
        status_value = str(product.get("trading_disabled", "")).strip().lower()
        status = "TRADING" if status_value not in {"true", "1"} else "HALTED"
        raw_filters = {
            "COINBASE_PRODUCT": {
                "product_id": product_id,
                "quote_increment": str(product.get("quote_increment", "")),
                "base_increment": str(product.get("base_increment", "")),
                "base_min_size": str(product.get("base_min_size", "")),
                "quote_min_size": str(product.get("quote_min_size", "")),
            }
        }
        constraints = VenueSymbolConstraints(
            venue=self.name,
            symbol=normalized_symbol,
            status=status,
            base_asset=base_currency,
            quote_asset=quote_currency,
            tick_size=quote_increment,
            step_size=base_increment,
            min_quantity=min_size,
            min_notional=min_market_funds,
            raw_filters=raw_filters,
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
        product_id = self._to_product_id(symbol)
        observed_at = now or _utc_now()
        key = (product_id, interval)

        try:
            registry = self.load_venue_constraints(symbol=symbol, now=observed_at)
            constraints = registry.symbol_constraints[0]
            normalized_symbol = constraints.symbol
            granularity_seconds = self._interval_to_granularity(interval)
            candles_payload = self._fetch_json(
                f"/api/v3/brokerage/products/{product_id}/candles",
                {
                    "start": str(
                        _to_millis(observed_at)
                        - ((lookback_candles + 1) * granularity_seconds * 1000)
                    ),
                    "end": str(_to_millis(observed_at)),
                    "granularity": str(granularity_seconds),
                },
            )
            book_payload = self._fetch_json(
                "/api/v3/brokerage/product_book",
                {
                    "product_id": product_id,
                    "limit": "1",
                },
            )
            candles = self._normalize_candles(
                payload=candles_payload,
                symbol=normalized_symbol,
                interval=interval,
                now=observed_at,
                lookback_candles=lookback_candles,
            )
            best_bid, best_ask = self._extract_best_bid_ask(book_payload)
            order_book = OrderBookSnapshot(
                venue=self.name,
                symbol=normalized_symbol,
                timestamp=observed_at,
                bids=[BookLevel(price=best_bid, quantity=1.0)],
                asks=[BookLevel(price=best_ask, quantity=1.0)],
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

    def _normalize_candles(
        self,
        *,
        payload: Any,
        symbol: str,
        interval: str,
        now: datetime,
        lookback_candles: int,
    ) -> list[Candle]:
        rows = (
            payload.get("candles")
            if isinstance(payload, dict) and "candles" in payload
            else payload
        )
        if not isinstance(rows, list):
            raise LiveMarketDataUnavailableError("Venue candle response must be a list")
        parsed: list[Candle] = []
        for row in rows:
            if not isinstance(row, dict):
                raise LiveMarketDataUnavailableError("Venue candle response contained invalid rows")
            start = row.get("start")
            open_price = row.get("open")
            high_price = row.get("high")
            low_price = row.get("low")
            close_price = row.get("close")
            volume = row.get("volume")
            if any(
                value is None
                for value in (start, open_price, high_price, low_price, close_price, volume)
            ):
                raise LiveMarketDataUnavailableError(
                    "Venue candle response contained incomplete rows"
                )
            assert start is not None
            assert open_price is not None
            assert high_price is not None
            assert low_price is not None
            assert close_price is not None
            assert volume is not None
            open_time = _from_millis(int(start))
            close_time = open_time + self._interval_delta(interval)
            candle = Candle(
                venue=self.name,
                symbol=symbol,
                interval=interval,
                open_time=open_time,
                close_time=close_time,
                open=float(open_price),
                high=float(high_price),
                low=float(low_price),
                close=float(close_price),
                volume=float(volume),
                closed=True,
            )
            if candle.close_time <= now:
                parsed.append(candle)
        parsed.sort(key=lambda candle: candle.open_time)
        if len(parsed) < lookback_candles:
            raise LiveMarketDataUnavailableError("Not enough closed venue candles available")
        return parsed[-lookback_candles:]

    def _extract_best_bid_ask(self, payload: Any) -> tuple[float, float]:
        if not isinstance(payload, dict):
            raise LiveMarketDataUnavailableError("Venue product book response must be an object")
        bids = payload.get("bids")
        asks = payload.get("asks")
        if not bids and isinstance(payload.get("pricebook"), dict):
            bids = payload["pricebook"].get("bids")
            asks = payload["pricebook"].get("asks")
        if not isinstance(bids, list) or not isinstance(asks, list) or not bids or not asks:
            raise LiveMarketDataUnavailableError("Venue product book response missing bids/asks")
        best_bid = self._extract_price(bids[0])
        best_ask = self._extract_price(asks[0])
        if best_bid >= best_ask:
            raise LiveMarketDataUnavailableError("Venue product book contains crossed market")
        return best_bid, best_ask

    def _extract_price(self, row: Any) -> float:
        if isinstance(row, dict):
            if "price" in row:
                return float(row["price"])
            if "px" in row:
                return float(row["px"])
        raise LiveMarketDataUnavailableError("Venue product book row missing price")

    def _to_product_id(self, symbol: str) -> str:
        normalized = symbol.strip().upper().replace("/", "-").replace("_", "-")
        if "-" in normalized:
            return normalized
        for quote in ("USDT", "USDC", "USD", "EUR", "GBP"):
            if normalized.endswith(quote) and len(normalized) > len(quote):
                return f"{normalized[:-len(quote)]}-{quote}"
        raise LiveMarketDataUnavailableError(
            "Coinbase symbol must be product-style (for example BTC-USD) "
            "or a recognized base+quote pair."
        )

    def _interval_to_granularity(self, interval: str) -> int:
        normalized_interval = interval.strip().lower()
        granularity = self._GRANULARITY_SECONDS.get(normalized_interval)
        if granularity is None:
            raise LiveMarketDataUnavailableError(
                f"Unsupported Coinbase candle interval: {interval}"
            )
        return granularity

    def _interval_delta(self, interval: str) -> timedelta:
        return timedelta(seconds=self._interval_to_granularity(interval))

    def _as_positive_float(self, value: Any, label: str) -> float:
        resolved = float(value)
        if resolved <= 0:
            raise LiveMarketDataUnavailableError(
                f"Invalid {label} value in Coinbase product metadata"
            )
        return resolved

    def _as_nonnegative_float(self, value: Any, label: str) -> float:
        resolved = float(value)
        if resolved < 0:
            raise LiveMarketDataUnavailableError(
                f"Invalid {label} value in Coinbase product metadata"
            )
        return resolved

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
