import json
from pathlib import Path

import pytest
from crypto_agent.enums import EventType, FillStatus, LiquidityRole, Mode, PolicyAction, Side
from crypto_agent.events.envelope import EventEnvelope
from crypto_agent.types import FillEvent, OrderIntent, PolicyDecision, TradeProposal

SCHEMA_DIR = Path("schemas")


@pytest.mark.parametrize(
    ("schema_name", "model"),
    [
        ("event-envelope.schema.json", EventEnvelope),
        ("trade-proposal.schema.json", TradeProposal),
        ("policy-decision.schema.json", PolicyDecision),
        ("order-intent.schema.json", OrderIntent),
        ("fill-event.schema.json", FillEvent),
    ],
)
def test_schema_artifacts_match_model_json_schema(schema_name: str, model: type[object]) -> None:
    schema_path = SCHEMA_DIR / schema_name
    assert schema_path.exists()

    actual = json.loads(schema_path.read_text(encoding="utf-8"))
    expected = model.model_json_schema()

    assert actual == expected


def test_trade_proposal_model_validates_expected_contract() -> None:
    proposal = TradeProposal(
        strategy_id="breakout_v1",
        symbol="BTCUSDT",
        side=Side.BUY,
        confidence=0.72,
        thesis="Range breakout with expanding volatility.",
        entry_reference=68_500.0,
        stop_price=67_200.0,
        take_profit_price=70_800.0,
        expected_holding_period="4h",
        invalidation_reason="Breakout fails and price closes back inside range.",
        supporting_features={"atr_14": 1250.5, "volume_expansion": True},
        regime_context={"label": "trend", "confidence": 0.81},
    )

    assert proposal.execution_constraints.max_slippage_bps == 20.0
    assert proposal.side is Side.BUY


def test_policy_and_fill_models_validate_enums() -> None:
    decision = PolicyDecision(
        proposal_id="proposal-123",
        action=PolicyAction.ALLOW,
        reason_codes=["within_limits"],
        summary="All deterministic checks passed.",
        mode=Mode.PAPER,
        approved_notional_usd=1_000.0,
    )
    fill = FillEvent(
        intent_id="intent-123",
        symbol="BTCUSDT",
        side=Side.BUY,
        status=FillStatus.FILLED,
        price=68_520.0,
        quantity=0.1,
        notional_usd=6_852.0,
        fee_usd=3.4,
        liquidity_role=LiquidityRole.TAKER,
        mode=Mode.PAPER,
    )
    envelope = EventEnvelope(
        event_type=EventType.ORDER_FILLED,
        source="execution_engine",
        run_id="run-1",
        symbol="BTCUSDT",
        mode=Mode.PAPER,
        payload=fill.model_dump(mode="json"),
    )

    assert decision.action is PolicyAction.ALLOW
    assert fill.status is FillStatus.FILLED
    assert envelope.event_type is EventType.ORDER_FILLED


def test_trade_proposal_rejects_invalid_buy_stop() -> None:
    with pytest.raises(ValueError, match="stop_price below entry_reference"):
        TradeProposal(
            strategy_id="breakout_v1",
            symbol="BTCUSDT",
            side=Side.BUY,
            confidence=0.72,
            thesis="Breakout setup.",
            entry_reference=68_500.0,
            stop_price=68_700.0,
            expected_holding_period="4h",
            invalidation_reason="Breakout fails.",
        )


def test_order_intent_rejects_limit_order_without_limit_price() -> None:
    with pytest.raises(ValueError, match="limit_price"):
        OrderIntent(
            proposal_id="proposal-123",
            symbol="BTCUSDT",
            side=Side.BUY,
            order_type="limit",
            quantity=0.1,
            mode=Mode.PAPER,
        )
