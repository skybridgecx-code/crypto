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
    parser.add_argument("--advisory-artifact-path", required=True)
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
        raise ValueError(
            f"forward_paper_experiment_command_failed:{' '.join(command)}:{detail}"
        )
    return _extract_json_object(completed.stdout)


def _sanitize_token(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9._-]+", "-", normalized)
    normalized = re.sub(r"-+", "-", normalized).strip("-")
    if not normalized:
        raise ValueError("forward_paper_experiment_invalid_token")
    return normalized


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
    advisory_artifact_path = str(Path(args.advisory_artifact_path).resolve())
    symbols = [symbol.strip().upper() for symbol in args.symbols if symbol.strip()]
    if not symbols:
        raise ValueError("forward_paper_experiment_empty_symbol_list")

    rows: list[dict[str, Any]] = []
    for symbol in symbols:
        symbol_token = _sanitize_token(symbol)
        prefix_token = _sanitize_token(args.run_id_prefix)
        advisory_runtime_id = f"{prefix_token}-{symbol_token}-advisory"
        control_runtime_id = f"{prefix_token}-{symbol_token}-control"

        advisory_result = cli_runner(
            _forward_paper_command(
                runtime_id=advisory_runtime_id,
                symbol=symbol,
                args=args,
                external_confirmation_path=advisory_artifact_path,
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
                "advisory_status_path": advisory_result.get("status_path"),
                "control_status_path": control_result.get("status_path"),
                "comparison_json_path": str(comparison_json_path),
                "comparison_report_path": str(comparison_report_path),
                "proposal_count_delta": int(delta.get("proposal_count", 0)),
                "event_count_delta": int(delta.get("event_count", 0)),
                "execution_request_count_delta": int(delta.get("execution_request_count", 0)),
                "advisory_marker_presence": advisory_run_payload.get(
                    "advisory_decision_marker_presence"
                ),
                "advisory_session_outcome_counts": advisory_run_payload.get(
                    "session_outcome_counts", {}
                ),
                "control_session_outcome_counts": control_run_payload.get(
                    "session_outcome_counts", {}
                ),
            }
        )

    experiment_payload = {
        "experiment_kind": "forward_paper_advisory_control_experiment_index_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_id_prefix": args.run_id_prefix,
        "advisory_artifact_path": advisory_artifact_path,
        "binance_base_url": args.binance_base_url,
        "execution_mode": args.execution_mode,
        "session_interval_seconds": args.session_interval_seconds,
        "max_sessions": args.max_sessions,
        "equity_usd": args.equity_usd,
        "live_interval": args.live_interval,
        "live_lookback_candles": args.live_lookback_candles,
        "feed_stale_after_seconds": args.feed_stale_after_seconds,
        "symbol_count": len(rows),
        "rows": rows,
    }
    return experiment_payload


def _render_index_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Forward-Paper Advisory vs Control Experiment Index",
        f"- run_id_prefix: `{payload['run_id_prefix']}`",
        f"- advisory_artifact_path: `{payload['advisory_artifact_path']}`",
        f"- binance_base_url: `{payload['binance_base_url']}`",
        f"- execution_mode: `{payload['execution_mode']}`",
        f"- session_interval_seconds: {payload['session_interval_seconds']}",
        f"- max_sessions: {payload['max_sessions']}",
        f"- symbol_count: {payload['symbol_count']}",
        "",
    ]
    for row in payload["rows"]:
        lines.extend(
            [
                f"## {row['symbol']}",
                f"- advisory_runtime_id: `{row['advisory_runtime_id']}`",
                f"- control_runtime_id: `{row['control_runtime_id']}`",
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
