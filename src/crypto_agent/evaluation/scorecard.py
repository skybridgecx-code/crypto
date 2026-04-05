from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from math import fsum

from crypto_agent.enums import EventType, PolicyAction, Side
from crypto_agent.evaluation.models import EvaluationScorecard, ReplayPnLSummary
from crypto_agent.events.envelope import EventEnvelope
from crypto_agent.types import FillEvent

POSITION_EPSILON = 1e-12


@dataclass
class _PnLPosition:
    quantity: float = 0.0
    average_entry_price: float = 0.0


def _collect_proposal_execution_state(
    events: list[EventEnvelope],
) -> dict[str, dict[str, bool]]:
    state: dict[str, dict[str, bool]] = defaultdict(
        lambda: {
            "allowed": False,
            "intent_created": False,
            "submitted": False,
            "filled_or_rejected": False,
        }
    )

    for event in events:
        payload = event.payload
        proposal_id = None
        if event.event_type is EventType.TRADE_PROPOSAL_CREATED:
            proposal_id = str(payload["proposal_id"])
        elif event.event_type is EventType.POLICY_DECISION_MADE:
            proposal_id = str(payload["proposal_id"])
        elif event.event_type is EventType.ORDER_INTENT_CREATED:
            proposal_id = str(payload["proposal_id"])
        elif event.event_type in (EventType.ORDER_SUBMITTED, EventType.ORDER_REJECTED):
            proposal_id = str(payload["intent"]["proposal_id"])
        elif event.event_type is EventType.ORDER_FILLED:
            proposal_id = None

        if proposal_id is None:
            continue

        state[proposal_id]

        if event.event_type is EventType.POLICY_DECISION_MADE:
            if str(payload["action"]) == PolicyAction.ALLOW.value:
                state[proposal_id]["allowed"] = True
        elif event.event_type is EventType.ORDER_INTENT_CREATED:
            state[proposal_id]["intent_created"] = True
        elif event.event_type is EventType.ORDER_SUBMITTED:
            state[proposal_id]["submitted"] = True
        elif event.event_type is EventType.ORDER_REJECTED:
            state[proposal_id]["filled_or_rejected"] = True

    intent_to_proposal: dict[str, str] = {}
    for event in events:
        if event.event_type is EventType.ORDER_INTENT_CREATED:
            intent_to_proposal[str(event.payload["intent_id"])] = str(event.payload["proposal_id"])
        elif event.event_type is EventType.ORDER_SUBMITTED:
            intent = event.payload["intent"]
            intent_to_proposal[str(intent["intent_id"])] = str(intent["proposal_id"])

    for event in events:
        if event.event_type is EventType.ORDER_FILLED:
            proposal_id = intent_to_proposal.get(str(event.payload["intent_id"]))
            if proposal_id is not None:
                state[proposal_id]["filled_or_rejected"] = True

    return state


def build_scorecard(events: list[EventEnvelope]) -> EvaluationScorecard:
    if not events:
        return EvaluationScorecard(run_id="empty", event_count=0)

    run_id = events[0].run_id
    slippage_values = [
        float(event.payload["estimated_slippage_bps"])
        for event in events
        if event.event_type is EventType.ORDER_SUBMITTED
    ]
    filled_intents = {
        str(event.payload["intent_id"])
        for event in events
        if event.event_type is EventType.ORDER_FILLED
    }
    partial_fill_intents = {
        str(event.payload["intent_id"])
        for event in events
        if event.event_type is EventType.ORDER_FILLED
        and str(event.payload["status"]) == "partially_filled"
    }
    total_fill_notional_usd = fsum(
        float(event.payload["notional_usd"])
        for event in events
        if event.event_type is EventType.ORDER_FILLED
    )
    total_fee_usd = fsum(
        float(event.payload["fee_usd"])
        for event in events
        if event.event_type is EventType.ORDER_FILLED
    )
    proposal_state = _collect_proposal_execution_state(events)
    complete_execution_count = sum(
        1
        for state in proposal_state.values()
        if not state["allowed"]
        or (state["intent_created"] and state["submitted"] and state["filled_or_rejected"])
    )

    return EvaluationScorecard(
        run_id=run_id,
        event_count=len(events),
        proposal_count=sum(
            1 for event in events if event.event_type is EventType.TRADE_PROPOSAL_CREATED
        ),
        approval_count=sum(
            1
            for event in events
            if event.event_type is EventType.POLICY_DECISION_MADE
            and str(event.payload["action"]) == PolicyAction.ALLOW.value
        ),
        denial_count=sum(
            1
            for event in events
            if event.event_type is EventType.POLICY_DECISION_MADE
            and str(event.payload["action"]) == PolicyAction.DENY.value
        ),
        halt_count=sum(
            1
            for event in events
            if event.event_type is EventType.POLICY_DECISION_MADE
            and str(event.payload["action"]) == PolicyAction.HALT.value
        ),
        order_intent_count=sum(
            1 for event in events if event.event_type is EventType.ORDER_INTENT_CREATED
        ),
        orders_submitted_count=sum(
            1 for event in events if event.event_type is EventType.ORDER_SUBMITTED
        ),
        order_reject_count=sum(
            1 for event in events if event.event_type is EventType.ORDER_REJECTED
        ),
        fill_event_count=sum(1 for event in events if event.event_type is EventType.ORDER_FILLED),
        filled_intent_count=len(filled_intents),
        partial_fill_intent_count=len(partial_fill_intents),
        complete_execution_count=complete_execution_count,
        incomplete_execution_count=len(proposal_state) - complete_execution_count,
        average_slippage_bps=(
            fsum(slippage_values) / len(slippage_values) if slippage_values else 0.0
        ),
        max_slippage_bps=max(slippage_values) if slippage_values else 0.0,
        total_fill_notional_usd=total_fill_notional_usd,
        total_fee_usd=total_fee_usd,
    )


def _apply_fill_to_pnl_position(
    position: _PnLPosition,
    fill: FillEvent,
) -> tuple[_PnLPosition, float]:
    signed_fill_quantity = fill.quantity if fill.side is Side.BUY else -fill.quantity

    if abs(position.quantity) < POSITION_EPSILON:
        return _PnLPosition(
            quantity=signed_fill_quantity,
            average_entry_price=fill.price,
        ), 0.0

    if position.quantity * signed_fill_quantity > 0:
        new_quantity = position.quantity + signed_fill_quantity
        average_entry_price = (
            abs(position.quantity) * position.average_entry_price
            + abs(signed_fill_quantity) * fill.price
        ) / abs(new_quantity)
        return _PnLPosition(
            quantity=new_quantity,
            average_entry_price=average_entry_price,
        ), 0.0

    closing_quantity = min(abs(position.quantity), abs(signed_fill_quantity))
    if position.quantity > 0:
        gross_realized_pnl_usd = closing_quantity * (fill.price - position.average_entry_price)
    else:
        gross_realized_pnl_usd = closing_quantity * (position.average_entry_price - fill.price)

    remaining_quantity = position.quantity + signed_fill_quantity
    if abs(remaining_quantity) < POSITION_EPSILON:
        return _PnLPosition(), gross_realized_pnl_usd

    if position.quantity * remaining_quantity > 0:
        return _PnLPosition(
            quantity=remaining_quantity,
            average_entry_price=position.average_entry_price,
        ), gross_realized_pnl_usd

    return _PnLPosition(
        quantity=remaining_quantity,
        average_entry_price=fill.price,
    ), gross_realized_pnl_usd


def build_replay_pnl(
    events: list[EventEnvelope],
    *,
    final_close_by_symbol: dict[str, float],
    starting_equity_usd: float,
) -> ReplayPnLSummary:
    fills = sorted(
        (
            FillEvent.model_validate(event.payload)
            for event in events
            if event.event_type is EventType.ORDER_FILLED
        ),
        key=lambda fill: (fill.timestamp, fill.intent_id, fill.fill_id),
    )

    positions: dict[str, _PnLPosition] = {}
    gross_realized_pnl_values: list[float] = []
    fee_values: list[float] = []

    for fill in fills:
        current_position = positions.get(fill.symbol, _PnLPosition())
        next_position, gross_realized_pnl_usd = _apply_fill_to_pnl_position(current_position, fill)
        gross_realized_pnl_values.append(gross_realized_pnl_usd)
        fee_values.append(fill.fee_usd)

        if abs(next_position.quantity) < POSITION_EPSILON:
            positions.pop(fill.symbol, None)
        else:
            positions[fill.symbol] = next_position

    gross_realized_pnl_usd = fsum(gross_realized_pnl_values)
    total_fee_usd = fsum(fee_values)
    ending_unrealized_pnl_usd = fsum(
        position.quantity
        * (
            final_close_by_symbol.get(symbol, position.average_entry_price)
            - position.average_entry_price
        )
        for symbol, position in positions.items()
    )
    net_realized_pnl_usd = gross_realized_pnl_usd - total_fee_usd
    ending_equity_usd = starting_equity_usd + net_realized_pnl_usd + ending_unrealized_pnl_usd

    return ReplayPnLSummary(
        starting_equity_usd=starting_equity_usd,
        gross_realized_pnl_usd=gross_realized_pnl_usd,
        total_fee_usd=total_fee_usd,
        net_realized_pnl_usd=net_realized_pnl_usd,
        ending_unrealized_pnl_usd=ending_unrealized_pnl_usd,
        ending_equity_usd=ending_equity_usd,
        return_fraction=(ending_equity_usd - starting_equity_usd) / starting_equity_usd,
    )
