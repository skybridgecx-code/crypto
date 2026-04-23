from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal, cast

from crypto_agent.config import load_settings
from crypto_agent.execution.live_adapter import ScriptedSandboxExecutionAdapter
from crypto_agent.execution.models import VenueExecutionAck, VenueOrderRequest, VenueOrderState
from crypto_agent.policy.live_controls import (
    default_live_control_config,
    default_manual_control_state,
)
from crypto_agent.policy.readiness import default_live_readiness_status
from crypto_agent.regime.base import RegimeConfig
from crypto_agent.runtime.loop import (
    run_forward_paper_runtime,
    run_live_market_preflight_probe,
)


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
        "--preflight-only",
        action="store_true",
        help=(
            "Probe live market availability once using the runtime live-market retry path, "
            "write live_market_preflight.json, and exit without starting sessions."
        ),
    )
    parser.add_argument(
        "--canary-only",
        action="store_true",
        help=(
            "Run a bounded shadow canary batch using the normal forward runtime, "
            "write shadow_canary_evaluation.json, and exit nonzero unless the canary passes."
        ),
    )

    parser.add_argument(
        "--sandbox-fixture-rehearsal",
        action="store_true",
        help=(
            "Allow replay-source sandbox rehearsal only for deterministic checked-in fixtures. "
            "Does not enable live execution."
        ),
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
        "--external-confirmation-path",
        default=None,
        help=(
            "Optional advisory external confirmation artifact path. "
            "This input can adjust confidence or veto proposals only; it cannot author "
            "entry/stop/take-profit fields."
        ),
    )
    parser.add_argument(
        "--regime-liquidity-stress-dollar-volume-threshold",
        type=float,
        default=None,
        help=(
            "Optional paper-only override for regime liquidity_stress_dollar_volume_threshold. "
            "Default behavior is unchanged when omitted."
        ),
    )
    parser.add_argument(
        "--regime-high-volatility-threshold",
        type=float,
        default=None,
        help="Optional paper-only override for regime high_volatility_threshold.",
    )
    parser.add_argument(
        "--regime-high-atr-pct-threshold",
        type=float,
        default=None,
        help="Optional paper-only override for regime high_atr_pct_threshold.",
    )
    parser.add_argument(
        "--regime-trend-return-threshold",
        type=float,
        default=None,
        help="Optional paper-only override for regime trend_return_threshold.",
    )
    parser.add_argument(
        "--regime-trend-range-bps-threshold",
        type=float,
        default=None,
        help="Optional paper-only override for regime trend_range_bps_threshold.",
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


def _build_cli_sandbox_execution_adapter() -> ScriptedSandboxExecutionAdapter:
    """Build a deterministic sandbox-only adapter for CLI rehearsals.

    This adapter is explicitly marked sandbox=True and never transmits live orders.
    It acknowledges ready requests and returns terminal filled states so operators can
    rehearse sandbox artifact generation through the normal runtime path.
    """

    def _submit(request: VenueOrderRequest) -> VenueExecutionAck:
        return VenueExecutionAck(
            request_id=request.request_id,
            client_order_id=request.client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            status="accepted",
            venue_order_id=f"sandbox-{request.client_order_id}",
            observed_at=datetime.now(UTC),
        )

    def _fetch_state(client_order_id: str, request: VenueOrderRequest) -> VenueOrderState:
        return VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id=f"sandbox-{client_order_id}",
            state="filled",
            terminal=True,
            filled_quantity=request.quantity,
            average_fill_price=request.reference_price,
            updated_at=datetime.now(UTC),
        )

    def _cancel(client_order_id: str, request: VenueOrderRequest) -> VenueOrderState:
        return VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id=f"sandbox-{client_order_id}",
            state="canceled",
            terminal=True,
            updated_at=datetime.now(UTC),
        )

    return ScriptedSandboxExecutionAdapter(
        submit_fn=_submit,
        fetch_state_fn=_fetch_state,
        cancel_fn=_cancel,
    )


def _build_regime_config_override(args: argparse.Namespace) -> RegimeConfig | None:
    override_values: dict[str, float] = {}
    if args.regime_liquidity_stress_dollar_volume_threshold is not None:
        override_values["liquidity_stress_dollar_volume_threshold"] = (
            args.regime_liquidity_stress_dollar_volume_threshold
        )
    if args.regime_high_volatility_threshold is not None:
        override_values["high_volatility_threshold"] = args.regime_high_volatility_threshold
    if args.regime_high_atr_pct_threshold is not None:
        override_values["high_atr_pct_threshold"] = args.regime_high_atr_pct_threshold
    if args.regime_trend_return_threshold is not None:
        override_values["trend_return_threshold"] = args.regime_trend_return_threshold
    if args.regime_trend_range_bps_threshold is not None:
        override_values["trend_range_bps_threshold"] = args.regime_trend_range_bps_threshold
    if not override_values:
        return None
    return RegimeConfig.model_validate(override_values)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.market_source == "replay" and args.replay_path is None:
        parser.error("replay_path is required when --market-source=replay")
    if args.market_source == "binance_spot" and args.live_symbol is None:
        parser.error("--live-symbol is required when --market-source=binance_spot")
    if args.preflight_only and args.market_source != "binance_spot":
        parser.error("--preflight-only requires --market-source=binance_spot")
    if args.preflight_only and args.canary_only:
        parser.error("--preflight-only and --canary-only are mutually exclusive")
    if args.canary_only and args.market_source != "binance_spot":
        parser.error("--canary-only requires --market-source=binance_spot")
    if args.canary_only and args.execution_mode != "shadow":
        parser.error("--canary-only requires --execution-mode=shadow")
    if args.sandbox_fixture_rehearsal and args.execution_mode != "sandbox":
        parser.error("--sandbox-fixture-rehearsal requires --execution-mode=sandbox")
    if args.sandbox_fixture_rehearsal and args.market_source != "replay":
        parser.error("--sandbox-fixture-rehearsal requires --market-source=replay")
    if args.sandbox_fixture_rehearsal and args.replay_path is None:
        parser.error("--sandbox-fixture-rehearsal requires replay_path")
    if args.sandbox_fixture_rehearsal and args.preflight_only:
        parser.error("--sandbox-fixture-rehearsal cannot be used with --preflight-only")
    if args.sandbox_fixture_rehearsal and args.canary_only:
        parser.error("--sandbox-fixture-rehearsal cannot be used with --canary-only")
    if args.manual_halt and args.manual_resume:
        parser.error("--manual-halt and --manual-resume are mutually exclusive")
    regime_config_override = _build_regime_config_override(args)
    if regime_config_override is not None and args.execution_mode != "paper":
        parser.error("Regime config overrides are paper-only and require --execution-mode=paper")
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

    if args.preflight_only:
        preflight_result = run_live_market_preflight_probe(
            settings=settings,
            runtime_id=args.runtime_id,
            market_source=cast(Literal["binance_spot"], market_source),
            live_symbol=args.live_symbol,
            live_interval=args.live_interval,
            live_lookback_candles=args.live_lookback_candles,
            feed_stale_after_seconds=args.feed_stale_after_seconds,
            binance_base_url=args.binance_base_url,
            live_market_poll_retry_count=args.live_market_poll_retry_count,
            live_market_poll_retry_delay_seconds=args.live_market_poll_retry_delay_seconds,
        )
        print(
            json.dumps(
                {
                    "runtime_id": preflight_result.runtime_id,
                    "preflight_path": str(preflight_result.artifact_path),
                    "status": preflight_result.artifact.status,
                    "success": preflight_result.artifact.success,
                    "single_probe_success": preflight_result.artifact.single_probe_success,
                    "batch_readiness": preflight_result.artifact.batch_readiness,
                    "batch_readiness_reason": preflight_result.artifact.batch_readiness_reason,
                    "attempt_count_used": preflight_result.artifact.attempt_count_used,
                    "stability_probe_attempt_count_used": (
                        preflight_result.artifact.stability_probe_attempt_count_used
                    ),
                    "stability_failure_status": preflight_result.artifact.stability_failure_status,
                    "stability_window_result": preflight_result.artifact.stability_window_result,
                    "feed_health_status": preflight_result.artifact.feed_health_status,
                    "feed_health_message": preflight_result.artifact.feed_health_message,
                    "configured_base_url": preflight_result.artifact.configured_base_url,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0 if preflight_result.artifact.success else 1

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
        sandbox_fixture_rehearsal=args.sandbox_fixture_rehearsal,
        sandbox_execution_adapter=(
            _build_cli_sandbox_execution_adapter() if args.execution_mode == "sandbox" else None
        ),
        external_confirmation_path=args.external_confirmation_path,
        regime_config_override=regime_config_override,
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
                "shadow_canary_evaluation_path": str(result.shadow_canary_evaluation_path),
                "live_market_preflight_path": str(result.live_market_preflight_path),
                "soak_evaluation_path": str(result.soak_evaluation_path),
                "shadow_evaluation_path": str(result.shadow_evaluation_path),
                "live_gate_config_path": str(result.live_gate_config_path)
                if result.live_gate_config_path is not None
                else None,
                "live_gate_decision_path": str(result.live_gate_decision_path),
                "live_gate_threshold_summary_path": str(result.live_gate_threshold_summary_path),
                "live_gate_report_path": str(result.live_gate_report_path),
                "live_launch_verdict_path": str(result.live_launch_verdict_path),
                "session_count": result.session_count,
                "session_ids": [session.session_id for session in result.session_summaries],
            },
            indent=2,
            sort_keys=True,
        )
    )
    if args.canary_only:
        canary = json.loads(result.shadow_canary_evaluation_path.read_text(encoding="utf-8"))
        return 0 if canary["state"] == "pass" else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
