from __future__ import annotations

from datetime import datetime
from math import fsum
from pathlib import Path
from typing import TYPE_CHECKING

from crypto_agent.enums import EventType, Side
from crypto_agent.evaluation.scorecard import (
    POSITION_EPSILON,
    InventoryPosition,
    apply_fill_to_inventory_position,
)
from crypto_agent.events.journal import AppendOnlyJournal
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.runtime.models import (
    ForwardPaperRuntimeAccountState,
    RuntimeAccountPosition,
)
from crypto_agent.types import FillEvent

if TYPE_CHECKING:
    from crypto_agent.runtime.models import ForwardPaperSessionSummary


def initial_runtime_account_state(
    *,
    runtime_id: str,
    starting_equity_usd: float,
    updated_at: datetime,
) -> ForwardPaperRuntimeAccountState:
    return ForwardPaperRuntimeAccountState(
        runtime_id=runtime_id,
        updated_at=updated_at,
        starting_equity_usd=starting_equity_usd,
        cash_balance_usd=starting_equity_usd,
        ending_equity_usd=starting_equity_usd,
    )


def _cash_delta(fill: FillEvent) -> float:
    return (
        -(fill.notional_usd + fill.fee_usd)
        if fill.side is Side.BUY
        else fill.notional_usd - fill.fee_usd
    )


def _final_close_by_symbol(path: Path) -> dict[str, float]:
    candles = load_candle_replay(path)
    return {candle.symbol: candle.close for candle in candles}


def _executed_sessions(
    session_summaries: list[ForwardPaperSessionSummary],
) -> list[ForwardPaperSessionSummary]:
    return sorted(
        (
            summary
            for summary in session_summaries
            if summary.status == "completed" and summary.session_outcome == "executed"
        ),
        key=lambda summary: summary.session_number,
    )


def build_runtime_account_state(
    *,
    runtime_id: str,
    starting_equity_usd: float,
    session_summaries: list[ForwardPaperSessionSummary],
    updated_at: datetime,
) -> ForwardPaperRuntimeAccountState:
    executed_sessions = _executed_sessions(session_summaries)
    if not executed_sessions:
        return initial_runtime_account_state(
            runtime_id=runtime_id,
            starting_equity_usd=starting_equity_usd,
            updated_at=updated_at,
        )

    positions: dict[str, InventoryPosition] = {}
    mark_prices: dict[str, float] = {}
    cash_balance_usd = starting_equity_usd
    gross_realized_pnl_usd = 0.0
    total_fee_usd = 0.0

    for summary in executed_sessions:
        if summary.journal_path is None:
            raise ValueError(f"Executed session is missing journal_path: {summary.session_id}")
        replay_source_path = summary.market_input_path or summary.replay_path
        if replay_source_path is None:
            raise ValueError(f"Executed session is missing market input path: {summary.session_id}")

        final_close_by_symbol = _final_close_by_symbol(Path(replay_source_path))
        events = AppendOnlyJournal(summary.journal_path).read_all()
        fills = sorted(
            (
                FillEvent.model_validate(event.payload)
                for event in events
                if event.event_type is EventType.ORDER_FILLED
            ),
            key=lambda fill: (fill.timestamp, fill.intent_id, fill.fill_id),
        )

        for fill in fills:
            current_position = positions.get(fill.symbol, InventoryPosition())
            next_position, realized_pnl = apply_fill_to_inventory_position(current_position, fill)
            gross_realized_pnl_usd += realized_pnl
            total_fee_usd += fill.fee_usd
            cash_balance_usd += _cash_delta(fill)

            if abs(next_position.quantity) < POSITION_EPSILON:
                positions.pop(fill.symbol, None)
                mark_prices.pop(fill.symbol, None)
            else:
                positions[fill.symbol] = next_position
                mark_prices[fill.symbol] = fill.price

        for symbol, position in list(positions.items()):
            preserved_mark = mark_prices.get(symbol, position.average_entry_price)
            mark_prices[symbol] = final_close_by_symbol.get(symbol, preserved_mark)

    runtime_positions = [
        RuntimeAccountPosition(
            symbol=symbol,
            quantity=position.quantity,
            entry_price=position.average_entry_price,
            mark_price=mark_prices.get(symbol, position.average_entry_price),
            market_value_usd=position.quantity
            * mark_prices.get(symbol, position.average_entry_price),
            unrealized_pnl_usd=position.quantity
            * (
                mark_prices.get(symbol, position.average_entry_price) - position.average_entry_price
            ),
        )
        for symbol, position in sorted(positions.items())
    ]

    ending_unrealized_pnl_usd = fsum(position.unrealized_pnl_usd for position in runtime_positions)
    ending_equity_usd = cash_balance_usd + fsum(
        position.market_value_usd for position in runtime_positions
    )

    latest_summary = executed_sessions[-1]
    return ForwardPaperRuntimeAccountState(
        runtime_id=runtime_id,
        as_of_session_id=latest_summary.session_id,
        as_of_run_id=latest_summary.run_id,
        updated_at=latest_summary.completed_at or updated_at,
        starting_equity_usd=starting_equity_usd,
        cash_balance_usd=cash_balance_usd,
        gross_position_notional_usd=fsum(
            abs(position.market_value_usd) for position in runtime_positions
        ),
        gross_realized_pnl_usd=gross_realized_pnl_usd,
        total_fee_usd=total_fee_usd,
        net_realized_pnl_usd=gross_realized_pnl_usd - total_fee_usd,
        ending_unrealized_pnl_usd=ending_unrealized_pnl_usd,
        ending_equity_usd=ending_equity_usd,
        return_fraction=(ending_equity_usd - starting_equity_usd) / starting_equity_usd,
        open_intent_ids=[],
        positions=runtime_positions,
    )
