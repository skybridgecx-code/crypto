from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from crypto_agent.config import load_settings
from crypto_agent.runtime.loop import run_forward_paper_runtime


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run the forward paper runtime on a real clock using the validated paper harness."
        )
    )
    parser.add_argument("replay_path", help="Path to the replay candle fixture JSONL file.")
    parser.add_argument(
        "--config",
        default="config/paper.yaml",
        help="Path to the paper-mode settings file.",
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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    result = run_forward_paper_runtime(
        args.replay_path,
        settings=load_settings(args.config),
        runtime_id=args.runtime_id,
        session_interval_seconds=args.session_interval_seconds,
        equity_usd=args.equity_usd,
        max_sessions=args.max_sessions,
    )
    print(
        json.dumps(
            {
                "runtime_id": result.runtime_id,
                "registry_path": str(result.registry_path),
                "status_path": str(result.status_path),
                "history_path": str(result.history_path),
                "sessions_dir": str(result.sessions_dir),
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
