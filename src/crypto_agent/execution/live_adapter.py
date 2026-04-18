from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import NAMESPACE_URL, uuid5

from crypto_agent.execution.models import (
    LiveTransmissionAck,
    LiveTransmissionOrderState,
    LiveTransmissionRequest,
    VenueExecutionAck,
    VenueOrderRequest,
    VenueOrderState,
)
from crypto_agent.market_data.live_models import LiveMarketState
from crypto_agent.market_data.venue_constraints import VenueSymbolConstraints
from crypto_agent.types import OrderIntent


def _utc_now() -> datetime:
    return datetime.now(UTC)


class SandboxExecutionAdapter(Protocol):
    venue: str
    sandbox: bool

    def submit_order(self, request: VenueOrderRequest) -> VenueExecutionAck: ...

    def fetch_order_state(
        self,
        *,
        client_order_id: str,
        request: VenueOrderRequest,
    ) -> VenueOrderState: ...

    def cancel_order(
        self,
        *,
        client_order_id: str,
        request: VenueOrderRequest,
    ) -> VenueOrderState: ...


class LiveExecutionAdapter(Protocol):
    venue: str

    def submit_order(self, request: LiveTransmissionRequest) -> LiveTransmissionAck: ...

    def fetch_order_state(
        self,
        *,
        client_order_id: str,
        request: LiveTransmissionRequest,
    ) -> LiveTransmissionOrderState: ...

    def cancel_order(
        self,
        *,
        client_order_id: str,
        request: LiveTransmissionRequest,
    ) -> LiveTransmissionOrderState: ...


class ScriptedSandboxExecutionAdapter:
    def __init__(
        self,
        *,
        venue: str = "binance_spot_testnet",
        submit_fn: Callable[[VenueOrderRequest], VenueExecutionAck],
        fetch_state_fn: Callable[[str, VenueOrderRequest], VenueOrderState],
        cancel_fn: Callable[[str, VenueOrderRequest], VenueOrderState],
    ) -> None:
        self.venue = venue
        self.sandbox = True
        self._submit_fn = submit_fn
        self._fetch_state_fn = fetch_state_fn
        self._cancel_fn = cancel_fn

    def submit_order(self, request: VenueOrderRequest) -> VenueExecutionAck:
        return self._submit_fn(request)

    def fetch_order_state(
        self,
        *,
        client_order_id: str,
        request: VenueOrderRequest,
    ) -> VenueOrderState:
        return self._fetch_state_fn(client_order_id, request)

    def cancel_order(
        self,
        *,
        client_order_id: str,
        request: VenueOrderRequest,
    ) -> VenueOrderState:
        return self._cancel_fn(client_order_id, request)


class BinanceSpotSandboxExecutionAdapter(ScriptedSandboxExecutionAdapter):
    def __init__(
        self,
        *,
        submit_fn: Callable[[VenueOrderRequest], VenueExecutionAck],
        fetch_state_fn: Callable[[str, VenueOrderRequest], VenueOrderState],
        cancel_fn: Callable[[str, VenueOrderRequest], VenueOrderState],
    ) -> None:
        super().__init__(
            venue="binance_spot_testnet",
            submit_fn=submit_fn,
            fetch_state_fn=fetch_state_fn,
            cancel_fn=cancel_fn,
        )


class ScriptedLiveExecutionAdapter:
    def __init__(
        self,
        *,
        venue: str = "binance_spot",
        submit_fn: Callable[[LiveTransmissionRequest], LiveTransmissionAck],
        fetch_state_fn: Callable[[str, LiveTransmissionRequest], LiveTransmissionOrderState],
        cancel_fn: Callable[[str, LiveTransmissionRequest], LiveTransmissionOrderState],
    ) -> None:
        self.venue = venue
        self._submit_fn = submit_fn
        self._fetch_state_fn = fetch_state_fn
        self._cancel_fn = cancel_fn

    def submit_order(self, request: LiveTransmissionRequest) -> LiveTransmissionAck:
        return self._submit_fn(request)

    def fetch_order_state(
        self,
        *,
        client_order_id: str,
        request: LiveTransmissionRequest,
    ) -> LiveTransmissionOrderState:
        return self._fetch_state_fn(client_order_id, request)

    def cancel_order(
        self,
        *,
        client_order_id: str,
        request: LiveTransmissionRequest,
    ) -> LiveTransmissionOrderState:
        return self._cancel_fn(client_order_id, request)


def build_venue_order_request(
    *,
    intent: OrderIntent,
    constraints: VenueSymbolConstraints,
    market_state: LiveMarketState,
    execution_mode: Literal["shadow", "sandbox"],
) -> VenueOrderRequest:
    resolved_venue = (
        constraints.venue
        if execution_mode == "shadow" or constraints.venue.endswith("_testnet")
        else f"{constraints.venue}_testnet"
    )
    client_order_id = str(
        uuid5(
            NAMESPACE_URL,
            f"{resolved_venue}:{execution_mode}:{intent.intent_id}",
        )
    )
    request_id = str(
        uuid5(
            NAMESPACE_URL,
            f"{client_order_id}:{intent.proposal_id}:{intent.symbol}",
        )
    )
    quantity = constraints.normalize_quantity(intent.quantity)
    price = (
        constraints.normalize_price(intent.limit_price) if intent.limit_price is not None else None
    )
    reference_price = (
        price
        if price is not None
        else market_state.order_book.asks[0].price
        if intent.side.value == "buy"
        else market_state.order_book.bids[0].price
    )
    estimated_notional_usd = quantity * reference_price
    ready = quantity > 0 and constraints.satisfies_min_notional(
        price=reference_price,
        quantity=quantity,
    )

    return VenueOrderRequest(
        request_id=request_id,
        client_order_id=client_order_id,
        venue=resolved_venue,
        execution_mode=execution_mode,
        sandbox=execution_mode == "sandbox",
        proposal_id=intent.proposal_id,
        intent_id=intent.intent_id,
        symbol=intent.symbol,
        side=intent.side.value,
        order_type=intent.order_type.value,
        time_in_force=intent.time_in_force.value,
        quantity=quantity,
        price=price,
        reference_price=reference_price,
        estimated_notional_usd=estimated_notional_usd,
        min_notional_usd=constraints.min_notional,
        normalization_status="ready" if ready else "rejected",
        normalization_reject_reason=None if ready else "venue_min_notional_not_met",
    )


def build_shadow_ack(
    request: VenueOrderRequest,
    *,
    observed_at: datetime | None = None,
) -> VenueExecutionAck:
    return VenueExecutionAck(
        request_id=request.request_id,
        client_order_id=request.client_order_id,
        venue=request.venue,
        execution_mode="shadow",
        sandbox=False,
        intent_id=request.intent_id,
        status="would_send" if request.normalization_status == "ready" else "rejected",
        reject_reason=request.normalization_reject_reason,
        observed_at=observed_at or _utc_now(),
    )


def build_shadow_state(
    request: VenueOrderRequest,
    *,
    updated_at: datetime | None = None,
) -> VenueOrderState:
    return VenueOrderState(
        request_id=request.request_id,
        client_order_id=request.client_order_id,
        venue=request.venue,
        execution_mode="shadow",
        sandbox=False,
        intent_id=request.intent_id,
        state="shadow_only" if request.normalization_status == "ready" else "rejected",
        terminal=True,
        updated_at=updated_at or _utc_now(),
    )
