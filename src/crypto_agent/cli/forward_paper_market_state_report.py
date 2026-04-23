from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.market_data.live_models import LiveMarketState
from crypto_agent.regime.rules import classify_regime

_SESSION_MARKET_STATE_RE = re.compile(r"^session-([0-9]{4})\.live_market_state\.json$")


class _FeatureAccumulator:
    def __init__(self) -> None:
        self.count = 0
        self.sum = 0.0
        self.min: float | None = None
        self.max: float | None = None

    def add(self, value: float) -> None:
        self.count += 1
        self.sum += value
        if self.min is None or value < self.min:
            self.min = value
        if self.max is None or value > self.max:
            self.max = value

    def to_summary(self) -> dict[str, float | int] | None:
        if self.count == 0 or self.min is None or self.max is None:
            return None
        return {
            "count": self.count,
            "min": self.min,
            "max": self.max,
            "avg": self.sum / self.count,
        }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate forward-paper live market-state artifacts across runtime IDs."
    )
    parser.add_argument(
        "--run-id",
        action="append",
        required=True,
        help="Forward-paper runtime ID to aggregate. Repeat for multiple runs.",
    )
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Output directory for aggregate artifacts "
            "(default: <runs_dir>/market_state_reports)."
        ),
    )
    return parser


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"forward_paper_market_state_missing_artifact:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"forward_paper_market_state_invalid_json:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"forward_paper_market_state_invalid_object:{path}")
    return payload


def _safe_float(value: object) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _safe_non_negative_int(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        try:
            return max(0, int(value))
        except ValueError:
            return 0
    return 0


def _counter_to_sorted_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}:{value}" for key, value in sorted(counts.items()))


def _load_session_market_states(run_dir: Path) -> list[tuple[int, str, LiveMarketState]]:
    sessions_dir = run_dir / "sessions"
    if not sessions_dir.is_dir():
        raise ValueError(f"forward_paper_market_state_missing_sessions_dir:{sessions_dir}")

    state_paths: list[tuple[int, str, Path]] = []
    for path in sorted(sessions_dir.iterdir()):
        if not path.is_file():
            continue
        match = _SESSION_MARKET_STATE_RE.match(path.name)
        if match is None:
            continue
        session_number = int(match.group(1))
        session_id = f"session-{session_number:04d}"
        state_paths.append((session_number, session_id, path))

    records: list[tuple[int, str, LiveMarketState]] = []
    for session_number, session_id, path in sorted(state_paths, key=lambda item: item[0]):
        payload = _read_json_object(path)
        try:
            state = LiveMarketState.model_validate(payload)
        except Exception as exc:
            raise ValueError(f"forward_paper_market_state_invalid_payload:{path}:{exc}") from exc
        records.append((session_number, session_id, state))
    return records


def _aggregate_run(*, run_id: str, runs_dir: Path) -> dict[str, Any]:
    run_dir = runs_dir / run_id
    if not run_dir.is_dir():
        raise ValueError(f"forward_paper_market_state_missing_run_dir:{run_dir}")

    records = _load_session_market_states(run_dir)
    regime_label_counts: Counter[str] = Counter()
    feature_unavailable_session_count = 0
    feed_health_counts: Counter[str] = Counter()

    feature_accumulators = {
        "momentum_return": _FeatureAccumulator(),
        "realized_volatility": _FeatureAccumulator(),
        "atr": _FeatureAccumulator(),
        "atr_pct": _FeatureAccumulator(),
        "average_volume": _FeatureAccumulator(),
        "average_dollar_volume": _FeatureAccumulator(),
        "average_range_bps": _FeatureAccumulator(),
    }

    session_snapshots: list[dict[str, Any]] = []
    for _, session_id, state in records:
        feed_health_counts.update([state.feed_health.status])
        candles = state.candles
        last_candle = candles[-1] if candles else None
        best_bid = state.order_book.bids[0].price if state.order_book.bids else None
        best_ask = state.order_book.asks[0].price if state.order_book.asks else None
        spread_bps: float | None = None
        if best_bid is not None and best_ask is not None and best_ask > 0:
            mid = (best_bid + best_ask) / 2
            if mid > 0:
                spread_bps = ((best_ask - best_bid) / mid) * 10_000

        regime_label: str | None = None
        regime_confidence: float | None = None
        regime_reasons: list[str] = []
        if len(candles) >= 2:
            features = build_feature_snapshot(candles, lookback_periods=len(candles))
            regime = classify_regime(features)
            regime_label = regime.label.value
            regime_confidence = regime.confidence
            regime_reasons = list(regime.reasons)
            regime_label_counts.update([regime_label])

            feature_accumulators["momentum_return"].add(features.momentum_return)
            feature_accumulators["realized_volatility"].add(features.realized_volatility)
            feature_accumulators["atr"].add(features.atr)
            feature_accumulators["atr_pct"].add(features.atr_pct)
            feature_accumulators["average_volume"].add(features.average_volume)
            feature_accumulators["average_dollar_volume"].add(features.average_dollar_volume)
            feature_accumulators["average_range_bps"].add(features.average_range_bps)
        else:
            feature_unavailable_session_count += 1

        session_snapshots.append(
            {
                "session_id": session_id,
                "symbol": state.symbol,
                "interval": state.interval,
                "polled_at": state.polled_at.isoformat(),
                "feed_health_status": state.feed_health.status,
                "feed_health_message": state.feed_health.message,
                "candle_count": len(candles),
                "last_candle_close_time": (
                    last_candle.close_time.isoformat() if last_candle is not None else None
                ),
                "last_candle_close": last_candle.close if last_candle is not None else None,
                "last_candle_volume": last_candle.volume if last_candle is not None else None,
                "best_bid": best_bid,
                "best_ask": best_ask,
                "spread_bps": spread_bps,
                "regime_label": regime_label,
                "regime_confidence": regime_confidence,
                "regime_reasons": regime_reasons,
            }
        )

    feature_summaries: dict[str, dict[str, float | int]] = {}
    for key, accumulator in feature_accumulators.items():
        summary = accumulator.to_summary()
        if summary is not None:
            feature_summaries[key] = summary

    return {
        "run_id": run_id,
        "session_count": len(records),
        "feed_health_status_counts": _counter_to_sorted_dict(feed_health_counts),
        "regime_label_counts": _counter_to_sorted_dict(regime_label_counts),
        "feature_unavailable_session_count": feature_unavailable_session_count,
        "feature_summaries": feature_summaries,
        "session_snapshots": session_snapshots,
    }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Forward-Paper Market-State Aggregate Report",
        f"- run_count: {payload['run_count']}",
        "",
    ]
    for run in payload["runs"]:
        lines.extend(
            [
                f"## {run['run_id']}",
                f"- session_count: {run['session_count']}",
                (
                    "- feed_health_status_counts: "
                    f"`{_format_counts(run['feed_health_status_counts'])}`"
                ),
                f"- regime_label_counts: `{_format_counts(run['regime_label_counts'])}`",
                (
                    "- feature_unavailable_session_count: "
                    f"{run['feature_unavailable_session_count']}"
                ),
                (
                    "- feature_summaries: "
                    f"`{json.dumps(run['feature_summaries'], sort_keys=True)}`"
                ),
                (
                    "- session_snapshots: "
                    f"`{json.dumps(run['session_snapshots'], sort_keys=True)}`"
                ),
                "",
            ]
        )
    return "\n".join(lines)


def _sanitize_path_token(value: str) -> str:
    return "".join(char if (char.isalnum() or char in ("-", "_", ".")) else "_" for char in value)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    run_ids = sorted(set(args.run_id))
    runs_dir = Path(args.runs_dir).resolve()
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir is not None
        else runs_dir / "market_state_reports"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    runs = [_aggregate_run(run_id=run_id, runs_dir=runs_dir) for run_id in run_ids]
    payload = {
        "report_kind": "forward_paper_market_state_aggregate_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_count": len(runs),
        "runs": runs,
    }

    base_name = "__".join(_sanitize_path_token(run_id) for run_id in run_ids)
    json_path = output_dir / f"{base_name}.market_state_aggregate.json"
    markdown_path = output_dir / f"{base_name}.market_state_aggregate.md"

    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "report_kind": payload["report_kind"],
                "run_ids": run_ids,
                "json_path": str(json_path),
                "report_path": str(markdown_path),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
