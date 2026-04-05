from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from typing import Literal, cast

from crypto_agent.config import load_settings
from crypto_agent.runtime.loop import run_forward_paper_runtime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the forward paper runtime on a real clock using the validated paper harness."
        )
    )
    parser.add_argument(
        "replay_path",
        nargs="?",
        default=None,
        help="Path to the replay candle fixture JSONL file for replay-source runtime mode.",
    )
    parser.add_argument(
        "--config",
        default="config/paper.yaml",
        help="Path to the paper-mode settings file.",
    )
    parser.add_argument(
        "--market-source",
        choices=("replay", "binance_spot"),
        default="replay",
        help="Paper runtime market input source.",
    )
    parser.add_argument(
        "--runtime-id",
        required=True,
        help="Explicit persistent runtime identifier.",
    )
    parser.add_argument(
        "--session-interval-seconds",
        type=int,
        default=60,
        help="Real-clock interval between paper sessions.",
    )
    parser.add_argument(
        "--max-sessions",
        type=int,
        default=1,
        help="Maximum sessions to execute in this invocation.",
    )
    parser.add_argument(
        "--equity-usd",
        type=float,
        default=100_000.0,
        help="Starting paper equity for each forward paper session.",
    )
    parser.add_argument(
        "--live-symbol",
        default=None,
        help="Live market symbol when --market-source=binance_spot.",
    )
    parser.add_argument(
        "--live-interval",
        default="1m",
        help="Live candle interval when --market-source=binance_spot.",
    )
    parser.add_argument(
        "--live-lookback-candles",
        type=int,
        default=8,
        help="Closed live candles to persist into each paper session.",
    )
    parser.add_argument(
        "--feed-stale-after-seconds",
        type=int,
        default=120,
        help="Feed freshness threshold for live market input.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.market_source == "replay" and args.replay_path is None:
        parser.error("replay_path is required when --market-source=replay")
    if args.market_source == "binance_spot" and args.live_symbol is None:
        parser.error("--live-symbol is required when --market-source=binance_spot")
    market_source = cast(Literal["replay", "binance_spot"], args.market_source)
    result = run_forward_paper_runtime(
        args.replay_path,
        settings=load_settings(args.config),
        runtime_id=args.runtime_id,
        session_interval_seconds=args.session_interval_seconds,
        equity_usd=args.equity_usd,
        max_sessions=args.max_sessions,
        market_source=market_source,
        live_symbol=args.live_symbol,
        live_interval=args.live_interval,
        live_lookback_candles=args.live_lookback_candles,
        feed_stale_after_seconds=args.feed_stale_after_seconds,
    )
    print(
        json.dumps(
            {
                "runtime_id": result.runtime_id,
                "registry_path": str(result.registry_path),
                "status_path": str(result.status_path),
                "history_path": str(result.history_path),
                "sessions_dir": str(result.sessions_dir),
                "live_market_status_path": str(result.live_market_status_path)
                if result.live_market_status_path is not None
                else None,
                "venue_constraints_path": str(result.venue_constraints_path)
                if result.venue_constraints_path is not None
                else None,
                "session_count": result.session_count,
                "session_ids": [session.session_id for session in result.session_summaries],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
