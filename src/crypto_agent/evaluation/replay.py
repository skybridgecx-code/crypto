from __future__ import annotations

from pathlib import Path

from crypto_agent.evaluation.models import ReplayResult
from crypto_agent.evaluation.scorecard import build_replay_pnl, build_scorecard
from crypto_agent.events.journal import AppendOnlyJournal
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.portfolio.positions import Position


def replay_journal(
    path: str | Path,
    *,
    replay_path: str | Path | None = None,
    starting_equity_usd: float | None = None,
    starting_positions: list[Position] | None = None,
) -> ReplayResult:
    journal = AppendOnlyJournal(path)
    events = journal.read_all()
    pnl = None
    if replay_path is not None and starting_equity_usd is not None:
        candles = load_candle_replay(Path(replay_path))
        final_close_by_symbol = {candle.symbol: candle.close for candle in candles}
        pnl = build_replay_pnl(
            events,
            final_close_by_symbol=final_close_by_symbol,
            starting_equity_usd=starting_equity_usd,
            starting_positions=starting_positions,
        )
    return ReplayResult(events=events, scorecard=build_scorecard(events), pnl=pnl)
