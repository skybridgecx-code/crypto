from crypto_agent.market_data.venue_constraints import (
    VenueConstraintRegistry,
    VenueSymbolConstraints,
)


def test_venue_symbol_constraints_normalize_price_quantity_and_min_notional() -> None:
    constraints = VenueSymbolConstraints(
        venue="binance_spot",
        symbol="btcusdt",
        status="TRADING",
        base_asset="btc",
        quote_asset="usdt",
        tick_size=0.1,
        step_size=0.001,
        min_quantity=0.001,
        min_notional=10.0,
        raw_filters={},
    )

    assert constraints.symbol == "BTCUSDT"
    assert constraints.base_asset == "BTC"
    assert constraints.quote_asset == "USDT"
    assert constraints.normalize_price(101.27) == 101.2
    assert constraints.normalize_quantity(0.1239) == 0.123
    assert constraints.satisfies_min_notional(price=101.2, quantity=0.123) is True
    assert constraints.satisfies_min_notional(price=101.2, quantity=0.01) is False


def test_venue_constraint_registry_returns_symbol_constraints() -> None:
    constraints = VenueSymbolConstraints(
        venue="binance_spot",
        symbol="ETHUSDT",
        status="TRADING",
        base_asset="ETH",
        quote_asset="USDT",
        tick_size=0.01,
        step_size=0.0001,
        min_quantity=0.0001,
        min_notional=5.0,
        raw_filters={},
    )
    registry = VenueConstraintRegistry(
        venue="binance_spot",
        updated_at="2026-04-05T00:00:00Z",
        symbol_constraints=[constraints],
    )

    assert registry.get("ethusdt") == constraints
