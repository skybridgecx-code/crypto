from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SESSION_PROPOSAL_SUMMARY_RE = re.compile(
    r"^session-([0-9]{4})\.proposal_generation_summary\.json$"
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate forward-paper proposal-generation summaries across one or more runtime IDs."
        )
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
            "(default: <runs_dir>/proposal_generation_reports)."
        ),
    )
    return parser


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"forward_paper_proposal_generation_missing_artifact:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"forward_paper_proposal_generation_invalid_json:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"forward_paper_proposal_generation_invalid_object:{path}")
    return payload


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


def _safe_float(value: object) -> float | None:
    if value is None:
        return None
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


def _safe_string(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return str(value)


def _counter_to_sorted_dict(counter: Counter[str]) -> dict[str, int]:
    return {key: int(counter[key]) for key in sorted(counter)}


class _NumericSummaryAccumulator:
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


def _merge_count_map(counter: Counter[str], payload: object) -> None:
    if not isinstance(payload, dict):
        return
    for key, value in payload.items():
        counter.update({str(key): _safe_non_negative_int(value)})


def _extract_strategy_payload(
    *,
    strategy_key: str,
    strategy_payload: object,
    session_id: str,
) -> dict[str, Any]:
    if not isinstance(strategy_payload, dict):
        raise ValueError(
            "forward_paper_proposal_generation_invalid_strategy_payload:"
            f"{strategy_key}:{session_id}"
        )
    return {
        "strategy_id": _safe_string(strategy_payload.get("strategy_id")) or strategy_key,
        "considered_window_count": _safe_non_negative_int(
            strategy_payload.get("considered_window_count")
        ),
        "insufficient_lookback_count": _safe_non_negative_int(
            strategy_payload.get("insufficient_lookback_count")
        ),
        "emitted_proposal_count": _safe_non_negative_int(
            strategy_payload.get("emitted_proposal_count")
        ),
        "emitted_side_counts": strategy_payload.get("emitted_side_counts"),
        "non_emit_reason_counts": strategy_payload.get("non_emit_reason_counts"),
        "last_outcome_status": _safe_string(strategy_payload.get("last_outcome_status")),
        "last_outcome_reason": _safe_string(strategy_payload.get("last_outcome_reason")),
        "strategy_config_source": _safe_string(strategy_payload.get("strategy_config_source"))
        or "default",
        "strategy_config": strategy_payload.get("strategy_config"),
        "threshold_visibility": strategy_payload.get("threshold_visibility"),
    }


def _extract_pipeline_payload(*, pipeline_payload: object, session_id: str) -> dict[str, Any]:
    if not isinstance(pipeline_payload, dict):
        raise ValueError(
            "forward_paper_proposal_generation_invalid_pipeline_payload:" f"{session_id}"
        )
    return {
        "emitted_proposal_count": _safe_non_negative_int(
            pipeline_payload.get("emitted_proposal_count")
        ),
        "dropped_by_external_confirmation_count": _safe_non_negative_int(
            pipeline_payload.get("dropped_by_external_confirmation_count")
        ),
        "blocked_by_risk_or_policy_count": _safe_non_negative_int(
            pipeline_payload.get("blocked_by_risk_or_policy_count")
        ),
        "blocked_reason_counts": pipeline_payload.get("blocked_reason_counts"),
        "allowed_for_execution_count": _safe_non_negative_int(
            pipeline_payload.get("allowed_for_execution_count")
        ),
    }


def _aggregate_strategy_threshold_visibility(
    session_entries: list[dict[str, Any]],
) -> dict[str, Any]:
    threshold_values: dict[str, set[float]] = {}
    observed_accumulators: dict[str, _NumericSummaryAccumulator] = {}
    gap_accumulators: dict[str, _NumericSummaryAccumulator] = {}
    session_snapshots: list[dict[str, Any]] = []

    for entry in session_entries:
        session_id = _safe_string(entry.get("session_id")) or "unknown"
        threshold_visibility = entry.get("threshold_visibility")
        if not isinstance(threshold_visibility, dict):
            continue
        session_snapshots.append(
            {
                "session_id": session_id,
                "threshold_visibility": threshold_visibility,
            }
        )
        for key, value in threshold_visibility.items():
            numeric_value = _safe_float(value)
            if numeric_value is None:
                continue
            if key.endswith("_threshold_used"):
                threshold_values.setdefault(key, set()).add(numeric_value)
            elif key.startswith("observed_") and key.endswith("_last"):
                accumulator = observed_accumulators.setdefault(key, _NumericSummaryAccumulator())
                accumulator.add(numeric_value)
            elif key.startswith("gap_to_") and key.endswith("_last"):
                accumulator = gap_accumulators.setdefault(key, _NumericSummaryAccumulator())
                accumulator.add(numeric_value)

    return {
        "threshold_values_used": {
            key: sorted(values) for key, values in sorted(threshold_values.items())
        },
        "observed_last_value_summaries": {
            key: summary
            for key, summary in (
                (name, accumulator.to_summary())
                for name, accumulator in sorted(observed_accumulators.items())
            )
            if summary is not None
        },
        "gap_last_value_summaries": {
            key: summary
            for key, summary in (
                (name, accumulator.to_summary())
                for name, accumulator in sorted(gap_accumulators.items())
            )
            if summary is not None
        },
        "session_threshold_snapshots": session_snapshots,
    }


def _load_run_session_summaries(run_dir: Path) -> list[tuple[int, str, dict[str, Any]]]:
    sessions_dir = run_dir / "sessions"
    if not sessions_dir.is_dir():
        raise ValueError(f"forward_paper_proposal_generation_missing_sessions_dir:{sessions_dir}")

    summary_paths: list[tuple[int, str, Path]] = []
    for path in sorted(sessions_dir.iterdir()):
        if not path.is_file():
            continue
        match = _SESSION_PROPOSAL_SUMMARY_RE.match(path.name)
        if match is None:
            continue
        session_number = int(match.group(1))
        session_id = f"session-{session_number:04d}"
        summary_paths.append((session_number, session_id, path))

    records: list[tuple[int, str, dict[str, Any]]] = []
    for session_number, session_id, path in sorted(summary_paths, key=lambda item: item[0]):
        payload = _read_json_object(path)
        if payload.get("artifact_kind") != "forward_paper_proposal_generation_summary_v1":
            raise ValueError(
                "forward_paper_proposal_generation_invalid_artifact_kind:"
                f"{path}:{payload.get('artifact_kind')}"
            )
        proposal_generation_payload = payload.get("proposal_generation")
        if not isinstance(proposal_generation_payload, dict):
            raise ValueError(
                "forward_paper_proposal_generation_invalid_proposal_generation_payload:" f"{path}"
            )
        if proposal_generation_payload.get("artifact_kind") != "proposal_generation_summary_v1":
            raise ValueError(
                "forward_paper_proposal_generation_invalid_inner_artifact_kind:"
                f"{path}:{proposal_generation_payload.get('artifact_kind')}"
            )
        records.append((session_number, session_id, proposal_generation_payload))
    return records


def _aggregate_run(*, run_id: str, runs_dir: Path) -> dict[str, Any]:
    run_dir = runs_dir / run_id
    if not run_dir.is_dir():
        raise ValueError(f"forward_paper_proposal_generation_missing_run_dir:{run_dir}")

    session_records = _load_run_session_summaries(run_dir)

    strategy_aggregates: dict[str, dict[str, Any]] = {
        "breakout": {
            "strategy_id": None,
            "total_considered_window_count": 0,
            "total_insufficient_lookback_count": 0,
            "total_emitted_proposal_count": 0,
            "emitted_side_counts": Counter(),
            "non_emit_reason_counts": Counter(),
            "strategy_config_source_counts": Counter(),
            "strategy_configs_used": set(),
            "session_last_outcomes": [],
            "session_threshold_visibility": [],
        },
        "mean_reversion": {
            "strategy_id": None,
            "total_considered_window_count": 0,
            "total_insufficient_lookback_count": 0,
            "total_emitted_proposal_count": 0,
            "emitted_side_counts": Counter(),
            "non_emit_reason_counts": Counter(),
            "strategy_config_source_counts": Counter(),
            "strategy_configs_used": set(),
            "session_last_outcomes": [],
            "session_threshold_visibility": [],
        },
    }

    pipeline_totals = {
        "emitted_proposal_count": 0,
        "dropped_by_external_confirmation_count": 0,
        "blocked_by_risk_or_policy_count": 0,
        "allowed_for_execution_count": 0,
    }
    pipeline_blocked_reason_counts: Counter[str] = Counter()

    for _, session_id, proposal_payload in session_records:
        for strategy_key in ("breakout", "mean_reversion"):
            strategy_payload = _extract_strategy_payload(
                strategy_key=strategy_key,
                strategy_payload=proposal_payload.get(strategy_key),
                session_id=session_id,
            )
            aggregate = strategy_aggregates[strategy_key]
            if aggregate["strategy_id"] is None:
                aggregate["strategy_id"] = strategy_payload["strategy_id"]
            aggregate["total_considered_window_count"] += strategy_payload[
                "considered_window_count"
            ]
            aggregate["total_insufficient_lookback_count"] += strategy_payload[
                "insufficient_lookback_count"
            ]
            aggregate["total_emitted_proposal_count"] += strategy_payload["emitted_proposal_count"]
            _merge_count_map(
                aggregate["emitted_side_counts"], strategy_payload["emitted_side_counts"]
            )
            _merge_count_map(
                aggregate["non_emit_reason_counts"], strategy_payload["non_emit_reason_counts"]
            )
            aggregate["strategy_config_source_counts"].update(
                [strategy_payload["strategy_config_source"]]
            )
            if isinstance(strategy_payload["strategy_config"], dict):
                aggregate["strategy_configs_used"].add(
                    json.dumps(strategy_payload["strategy_config"], sort_keys=True)
                )
            aggregate["session_last_outcomes"].append(
                {
                    "session_id": session_id,
                    "last_outcome_status": strategy_payload["last_outcome_status"],
                    "last_outcome_reason": strategy_payload["last_outcome_reason"],
                }
            )
            aggregate["session_threshold_visibility"].append(
                {
                    "session_id": session_id,
                    "threshold_visibility": strategy_payload["threshold_visibility"],
                }
            )

        pipeline_payload = _extract_pipeline_payload(
            pipeline_payload=proposal_payload.get("proposal_pipeline"),
            session_id=session_id,
        )
        pipeline_totals["emitted_proposal_count"] += pipeline_payload["emitted_proposal_count"]
        pipeline_totals["dropped_by_external_confirmation_count"] += pipeline_payload[
            "dropped_by_external_confirmation_count"
        ]
        pipeline_totals["blocked_by_risk_or_policy_count"] += pipeline_payload[
            "blocked_by_risk_or_policy_count"
        ]
        pipeline_totals["allowed_for_execution_count"] += pipeline_payload[
            "allowed_for_execution_count"
        ]
        _merge_count_map(pipeline_blocked_reason_counts, pipeline_payload["blocked_reason_counts"])

    breakout_aggregate = strategy_aggregates["breakout"]
    mean_reversion_aggregate = strategy_aggregates["mean_reversion"]

    return {
        "run_id": run_id,
        "session_count": len(session_records),
        "strategy_aggregates": {
            "breakout": {
                "strategy_id": breakout_aggregate["strategy_id"] or "breakout_v1",
                "total_considered_window_count": breakout_aggregate[
                    "total_considered_window_count"
                ],
                "total_insufficient_lookback_count": breakout_aggregate[
                    "total_insufficient_lookback_count"
                ],
                "total_emitted_proposal_count": breakout_aggregate["total_emitted_proposal_count"],
                "emitted_side_counts": _counter_to_sorted_dict(
                    breakout_aggregate["emitted_side_counts"]
                ),
                "non_emit_reason_counts": _counter_to_sorted_dict(
                    breakout_aggregate["non_emit_reason_counts"]
                ),
                "strategy_config_source_counts": _counter_to_sorted_dict(
                    breakout_aggregate["strategy_config_source_counts"]
                ),
                "strategy_configs_used": [
                    json.loads(item) for item in sorted(breakout_aggregate["strategy_configs_used"])
                ],
                "session_last_outcomes": breakout_aggregate["session_last_outcomes"],
                "threshold_visibility": _aggregate_strategy_threshold_visibility(
                    breakout_aggregate["session_threshold_visibility"]
                ),
            },
            "mean_reversion": {
                "strategy_id": mean_reversion_aggregate["strategy_id"] or "mean_reversion_v1",
                "total_considered_window_count": mean_reversion_aggregate[
                    "total_considered_window_count"
                ],
                "total_insufficient_lookback_count": mean_reversion_aggregate[
                    "total_insufficient_lookback_count"
                ],
                "total_emitted_proposal_count": mean_reversion_aggregate[
                    "total_emitted_proposal_count"
                ],
                "emitted_side_counts": _counter_to_sorted_dict(
                    mean_reversion_aggregate["emitted_side_counts"]
                ),
                "non_emit_reason_counts": _counter_to_sorted_dict(
                    mean_reversion_aggregate["non_emit_reason_counts"]
                ),
                "strategy_config_source_counts": _counter_to_sorted_dict(
                    mean_reversion_aggregate["strategy_config_source_counts"]
                ),
                "strategy_configs_used": [
                    json.loads(item)
                    for item in sorted(mean_reversion_aggregate["strategy_configs_used"])
                ],
                "session_last_outcomes": mean_reversion_aggregate["session_last_outcomes"],
                "threshold_visibility": _aggregate_strategy_threshold_visibility(
                    mean_reversion_aggregate["session_threshold_visibility"]
                ),
            },
        },
        "pipeline_aggregate": {
            "emitted_proposal_count": pipeline_totals["emitted_proposal_count"],
            "dropped_by_external_confirmation_count": pipeline_totals[
                "dropped_by_external_confirmation_count"
            ],
            "blocked_by_risk_or_policy_count": pipeline_totals["blocked_by_risk_or_policy_count"],
            "blocked_reason_counts": _counter_to_sorted_dict(pipeline_blocked_reason_counts),
            "allowed_for_execution_count": pipeline_totals["allowed_for_execution_count"],
        },
    }


def _fmt_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}:{value}" for key, value in sorted(counts.items()))


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Forward-Paper Proposal-Generation Aggregate Report",
        f"- run_count: {payload['run_count']}",
        "",
    ]

    for run in payload["runs"]:
        breakout = run["strategy_aggregates"]["breakout"]
        mean_reversion = run["strategy_aggregates"]["mean_reversion"]
        pipeline = run["pipeline_aggregate"]
        lines.extend(
            [
                f"## {run['run_id']}",
                f"- session_count: {run['session_count']}",
                "",
                "### Breakout",
                f"- strategy_id: `{breakout['strategy_id']}`",
                f"- total_considered_window_count: {breakout['total_considered_window_count']}",
                (
                    "- total_insufficient_lookback_count: "
                    f"{breakout['total_insufficient_lookback_count']}"
                ),
                f"- total_emitted_proposal_count: {breakout['total_emitted_proposal_count']}",
                f"- emitted_side_counts: `{_fmt_counts(breakout['emitted_side_counts'])}`",
                f"- non_emit_reason_counts: `{_fmt_counts(breakout['non_emit_reason_counts'])}`",
                (
                    "- strategy_config_source_counts: "
                    f"`{_fmt_counts(breakout['strategy_config_source_counts'])}`"
                ),
                (
                    "- strategy_configs_used: "
                    f"`{json.dumps(breakout['strategy_configs_used'], sort_keys=True)}`"
                ),
                (
                    "- session_last_outcomes: "
                    f"`{json.dumps(breakout['session_last_outcomes'], sort_keys=True)}`"
                ),
                (
                    "- threshold_visibility: "
                    f"`{json.dumps(breakout['threshold_visibility'], sort_keys=True)}`"
                ),
                "",
                "### Mean Reversion",
                f"- strategy_id: `{mean_reversion['strategy_id']}`",
                (
                    "- total_considered_window_count: "
                    f"{mean_reversion['total_considered_window_count']}"
                ),
                (
                    "- total_insufficient_lookback_count: "
                    f"{mean_reversion['total_insufficient_lookback_count']}"
                ),
                (
                    "- total_emitted_proposal_count: "
                    f"{mean_reversion['total_emitted_proposal_count']}"
                ),
                (
                    "- emitted_side_counts: "
                    f"`{_fmt_counts(mean_reversion['emitted_side_counts'])}`"
                ),
                (
                    "- non_emit_reason_counts: "
                    f"`{_fmt_counts(mean_reversion['non_emit_reason_counts'])}`"
                ),
                (
                    "- strategy_config_source_counts: "
                    f"`{_fmt_counts(mean_reversion['strategy_config_source_counts'])}`"
                ),
                (
                    "- strategy_configs_used: "
                    f"`{json.dumps(mean_reversion['strategy_configs_used'], sort_keys=True)}`"
                ),
                (
                    "- session_last_outcomes: "
                    f"`{json.dumps(mean_reversion['session_last_outcomes'], sort_keys=True)}`"
                ),
                (
                    "- threshold_visibility: "
                    f"`{json.dumps(mean_reversion['threshold_visibility'], sort_keys=True)}`"
                ),
                "",
                "### Pipeline",
                f"- emitted_proposal_count: {pipeline['emitted_proposal_count']}",
                (
                    "- dropped_by_external_confirmation_count: "
                    f"{pipeline['dropped_by_external_confirmation_count']}"
                ),
                (
                    "- blocked_by_risk_or_policy_count: "
                    f"{pipeline['blocked_by_risk_or_policy_count']}"
                ),
                f"- blocked_reason_counts: `{_fmt_counts(pipeline['blocked_reason_counts'])}`",
                f"- allowed_for_execution_count: {pipeline['allowed_for_execution_count']}",
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
        else runs_dir / "proposal_generation_reports"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    reports = [_aggregate_run(run_id=run_id, runs_dir=runs_dir) for run_id in run_ids]
    payload = {
        "report_kind": "forward_paper_proposal_generation_aggregate_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "run_count": len(reports),
        "runs": reports,
    }

    base_name = "__".join(_sanitize_path_token(run_id) for run_id in run_ids)
    json_path = output_dir / f"{base_name}.proposal_generation_aggregate.json"
    markdown_path = output_dir / f"{base_name}.proposal_generation_aggregate.md"

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
