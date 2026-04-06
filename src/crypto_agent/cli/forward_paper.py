from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, cast

from crypto_agent.config import load_settings
from crypto_agent.policy.live_controls import (
    default_live_control_config,
    default_manual_control_state,
)
from crypto_agent.policy.readiness import default_live_readiness_status
from crypto_agent.runtime.loop import run_forward_paper_runtime


def _symbol_cap(value: str) -> tuple[str, float]:
    symbol, separator, raw_cap = value.partition("=")
    if separator != "=" or not symbol or not raw_cap:
        raise argparse.ArgumentTypeError("expected SYMBOL=CAP format")
    try:
        cap = float(raw_cap)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("cap must be numeric") from exc
    if cap < 0:
        raise argparse.ArgumentTypeError("cap must be non-negative")
    return symbol.strip().upper(), cap


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
        "--execution-mode",
        choices=("paper", "shadow", "sandbox"),
        default="paper",
        help="Execution adapter mode for the forward runtime.",
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
    parser.add_argument(
        "--allow-execution-mode",
        action="append",
        choices=("paper", "shadow", "sandbox"),
        default=None,
        help="Explicitly allowed execution mode. Repeat to build the allowlist.",
    )
    parser.add_argument(
        "--allowed-symbol",
        action="append",
        default=None,
        help="Explicitly allowed symbol. Repeat to build the allowlist.",
    )
    parser.add_argument(
        "--per-symbol-max-notional",
        action="append",
        type=_symbol_cap,
        default=None,
        help="Per-symbol notional cap in SYMBOL=CAP format. Repeat as needed.",
    )
    parser.add_argument(
        "--max-session-loss-fraction",
        type=float,
        default=None,
        help="Block future non-paper progression after a session loss above this fraction.",
    )
    parser.add_argument(
        "--max-daily-loss-fraction",
        type=float,
        default=None,
        help="Block sessions when cumulative realized loss exceeds this fraction.",
    )
    parser.add_argument(
        "--max-open-positions",
        type=int,
        default=None,
        help="Maximum allowed open positions before the runtime is blocked.",
    )
    parser.add_argument(
        "--manual-approval-above-notional-usd",
        type=float,
        default=None,
        help="Require manual approval above this estimated request notional.",
    )
    parser.add_argument(
        "--manual-approval-granted",
        action="store_true",
        help="Grant manual approval for requests above the configured threshold.",
    )
    parser.add_argument(
        "--manual-halt",
        action="store_true",
        help="Persist manual halt active for this runtime.",
    )
    parser.add_argument(
        "--manual-resume",
        action="store_true",
        help="Clear persisted manual halt state for this runtime.",
    )
    parser.add_argument(
        "--readiness-status",
        choices=("ready", "not_ready"),
        default=None,
        help="Explicit operator readiness status for this runtime.",
    )
    parser.add_argument(
        "--readiness-note",
        default=None,
        help="Operator note persisted into the readiness artifact.",
    )
    parser.add_argument(
        "--limited-live-gate-status",
        choices=("not_ready", "ready_for_review"),
        default=None,
        help="Future limited-live gate status. Does not enable live execution.",
    )
    parser.add_argument(
        "--binance-base-url",
        default=None,
        help=(
            "Override the Binance REST base URL (default: https://api.binance.com). "
            "Use to point at an alternate endpoint when the default is geo/IP restricted."
        ),
    )
    parser.add_argument(
        "--live-market-poll-retry-count",
        type=int,
        default=2,
        help=(
            "Number of additional retry attempts after a transient live-market fetch failure"
            " (default: 2)."
        ),
    )
    parser.add_argument(
        "--live-market-poll-retry-delay-seconds",
        type=float,
        default=2.0,
        help="Seconds to wait between live-market fetch retry attempts (default: 2.0).",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.market_source == "replay" and args.replay_path is None:
        parser.error("replay_path is required when --market-source=replay")
    if args.market_source == "binance_spot" and args.live_symbol is None:
        parser.error("--live-symbol is required when --market-source=binance_spot")
    if args.manual_halt and args.manual_resume:
        parser.error("--manual-halt and --manual-resume are mutually exclusive")
    market_source = cast(Literal["replay", "binance_spot"], args.market_source)
    settings = load_settings(args.config)
    runtime_control_id = args.runtime_id
    updated_at = datetime.now(UTC)
    controls = default_live_control_config(
        runtime_id=runtime_control_id,
        settings=settings,
        updated_at=updated_at,
    )
    if args.allow_execution_mode is not None:
        controls = controls.model_copy(
            update={"allowed_execution_modes": args.allow_execution_mode}
        )
    if args.allowed_symbol is not None:
        controls = controls.model_copy(update={"symbol_allowlist": args.allowed_symbol})
    if args.per_symbol_max_notional is not None:
        controls = controls.model_copy(
            update={"per_symbol_max_notional_usd": dict(args.per_symbol_max_notional)}
        )
    if args.max_session_loss_fraction is not None:
        controls = controls.model_copy(
            update={"max_session_loss_fraction": args.max_session_loss_fraction}
        )
    if args.max_daily_loss_fraction is not None:
        controls = controls.model_copy(
            update={"max_daily_loss_fraction": args.max_daily_loss_fraction}
        )
    if args.max_open_positions is not None:
        controls = controls.model_copy(update={"max_open_positions": args.max_open_positions})
    if args.manual_approval_above_notional_usd is not None:
        controls = controls.model_copy(
            update={"manual_approval_above_notional_usd": args.manual_approval_above_notional_usd}
        )

    readiness = default_live_readiness_status(
        runtime_id=runtime_control_id,
        updated_at=updated_at,
    )
    if args.readiness_status is not None:
        readiness = readiness.model_copy(update={"status": args.readiness_status})
    if args.readiness_note is not None:
        readiness = readiness.model_copy(update={"note": args.readiness_note})
    if args.limited_live_gate_status is not None:
        readiness = readiness.model_copy(
            update={"limited_live_gate_status": args.limited_live_gate_status}
        )

    manual_controls = default_manual_control_state(
        runtime_id=runtime_control_id,
        updated_at=updated_at,
    )
    if args.manual_halt:
        manual_controls = manual_controls.model_copy(update={"halt_active": True})
    if args.manual_resume:
        manual_controls = manual_controls.model_copy(
            update={"halt_active": False, "halt_reason": None}
        )
    if args.manual_approval_granted:
        manual_controls = manual_controls.model_copy(update={"approval_granted": True})

    result = run_forward_paper_runtime(
        args.replay_path,
        settings=settings,
        runtime_id=args.runtime_id,
        session_interval_seconds=args.session_interval_seconds,
        equity_usd=args.equity_usd,
        execution_mode=cast(Literal["paper", "shadow", "sandbox"], args.execution_mode),
        max_sessions=args.max_sessions,
        market_source=market_source,
        live_symbol=args.live_symbol,
        live_interval=args.live_interval,
        live_lookback_candles=args.live_lookback_candles,
        feed_stale_after_seconds=args.feed_stale_after_seconds,
        live_control_config=controls,
        readiness_status=readiness,
        manual_control_state=manual_controls,
        binance_base_url=args.binance_base_url,
        live_market_poll_retry_count=args.live_market_poll_retry_count,
        live_market_poll_retry_delay_seconds=args.live_market_poll_retry_delay_seconds,
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
                "account_state_path": str(result.account_state_path),
                "reconciliation_report_path": str(result.reconciliation_report_path),
                "recovery_status_path": str(result.recovery_status_path),
                "execution_mode": result.execution_mode,
                "execution_state_dir": str(result.execution_state_dir),
                "live_control_config_path": str(result.live_control_config_path),
                "live_control_status_path": str(result.live_control_status_path),
                "readiness_status_path": str(result.readiness_status_path),
                "manual_control_state_path": str(result.manual_control_state_path),
                "soak_evaluation_path": str(result.soak_evaluation_path),
                "shadow_evaluation_path": str(result.shadow_evaluation_path),
                "live_gate_decision_path": str(result.live_gate_decision_path),
                "live_gate_threshold_summary_path": str(result.live_gate_threshold_summary_path),
                "live_gate_report_path": str(result.live_gate_report_path),
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
