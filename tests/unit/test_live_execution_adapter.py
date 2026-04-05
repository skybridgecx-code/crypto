from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from crypto_agent.enums import Mode, OrderType, Side, TimeInForce
from crypto_agent.execution.live_adapter import build_venue_order_request
from crypto_agent.market_data.live_models import LiveFeedHealth, LiveMarketState
from crypto_agent.market_data.models import BookLevel, Candle, OrderBookSnapshot
from crypto_agent.market_data.venue_constraints import (
    VenueConstraintRegistry,
    VenueSymbolConstraints,
)
from crypto_agent.types import OrderIntent


def _market_state() -> LiveMarketState:
    constraints = VenueSymbolConstraints(
        venue="binance_spot",
        symbol="BTCUSDT",
        status="TRADING",
        base_asset="BTC",
        quote_asset="USDT",
        tick_size=0.1,
        step_size=0.001,
        min_quantity=0.001,
        min_notional=10.0,
    )
    now = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
    return LiveMarketState(
        venue="binance_spot",
        symbol="BTCUSDT",
        interval="1m",
        polled_at=now,
        candles=[
            Candle(
                venue="binance_spot",
                symbol="BTCUSDT",
                interval="1m",
                open_time=now,
                close_time=now + timedelta(minutes=1),
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1000.0,
                closed=True,
            )
        ],
        order_book=OrderBookSnapshot(
            venue="binance_spot",
            symbol="BTCUSDT",
            timestamp=now,
            bids=[BookLevel(price=100.4, quantity=1.0)],
            asks=[BookLevel(price=100.6, quantity=1.0)],
        ),
        constraints=constraints,
        constraint_registry=VenueConstraintRegistry(
            venue="binance_spot",
            updated_at=now,
            symbol_constraints=[constraints],
        ),
        feed_health=LiveFeedHealth(
            status="healthy",
            observed_at=now,
            last_success_at=now,
            last_candle_close_time=now,
            stale_after_seconds=120,
        ),
    )


def test_build_venue_order_request_normalizes_live_compatible_request() -> None:
    market_state = _market_state()
    intent = OrderIntent(
        intent_id="intent-1",
        proposal_id="proposal-1",
        symbol="BTCUSDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.GTC,
        quantity=0.123456,
        max_slippage_bps=10.0,
        mode=Mode.PAPER,
    )

    request = build_venue_order_request(
        intent=intent,
        constraints=market_state.constraints,
        market_state=market_state,
        execution_mode="shadow",
    )

    assert request.client_order_id
    assert request.quantity == pytest.approx(0.123)
    assert request.reference_price == pytest.approx(100.6)
    assert request.estimated_notional_usd == pytest.approx(12.3738)
    assert request.normalization_status == "ready"
    assert request.normalization_reject_reason is None


def test_build_venue_order_request_rejects_below_min_notional() -> None:
    market_state = _market_state()
    intent = OrderIntent(
        intent_id="intent-2",
        proposal_id="proposal-2",
        symbol="BTCUSDT",
        side=Side.BUY,
        order_type=OrderType.MARKET,
        time_in_force=TimeInForce.GTC,
        quantity=0.001,
        max_slippage_bps=10.0,
        mode=Mode.PAPER,
    )

    request = build_venue_order_request(
        intent=intent,
        constraints=market_state.constraints,
        market_state=market_state,
        execution_mode="sandbox",
    )

    assert request.estimated_notional_usd < request.min_notional_usd
    assert request.normalization_status == "rejected"
    assert request.normalization_reject_reason == "venue_min_notional_not_met"
