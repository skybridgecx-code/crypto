from __future__ import annotations

from collections import defaultdict

from crypto_agent.enums import EventType, PolicyAction
from crypto_agent.evaluation.models import EvaluationScorecard
from crypto_agent.events.envelope import EventEnvelope


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
            sum(slippage_values) / len(slippage_values) if slippage_values else 0.0
        ),
        max_slippage_bps=max(slippage_values) if slippage_values else 0.0,
        total_fill_notional_usd=sum(
            float(event.payload["notional_usd"])
            for event in events
            if event.event_type is EventType.ORDER_FILLED
        ),
        total_fee_usd=sum(
            float(event.payload["fee_usd"])
            for event in events
            if event.event_type is EventType.ORDER_FILLED
        ),
    )
