from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run repeatable local advisory-vs-control forward-paper experiments across symbols."
        )
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        required=True,
        help="Symbol list, e.g. BTCUSDT ETHUSDT SOLUSDT.",
    )
    parser.add_argument(
        "--advisory-artifact-path",
        default=None,
        help="Shared advisory artifact path used as fallback for all symbols.",
    )
    parser.add_argument(
        "--symbol-advisory",
        action="append",
        default=None,
        help="Per-symbol advisory path mapping in SYMBOL=/path/to/artifact.json format.",
    )
    parser.add_argument("--binance-base-url", required=True)
    parser.add_argument("--run-id-prefix", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--config", default="config/paper.yaml")
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument(
        "--execution-mode",
        choices=("paper", "shadow", "sandbox"),
        default="paper",
    )
    parser.add_argument("--session-interval-seconds", type=int, default=60)
    parser.add_argument("--max-sessions", type=int, default=1)
    parser.add_argument("--equity-usd", type=float, default=100_000.0)
    parser.add_argument("--live-interval", default="1m")
    parser.add_argument("--live-lookback-candles", type=int, default=8)
    parser.add_argument("--feed-stale-after-seconds", type=int, default=120)
    parser.add_argument("--live-market-poll-retry-count", type=int, default=2)
    parser.add_argument("--live-market-poll-retry-delay-seconds", type=float, default=2.0)
    parser.add_argument(
        "--regime-liquidity-stress-dollar-volume-threshold",
        type=float,
        default=None,
    )
    parser.add_argument("--regime-high-volatility-threshold", type=float, default=None)
    parser.add_argument("--regime-high-atr-pct-threshold", type=float, default=None)
    parser.add_argument("--regime-trend-return-threshold", type=float, default=None)
    parser.add_argument("--regime-trend-range-bps-threshold", type=float, default=None)
    parser.add_argument("--mean-reversion-min-average-dollar-volume", type=float, default=None)
    parser.add_argument("--mean-reversion-zscore-entry-threshold", type=float, default=None)
    parser.add_argument("--mean-reversion-max-atr-pct", type=float, default=None)
    parser.add_argument("--breakout-min-average-dollar-volume", type=float, default=None)
    return parser


def _extract_json_object(raw_output: str) -> dict[str, Any]:
    text = raw_output.strip()
    if not text:
        raise ValueError("forward_paper_experiment_empty_cli_output")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("forward_paper_experiment_invalid_cli_json_output") from None
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("forward_paper_experiment_invalid_cli_object_output")
    return payload


def _run_cli_command(command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        detail = stderr or stdout or "no_output"
        raise ValueError(f"forward_paper_experiment_command_failed:{' '.join(command)}:{detail}")
    return _extract_json_object(completed.stdout)


def _sanitize_token(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise ValueError("forward_paper_experiment_invalid_token")
    return normalized


def _parse_symbol_advisory_mapping(raw_values: list[str] | None) -> dict[str, str]:
    if not raw_values:
        return {}
    mapping: dict[str, str] = {}
    for raw in raw_values:
        symbol, separator, artifact_path = raw.partition("=")
        normalized_symbol = symbol.strip().upper()
        normalized_path = artifact_path.strip()
        if separator != "=" or not normalized_symbol or not normalized_path:
            raise ValueError(f"forward_paper_experiment_invalid_symbol_advisory:{raw}")
        mapping[normalized_symbol] = str(Path(normalized_path).resolve())
    return mapping


def _resolve_advisory_for_symbol(
    *,
    symbol: str,
    per_symbol_mapping: dict[str, str],
    shared_artifact_path: str | None,
) -> tuple[str | None, str, bool]:
    if symbol in per_symbol_mapping:
        return per_symbol_mapping[symbol], "per_symbol", False
    if shared_artifact_path is not None:
        return shared_artifact_path, "shared_fallback", False
    return None, "none", True


def _forward_paper_command(
    *,
    runtime_id: str,
    symbol: str,
    args: argparse.Namespace,
    external_confirmation_path: str | None,
) -> list[str]:
    command = [
        sys.executable,
        "-m",
        "crypto_agent.cli.forward_paper",
        "--config",
        args.config,
        "--runtime-id",
        runtime_id,
        "--market-source",
        "binance_spot",
        "--execution-mode",
        args.execution_mode,
        "--session-interval-seconds",
        str(args.session_interval_seconds),
        "--max-sessions",
        str(args.max_sessions),
        "--equity-usd",
        str(args.equity_usd),
        "--live-symbol",
        symbol,
        "--live-interval",
        args.live_interval,
        "--live-lookback-candles",
        str(args.live_lookback_candles),
        "--feed-stale-after-seconds",
        str(args.feed_stale_after_seconds),
        "--binance-base-url",
        args.binance_base_url,
        "--live-market-poll-retry-count",
        str(args.live_market_poll_retry_count),
        "--live-market-poll-retry-delay-seconds",
        str(args.live_market_poll_retry_delay_seconds),
    ]
    if external_confirmation_path is not None:
        command.extend(
            [
                "--external-confirmation-path",
                external_confirmation_path,
            ]
        )
    if args.regime_liquidity_stress_dollar_volume_threshold is not None:
        command.extend(
            [
                "--regime-liquidity-stress-dollar-volume-threshold",
                str(args.regime_liquidity_stress_dollar_volume_threshold),
            ]
        )
    if args.regime_high_volatility_threshold is not None:
        command.extend(
            [
                "--regime-high-volatility-threshold",
                str(args.regime_high_volatility_threshold),
            ]
        )
    if args.regime_high_atr_pct_threshold is not None:
        command.extend(
            [
                "--regime-high-atr-pct-threshold",
                str(args.regime_high_atr_pct_threshold),
            ]
        )
    if args.regime_trend_return_threshold is not None:
        command.extend(
            [
                "--regime-trend-return-threshold",
                str(args.regime_trend_return_threshold),
            ]
        )
    if args.regime_trend_range_bps_threshold is not None:
        command.extend(
            [
                "--regime-trend-range-bps-threshold",
                str(args.regime_trend_range_bps_threshold),
            ]
        )
    if args.mean_reversion_min_average_dollar_volume is not None:
        command.extend(
            [
                "--mean-reversion-min-average-dollar-volume",
                str(args.mean_reversion_min_average_dollar_volume),
            ]
        )
    if args.mean_reversion_zscore_entry_threshold is not None:
        command.extend(
            [
                "--mean-reversion-zscore-entry-threshold",
                str(args.mean_reversion_zscore_entry_threshold),
            ]
        )
    if args.mean_reversion_max_atr_pct is not None:
        command.extend(
            [
                "--mean-reversion-max-atr-pct",
                str(args.mean_reversion_max_atr_pct),
            ]
        )
    if args.breakout_min_average_dollar_volume is not None:
        command.extend(
            [
                "--breakout-min-average-dollar-volume",
                str(args.breakout_min_average_dollar_volume),
            ]
        )
    return command


def _forward_paper_compare_command(
    *,
    advisory_runtime_id: str,
    control_runtime_id: str,
    runs_dir: Path,
    output_dir: Path,
) -> list[str]:
    return [
        sys.executable,
        "-m",
        "crypto_agent.cli.forward_paper_compare",
        "--advisory-run-id",
        advisory_runtime_id,
        "--control-run-id",
        control_runtime_id,
        "--runs-dir",
        str(runs_dir),
        "--output-dir",
        str(output_dir),
    ]


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"forward_paper_experiment_missing_output:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"forward_paper_experiment_invalid_json:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"forward_paper_experiment_invalid_object:{path}")
    return payload


def run_advisory_control_experiment(
    *,
    args: argparse.Namespace,
    cli_runner: Callable[[list[str]], dict[str, Any]] = _run_cli_command,
) -> dict[str, Any]:
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    comparisons_dir = output_dir / "comparisons"
    comparisons_dir.mkdir(parents=True, exist_ok=True)
    runs_dir = Path(args.runs_dir).resolve()
    advisory_artifact_path = (
        str(Path(args.advisory_artifact_path).resolve())
        if args.advisory_artifact_path is not None
        else None
    )
    per_symbol_mapping = _parse_symbol_advisory_mapping(args.symbol_advisory)
    symbols = [symbol.strip().upper() for symbol in args.symbols if symbol.strip()]
    if not symbols:
        raise ValueError("forward_paper_experiment_empty_symbol_list")
    if args.execution_mode != "paper" and (
        args.mean_reversion_min_average_dollar_volume is not None
        or args.mean_reversion_zscore_entry_threshold is not None
        or args.mean_reversion_max_atr_pct is not None
        or args.breakout_min_average_dollar_volume is not None
    ):
        raise ValueError("forward_paper_experiment_strategy_overrides_require_execution_mode_paper")
    regime_config_override: dict[str, float] = {}
    if args.regime_liquidity_stress_dollar_volume_threshold is not None:
        regime_config_override["liquidity_stress_dollar_volume_threshold"] = (
            args.regime_liquidity_stress_dollar_volume_threshold
        )
    if args.regime_high_volatility_threshold is not None:
        regime_config_override["high_volatility_threshold"] = args.regime_high_volatility_threshold
    if args.regime_high_atr_pct_threshold is not None:
        regime_config_override["high_atr_pct_threshold"] = args.regime_high_atr_pct_threshold
    if args.regime_trend_return_threshold is not None:
        regime_config_override["trend_return_threshold"] = args.regime_trend_return_threshold
    if args.regime_trend_range_bps_threshold is not None:
        regime_config_override["trend_range_bps_threshold"] = args.regime_trend_range_bps_threshold
    strategy_config_override: dict[str, dict[str, float]] = {}
    if args.mean_reversion_min_average_dollar_volume is not None:
        strategy_config_override.setdefault("mean_reversion", {})
        strategy_config_override["mean_reversion"]["min_average_dollar_volume"] = (
            args.mean_reversion_min_average_dollar_volume
        )
    if args.mean_reversion_zscore_entry_threshold is not None:
        strategy_config_override.setdefault("mean_reversion", {})
        strategy_config_override["mean_reversion"]["zscore_entry_threshold"] = (
            args.mean_reversion_zscore_entry_threshold
        )
    if args.mean_reversion_max_atr_pct is not None:
        strategy_config_override.setdefault("mean_reversion", {})
        strategy_config_override["mean_reversion"]["max_atr_pct"] = args.mean_reversion_max_atr_pct
    if args.breakout_min_average_dollar_volume is not None:
        strategy_config_override["breakout"] = {
            "min_average_dollar_volume": args.breakout_min_average_dollar_volume
        }

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        symbol_token = _sanitize_token(symbol)
        prefix_token = _sanitize_token(args.run_id_prefix)
        advisory_runtime_id = f"{prefix_token}-{symbol_token}-advisory"
        control_runtime_id = f"{prefix_token}-{symbol_token}-control"

        (
            resolved_advisory_artifact_path,
            advisory_artifact_resolution,
            advisory_lane_skipped,
        ) = _resolve_advisory_for_symbol(
            symbol=symbol,
            per_symbol_mapping=per_symbol_mapping,
            shared_artifact_path=advisory_artifact_path,
        )

        advisory_result: dict[str, Any] | None = None
        if not advisory_lane_skipped:
            advisory_result = cli_runner(
                _forward_paper_command(
                    runtime_id=advisory_runtime_id,
                    symbol=symbol,
                    args=args,
                    external_confirmation_path=resolved_advisory_artifact_path,
                )
            )
        control_result = cli_runner(
            _forward_paper_command(
                runtime_id=control_runtime_id,
                symbol=symbol,
                args=args,
                external_confirmation_path=None,
            )
        )
        comparison_json_path: Path | None = None
        comparison_report_path: Path | None = None
        delta: dict[str, Any] = {}
        advisory_run_payload: dict[str, Any] = {}
        control_run_payload: dict[str, Any] = {}
        if not advisory_lane_skipped:
            comparison_result = cli_runner(
                _forward_paper_compare_command(
                    advisory_runtime_id=advisory_runtime_id,
                    control_runtime_id=control_runtime_id,
                    runs_dir=runs_dir,
                    output_dir=comparisons_dir,
                )
            )
            comparison_json_path = Path(str(comparison_result["json_path"])).resolve()
            comparison_report_path = Path(str(comparison_result["report_path"])).resolve()
            comparison_payload = _load_json_file(comparison_json_path)
            delta = comparison_payload.get("delta", {})
            advisory_run_payload = comparison_payload.get("advisory_run", {})
            control_run_payload = comparison_payload.get("control_run", {})

        rows.append(
            {
                "symbol": symbol,
                "advisory_runtime_id": advisory_runtime_id,
                "control_runtime_id": control_runtime_id,
                "advisory_artifact_path_used": resolved_advisory_artifact_path,
                "advisory_artifact_resolution": advisory_artifact_resolution,
                "advisory_lane_skipped": advisory_lane_skipped,
                "advisory_skip_reason": (
                    "no_symbol_or_shared_advisory_artifact" if advisory_lane_skipped else None
                ),
                "advisory_status_path": advisory_result.get("status_path")
                if advisory_result is not None
                else None,
                "control_status_path": control_result.get("status_path"),
                "comparison_json_path": str(comparison_json_path)
                if comparison_json_path is not None
                else None,
                "comparison_report_path": str(comparison_report_path)
                if comparison_report_path is not None
                else None,
                "proposal_count_delta": int(delta.get("proposal_count", 0))
                if not advisory_lane_skipped
                else None,
                "event_count_delta": int(delta.get("event_count", 0))
                if not advisory_lane_skipped
                else None,
                "execution_request_count_delta": int(delta.get("execution_request_count", 0))
                if not advisory_lane_skipped
                else None,
                "advisory_marker_presence": advisory_run_payload.get(
                    "advisory_decision_marker_presence"
                )
                if not advisory_lane_skipped
                else "skipped",
                "advisory_session_outcome_counts": advisory_run_payload.get(
                    "session_outcome_counts", {}
                )
                if not advisory_lane_skipped
                else {},
                "control_session_outcome_counts": control_run_payload.get(
                    "session_outcome_counts", {}
                )
                if not advisory_lane_skipped
                else {},
            }
        )

    experiment_payload = {
        "experiment_kind": "forward_paper_advisory_control_experiment_index_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id_prefix": args.run_id_prefix,
        "advisory_artifact_path": advisory_artifact_path,
        "symbol_advisory_mapping": per_symbol_mapping,
        "binance_base_url": args.binance_base_url,
        "execution_mode": args.execution_mode,
        "session_interval_seconds": args.session_interval_seconds,
        "max_sessions": args.max_sessions,
        "equity_usd": args.equity_usd,
        "live_interval": args.live_interval,
        "live_lookback_candles": args.live_lookback_candles,
        "feed_stale_after_seconds": args.feed_stale_after_seconds,
        "regime_config_override": regime_config_override,
        "strategy_config_override": strategy_config_override,
        "symbol_count": len(rows),
        "rows": rows,
    }
    return experiment_payload


def _render_index_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Forward-Paper Advisory vs Control Experiment Index",
        f"- run_id_prefix: `{payload['run_id_prefix']}`",
        f"- advisory_artifact_path: `{payload['advisory_artifact_path']}`",
        (
            "- symbol_advisory_mapping: "
            f"`{json.dumps(payload['symbol_advisory_mapping'], sort_keys=True)}`"
        ),
        f"- binance_base_url: `{payload['binance_base_url']}`",
        f"- execution_mode: `{payload['execution_mode']}`",
        f"- session_interval_seconds: {payload['session_interval_seconds']}",
        f"- max_sessions: {payload['max_sessions']}",
        (
            "- regime_config_override: "
            f"`{json.dumps(payload['regime_config_override'], sort_keys=True)}`"
        ),
        (
            "- strategy_config_override: "
            f"`{json.dumps(payload['strategy_config_override'], sort_keys=True)}`"
        ),
        f"- symbol_count: {payload['symbol_count']}",
        "",
    ]
    for row in payload["rows"]:
        lines.extend(
            [
                f"## {row['symbol']}",
                f"- advisory_runtime_id: `{row['advisory_runtime_id']}`",
                f"- control_runtime_id: `{row['control_runtime_id']}`",
                f"- advisory_artifact_path_used: `{row['advisory_artifact_path_used']}`",
                f"- advisory_artifact_resolution: `{row['advisory_artifact_resolution']}`",
                f"- advisory_lane_skipped: {row['advisory_lane_skipped']}",
                f"- advisory_skip_reason: `{row['advisory_skip_reason']}`",
                f"- comparison_report_path: `{row['comparison_report_path']}`",
                f"- comparison_json_path: `{row['comparison_json_path']}`",
                f"- proposal_count_delta: {row['proposal_count_delta']}",
                f"- event_count_delta: {row['event_count_delta']}",
                f"- execution_request_count_delta: {row['execution_request_count_delta']}",
                f"- advisory_marker_presence: `{row['advisory_marker_presence']}`",
                (
                    "- advisory_session_outcome_counts: "
                    f"`{json.dumps(row['advisory_session_outcome_counts'], sort_keys=True)}`"
                ),
                (
                    "- control_session_outcome_counts: "
                    f"`{json.dumps(row['control_session_outcome_counts'], sort_keys=True)}`"
                ),
                "",
            ]
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    payload = run_advisory_control_experiment(args=args)
    prefix_token = _sanitize_token(args.run_id_prefix)
    index_json_path = output_dir / f"{prefix_token}.forward_paper_experiment.index.json"
    index_report_path = output_dir / f"{prefix_token}.forward_paper_experiment.index.md"

    index_json_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    index_report_path.write_text(
        _render_index_markdown(payload),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "experiment_kind": payload["experiment_kind"],
                "index_json_path": str(index_json_path),
                "index_report_path": str(index_report_path),
                "symbol_count": payload["symbol_count"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
