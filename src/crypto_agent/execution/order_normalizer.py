from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from uuid import NAMESPACE_URL, uuid5

from crypto_agent.enums import PolicyAction
from crypto_agent.execution.models import PaperExecutionConfig
from crypto_agent.risk.checks import RiskCheckResult
from crypto_agent.types import OrderIntent


def _round_down(value: float, step: float) -> float:
    decimal_value = Decimal(str(value))
    decimal_step = Decimal(str(step))
    return float(decimal_value.quantize(decimal_step, rounding=ROUND_DOWN))


def _normalize_price(price: float, tick: float) -> float:
    decimal_price = Decimal(str(price))
    decimal_tick = Decimal(str(tick))
    rounded = decimal_price.quantize(decimal_tick)
    return float(rounded)


def normalize_order_intent(
    risk_result: RiskCheckResult,
    config: PaperExecutionConfig | None = None,
) -> OrderIntent:
    normalization = config or PaperExecutionConfig()

    if risk_result.decision.action is not PolicyAction.ALLOW:
        raise ValueError("Only approved risk decisions can be normalized into order intents.")
    if risk_result.sizing is None:
        raise ValueError("Approved risk decision is missing sizing data.")

    proposal = risk_result.proposal
    sizing = risk_result.sizing
    normalized_quantity = _round_down(sizing.quantity, normalization.quantity_step)
    if normalized_quantity <= 0:
        raise ValueError("Normalized quantity must remain positive.")

    limit_price = None
    if proposal.execution_constraints.order_type.value == "limit":
        limit_price = _normalize_price(proposal.entry_reference, normalization.price_tick)

    intent_id = str(
        uuid5(
            NAMESPACE_URL,
            f"{proposal.proposal_id}:{risk_result.decision.mode.value}:{proposal.symbol}:{proposal.side.value}",
        )
    )

    return OrderIntent(
        intent_id=intent_id,
        proposal_id=proposal.proposal_id,
        symbol=proposal.symbol,
        side=proposal.side,
        order_type=proposal.execution_constraints.order_type,
        time_in_force=proposal.execution_constraints.time_in_force,
        quantity=normalized_quantity,
        limit_price=limit_price,
        max_slippage_bps=proposal.execution_constraints.max_slippage_bps,
        reduce_only=False,
        mode=risk_result.decision.mode,
    )
