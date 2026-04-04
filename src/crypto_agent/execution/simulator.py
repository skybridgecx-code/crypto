from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

from crypto_agent.enums import FillStatus, LiquidityRole, PolicyAction, Side
from crypto_agent.execution.models import ExecutionReport, PaperExecutionConfig
from crypto_agent.execution.order_normalizer import normalize_order_intent
from crypto_agent.risk.checks import RiskCheckResult
from crypto_agent.types import FillEvent, OrderIntent


def _deterministic_timestamp(intent_id: str, offset_seconds: int = 0) -> datetime:
    base = datetime(2026, 1, 1, tzinfo=UTC)
    derived_seconds = UUID(intent_id).int % 86_400
    return base + timedelta(seconds=derived_seconds + offset_seconds)


class PaperExecutionSimulator:
    def __init__(self, config: PaperExecutionConfig | None = None) -> None:
        self.config = config or PaperExecutionConfig()
        self._reports: dict[str, ExecutionReport] = {}

    def submit(self, risk_result: RiskCheckResult) -> ExecutionReport:
        if risk_result.decision.action is not PolicyAction.ALLOW:
            raise ValueError("Simulator only accepts approved risk decisions.")

        intent = normalize_order_intent(risk_result, self.config)
        existing = self._reports.get(intent.intent_id)
        if existing is not None:
            return existing

        report = self._execute_intent(intent, risk_result)
        self._reports[intent.intent_id] = report
        return report

    def _execute_intent(
        self,
        intent: OrderIntent,
        risk_result: RiskCheckResult,
    ) -> ExecutionReport:
        proposal = risk_result.proposal
        notional_usd = intent.quantity * proposal.entry_reference
        min_notional_usd = (
            proposal.execution_constraints.min_notional_usd or self.config.min_notional_usd
        )
        if notional_usd < min_notional_usd:
            return ExecutionReport(
                intent=intent,
                rejected=True,
                reject_reason="min_notional_not_met",
            )

        estimated_slippage_bps = max(
            self.config.base_slippage_bps,
            min(
                5.0,
                float(proposal.supporting_features.get("average_range_bps", 0.0)) / 10,
            ),
        )
        if intent.max_slippage_bps < estimated_slippage_bps:
            return ExecutionReport(
                intent=intent,
                rejected=True,
                reject_reason="slippage_limit_exceeded",
                estimated_slippage_bps=estimated_slippage_bps,
            )

        fill_price = proposal.entry_reference
        if intent.side is Side.BUY:
            fill_price = proposal.entry_reference * (1 + estimated_slippage_bps / 10_000)
        else:
            fill_price = proposal.entry_reference * (1 - estimated_slippage_bps / 10_000)

        fills = self._build_fills(intent, fill_price)
        return ExecutionReport(
            intent=intent,
            fills=fills,
            estimated_slippage_bps=estimated_slippage_bps,
        )

    def _build_fills(
        self,
        intent: OrderIntent,
        fill_price: float,
    ) -> list[FillEvent]:
        notional_usd = intent.quantity * fill_price
        if notional_usd >= self.config.partial_fill_notional_threshold:
            first_quantity = intent.quantity * self.config.partial_fill_fraction
            second_quantity = intent.quantity - first_quantity
            return [
                self._make_fill(
                    intent,
                    price=fill_price,
                    quantity=first_quantity,
                    status=FillStatus.PARTIALLY_FILLED,
                    offset_seconds=0,
                ),
                self._make_fill(
                    intent,
                    price=fill_price,
                    quantity=second_quantity,
                    status=FillStatus.FILLED,
                    offset_seconds=1,
                ),
            ]

        return [
            self._make_fill(
                intent,
                price=fill_price,
                quantity=intent.quantity,
                status=FillStatus.FILLED,
                offset_seconds=0,
            )
        ]

    def _make_fill(
        self,
        intent: OrderIntent,
        price: float,
        quantity: float,
        status: FillStatus,
        offset_seconds: int,
    ) -> FillEvent:
        notional_usd = price * quantity
        fee_usd = notional_usd * (self.config.fee_bps / 10_000)
        return FillEvent(
            intent_id=intent.intent_id,
            symbol=intent.symbol,
            side=intent.side,
            status=status,
            price=price,
            quantity=quantity,
            notional_usd=notional_usd,
            fee_usd=fee_usd,
            liquidity_role=LiquidityRole.TAKER,
            timestamp=_deterministic_timestamp(intent.intent_id, offset_seconds),
            mode=intent.mode,
        )
