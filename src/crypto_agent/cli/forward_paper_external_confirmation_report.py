from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_CANONICAL_SESSION_FILENAME_RE = re.compile(r"^session-([0-9]{4})\.json$")
_TRACKED_DECISION_STATUSES = (
    "boosted_confirmation",
    "penalized_conflict",
    "ignored_asset_mismatch",
    "vetoed_conflict",
    "vetoed_neutral",
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Summarize external confirmation / Polymarket bridge impact for one "
            "forward-paper runtime ID."
        )
    )
    parser.add_argument("--run-id", required=True, help="Forward-paper runtime ID to report.")
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument("--journals-dir", default="journals")
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Output directory for external confirmation impact artifacts "
            "(default: <runs_dir>/external_confirmation_reports)."
        ),
    )
    return parser


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"forward_paper_external_confirmation_missing_artifact:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"forward_paper_external_confirmation_invalid_json:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"forward_paper_external_confirmation_invalid_object:{path}")
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


def _decision_counts_with_tracked_zeros(counter: Counter[str]) -> dict[str, int]:
    merged = Counter({status: 0 for status in _TRACKED_DECISION_STATUSES})
    merged.update(counter)
    return _counter_to_sorted_dict(merged)


def _merge_count_map(counter: Counter[str], payload: object) -> None:
    if not isinstance(payload, dict):
        return
    for key, value in payload.items():
        counter.update({str(key): _safe_non_negative_int(value)})


def _resolve_path(
    value: object,
    *,
    runs_dir: Path,
    journals_dir: Path,
) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    candidates = [
        Path.cwd() / path,
        runs_dir.parent / path,
        journals_dir.parent / path,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _scorecard_counts(
    summary_payload: dict[str, Any],
    session_payload: dict[str, Any],
) -> dict[str, int]:
    scorecard_payload = summary_payload.get("scorecard")
    if not isinstance(scorecard_payload, dict):
        scorecard_payload = session_payload.get("scorecard")
    if not isinstance(scorecard_payload, dict):
        scorecard_payload = {}

    operator_summary = summary_payload.get("operator_summary")
    if not isinstance(operator_summary, dict):
        operator_summary = session_payload.get("operator_summary")
    if not isinstance(operator_summary, dict):
        operator_summary = {}

    return {
        "proposal_count": _safe_non_negative_int(
            scorecard_payload.get("proposal_count", operator_summary.get("proposal_count"))
        ),
        "orders_submitted_count": _safe_non_negative_int(
            scorecard_payload.get(
                "orders_submitted_count", operator_summary.get("orders_submitted_count")
            )
        ),
        "fill_event_count": _safe_non_negative_int(
            scorecard_payload.get("fill_event_count", operator_summary.get("fill_event_count"))
        ),
    }


def _proposal_pipeline_payload(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    payload = _read_json_object(path)
    proposal_generation = payload.get("proposal_generation")
    if not isinstance(proposal_generation, dict):
        return {}
    pipeline = proposal_generation.get("proposal_pipeline")
    return pipeline if isinstance(pipeline, dict) else {}


def _journal_decision_status_counts(path: Path | None) -> dict[str, int]:
    if path is None or not path.is_file():
        return _decision_counts_with_tracked_zeros(Counter())

    counter: Counter[str] = Counter()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"forward_paper_external_confirmation_invalid_journal_json:{path}:{line_number}"
            ) from exc
        if not isinstance(event, dict):
            continue
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        if payload.get("decision_kind") != "external_confirmation_decision_v1":
            continue
        status = _safe_string(payload.get("status"))
        if status is not None:
            counter.update([status])
    return _decision_counts_with_tracked_zeros(counter)


def _sum_optional_float(current: float | None, value: object) -> float | None:
    numeric_value = _safe_float(value)
    if numeric_value is None:
        return current
    return (current or 0.0) + numeric_value


def _journal_execution_evidence(path: Path | None) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "approved_notional_usd": None,
        "approved_quantity": None,
        "submitted_quantity": None,
        "submitted_order_notional_usd": None,
        "total_fill_notional_usd": None,
        "cap_or_block_reasons": [],
    }
    if path is None or not path.is_file():
        return evidence

    proposal_entry_reference_by_id: dict[str, float] = {}
    cap_or_block_reasons: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"forward_paper_external_confirmation_invalid_journal_json:{path}:{line_number}"
            ) from exc
        if not isinstance(event, dict):
            continue
        event_type = _safe_string(event.get("event_type"))
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue

        if event_type == "trade.proposal.created":
            proposal_id = _safe_string(payload.get("proposal_id"))
            entry_reference = _safe_float(payload.get("entry_reference"))
            if proposal_id is not None and entry_reference is not None:
                proposal_entry_reference_by_id[proposal_id] = entry_reference
            continue

        if event_type == "risk.check.completed":
            sizing = payload.get("sizing")
            if isinstance(sizing, dict):
                evidence["approved_notional_usd"] = _safe_float(sizing.get("approved_notional_usd"))
                evidence["approved_quantity"] = _safe_float(sizing.get("quantity"))
            for reason in payload.get("rejection_reasons", []):
                reason_value = _safe_string(reason)
                if reason_value is not None:
                    cap_or_block_reasons.add(reason_value)
            decision = payload.get("decision")
            if isinstance(decision, dict):
                for reason in decision.get("reason_codes", []):
                    reason_value = _safe_string(reason)
                    if reason_value is not None and reason_value != "within_limits":
                        cap_or_block_reasons.add(reason_value)
            continue

        if event_type == "policy.decision.made":
            for reason in payload.get("reason_codes", []):
                reason_value = _safe_string(reason)
                if reason_value is not None and reason_value != "within_limits":
                    cap_or_block_reasons.add(reason_value)
            continue

        if event_type == "order.submitted":
            intent = payload.get("intent")
            if isinstance(intent, dict):
                submitted_quantity = _safe_float(intent.get("quantity"))
                evidence["submitted_quantity"] = submitted_quantity
                proposal_id = _safe_string(intent.get("proposal_id"))
                if (
                    proposal_id is not None
                    and submitted_quantity is not None
                    and proposal_id in proposal_entry_reference_by_id
                ):
                    evidence["submitted_order_notional_usd"] = (
                        submitted_quantity * proposal_entry_reference_by_id[proposal_id]
                    )
            continue

        if event_type == "order.rejected":
            reason_value = _safe_string(payload.get("reject_reason"))
            if reason_value is not None:
                cap_or_block_reasons.add(reason_value)
            continue

        if event_type == "order.filled":
            evidence["total_fill_notional_usd"] = _sum_optional_float(
                _safe_float(evidence["total_fill_notional_usd"]),
                payload.get("notional_usd"),
            )

    evidence["cap_or_block_reasons"] = sorted(cap_or_block_reasons)
    return evidence


def _load_session_records(
    *,
    run_id: str,
    runs_dir: Path,
    journals_dir: Path,
) -> list[dict[str, Any]]:
    run_dir = runs_dir / run_id
    if not run_dir.is_dir():
        raise ValueError(f"forward_paper_external_confirmation_missing_run_dir:{run_dir}")

    sessions_dir = run_dir / "sessions"
    if not sessions_dir.is_dir():
        raise ValueError(f"forward_paper_external_confirmation_missing_sessions_dir:{sessions_dir}")

    session_paths: list[tuple[int, Path]] = []
    for path in sorted(sessions_dir.iterdir()):
        if not path.is_file():
            continue
        match = _CANONICAL_SESSION_FILENAME_RE.match(path.name)
        if match is None:
            continue
        session_paths.append((int(match.group(1)), path))

    records: list[dict[str, Any]] = []
    for session_number_from_path, path in sorted(session_paths, key=lambda item: item[0]):
        session_payload = _read_json_object(path)
        session_number = _safe_non_negative_int(
            session_payload.get("session_number", session_number_from_path)
        )
        session_id = (
            _safe_string(session_payload.get("session_id")) or f"session-{session_number:04d}"
        )

        summary_path = _resolve_path(
            session_payload.get("summary_path"),
            runs_dir=runs_dir,
            journals_dir=journals_dir,
        )
        if summary_path is None:
            fallback = runs_dir / f"{run_id}-{session_id}" / "summary.json"
            summary_path = fallback if fallback.exists() else None
        summary_payload = _read_json_object(summary_path) if summary_path is not None else {}

        proposal_generation_path = sessions_dir / f"{session_id}.proposal_generation_summary.json"
        if not proposal_generation_path.is_file():
            proposal_generation_path = (
                runs_dir / f"{run_id}-{session_id}" / ("proposal_generation_summary.json")
            )
        pipeline_payload = _proposal_pipeline_payload(proposal_generation_path)

        journal_path = _resolve_path(
            session_payload.get("journal_path"),
            runs_dir=runs_dir,
            journals_dir=journals_dir,
        )
        if journal_path is None:
            fallback = journals_dir / f"{run_id}-{session_id}.jsonl"
            journal_path = fallback if fallback.exists() else None

        external_payload = summary_payload.get("external_confirmation")
        if not isinstance(external_payload, dict):
            external_payload = {}
        status_counts: Counter[str] = Counter()
        _merge_count_map(status_counts, external_payload.get("decision_status_counts"))
        scorecard_counts = _scorecard_counts(summary_payload, session_payload)

        records.append(
            {
                "session_id": session_id,
                "session_number": session_number,
                "run_id": _safe_string(session_payload.get("run_id")),
                "session_summary_path": str(path),
                "summary_path": str(summary_path) if summary_path is not None else None,
                "proposal_generation_summary_path": (
                    str(proposal_generation_path) if proposal_generation_path.is_file() else None
                ),
                "journal_path": str(journal_path) if journal_path is not None else None,
                "artifact_loaded": external_payload.get("artifact_loaded"),
                "source_system": _safe_string(external_payload.get("source_system")),
                "asset": _safe_string(external_payload.get("asset")),
                "decision_count": _safe_non_negative_int(external_payload.get("decision_count")),
                "decision_status_counts": _decision_counts_with_tracked_zeros(status_counts),
                "journal_decision_status_counts": _journal_decision_status_counts(journal_path),
                "external_confirmation_impact_policy": _safe_string(
                    external_payload.get(
                        "impact_policy",
                        pipeline_payload.get("external_confirmation_impact_policy"),
                    )
                ),
                "external_confirmation_boosted_size_multiplier": _safe_float(
                    external_payload.get(
                        "boosted_size_multiplier",
                        pipeline_payload.get("external_confirmation_boosted_size_multiplier"),
                    )
                ),
                "dropped_by_external_confirmation_count": _safe_non_negative_int(
                    pipeline_payload.get("dropped_by_external_confirmation_count")
                ),
                "sizing_evidence": _journal_execution_evidence(journal_path),
                **scorecard_counts,
            }
        )
    return records


def _artifact_loaded_status(counts: dict[str, int]) -> str:
    loaded = counts.get("loaded", 0)
    not_loaded = counts.get("not_loaded", 0)
    missing = counts.get("missing", 0)
    total = loaded + not_loaded + missing
    if total == 0 or missing == total:
        return "absent"
    if loaded == total:
        return "loaded_all_sessions"
    if loaded > 0 and (not_loaded > 0 or missing > 0):
        return "mixed"
    return "not_loaded"


def _aggregate_run(*, run_id: str, runs_dir: Path, journals_dir: Path) -> dict[str, Any]:
    records = _load_session_records(run_id=run_id, runs_dir=runs_dir, journals_dir=journals_dir)
    artifact_loaded_counts: Counter[str] = Counter()
    source_system_counts: Counter[str] = Counter()
    asset_counts: Counter[str] = Counter()
    impact_policy_counts: Counter[str] = Counter()
    boosted_size_multiplier_counts: Counter[str] = Counter()
    decision_status_counts: Counter[str] = Counter()
    journal_decision_status_counts: Counter[str] = Counter()
    cap_or_block_reason_counts: Counter[str] = Counter()

    dropped_total = 0
    proposal_total = 0
    orders_submitted_total = 0
    fill_event_total = 0
    approved_notional_total = 0.0
    approved_notional_count = 0
    submitted_order_notional_total = 0.0
    submitted_order_notional_count = 0
    total_fill_notional = 0.0

    for record in records:
        loaded_value = record["artifact_loaded"]
        loaded_key = (
            "loaded"
            if loaded_value is True
            else "not_loaded"
            if loaded_value is False
            else "missing"
        )
        artifact_loaded_counts.update([loaded_key])
        if record["source_system"] is not None:
            source_system_counts.update([record["source_system"]])
        if record["asset"] is not None:
            asset_counts.update([record["asset"]])
        if record["external_confirmation_impact_policy"] is not None:
            impact_policy_counts.update([record["external_confirmation_impact_policy"]])
        if record["external_confirmation_boosted_size_multiplier"] is not None:
            boosted_size_multiplier_counts.update(
                [str(record["external_confirmation_boosted_size_multiplier"])]
            )
        _merge_count_map(decision_status_counts, record["decision_status_counts"])
        _merge_count_map(journal_decision_status_counts, record["journal_decision_status_counts"])
        sizing_evidence = record["sizing_evidence"]
        if isinstance(sizing_evidence, dict):
            approved_notional = _safe_float(sizing_evidence.get("approved_notional_usd"))
            if approved_notional is not None:
                approved_notional_total += approved_notional
                approved_notional_count += 1
            submitted_order_notional = _safe_float(
                sizing_evidence.get("submitted_order_notional_usd")
            )
            if submitted_order_notional is not None:
                submitted_order_notional_total += submitted_order_notional
                submitted_order_notional_count += 1
            fill_notional = _safe_float(sizing_evidence.get("total_fill_notional_usd"))
            if fill_notional is not None:
                total_fill_notional += fill_notional
            for reason in sizing_evidence.get("cap_or_block_reasons", []):
                reason_value = _safe_string(reason)
                if reason_value is not None:
                    cap_or_block_reason_counts.update([reason_value])
        dropped_total += record["dropped_by_external_confirmation_count"]
        proposal_total += record["proposal_count"]
        orders_submitted_total += record["orders_submitted_count"]
        fill_event_total += record["fill_event_count"]

    loaded_counts = _counter_to_sorted_dict(artifact_loaded_counts)
    return {
        "run_id": run_id,
        "session_count": len(records),
        "artifact_loaded_status": _artifact_loaded_status(loaded_counts),
        "artifact_loaded_counts": loaded_counts,
        "source_system_counts": _counter_to_sorted_dict(source_system_counts),
        "asset_counts": _counter_to_sorted_dict(asset_counts),
        "external_confirmation_impact_policy_counts": _counter_to_sorted_dict(impact_policy_counts),
        "external_confirmation_boosted_size_multiplier_counts": _counter_to_sorted_dict(
            boosted_size_multiplier_counts
        ),
        "decision_status_counts": _decision_counts_with_tracked_zeros(decision_status_counts),
        "journal_decision_status_counts": _decision_counts_with_tracked_zeros(
            journal_decision_status_counts
        ),
        "totals": {
            "dropped_by_external_confirmation_count": dropped_total,
            "proposal_count": proposal_total,
            "orders_submitted_count": orders_submitted_total,
            "fill_event_count": fill_event_total,
            "approved_notional_usd": approved_notional_total
            if approved_notional_count > 0
            else None,
            "submitted_order_notional_usd": submitted_order_notional_total
            if submitted_order_notional_count > 0
            else None,
            "total_fill_notional_usd": total_fill_notional if total_fill_notional > 0 else None,
            "cap_or_block_reason_counts": _counter_to_sorted_dict(cap_or_block_reason_counts),
        },
        "sessions": records,
    }


def _format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}:{value}" for key, value in sorted(counts.items()))


def _render_markdown(payload: dict[str, Any]) -> str:
    run = payload["run"]
    lines = [
        "# Forward-Paper External Confirmation Impact Report",
        f"- run_id: `{run['run_id']}`",
        f"- session_count: {run['session_count']}",
        f"- artifact_loaded_status: `{run['artifact_loaded_status']}`",
        f"- artifact_loaded_counts: `{_format_counts(run['artifact_loaded_counts'])}`",
        f"- source_system_counts: `{_format_counts(run['source_system_counts'])}`",
        f"- asset_counts: `{_format_counts(run['asset_counts'])}`",
        (
            "- external_confirmation_impact_policy_counts: "
            f"`{_format_counts(run['external_confirmation_impact_policy_counts'])}`"
        ),
        (
            "- external_confirmation_boosted_size_multiplier_counts: "
            f"`{_format_counts(run['external_confirmation_boosted_size_multiplier_counts'])}`"
        ),
        f"- decision_status_counts: `{_format_counts(run['decision_status_counts'])}`",
        (
            "- journal_decision_status_counts: "
            f"`{_format_counts(run['journal_decision_status_counts'])}`"
        ),
        (
            "- dropped_by_external_confirmation_count: "
            f"{run['totals']['dropped_by_external_confirmation_count']}"
        ),
        f"- proposal_count: {run['totals']['proposal_count']}",
        f"- orders_submitted_count: {run['totals']['orders_submitted_count']}",
        f"- fill_event_count: {run['totals']['fill_event_count']}",
        f"- approved_notional_usd: {run['totals']['approved_notional_usd']}",
        f"- submitted_order_notional_usd: {run['totals']['submitted_order_notional_usd']}",
        f"- total_fill_notional_usd: {run['totals']['total_fill_notional_usd']}",
        (
            "- cap_or_block_reason_counts: "
            f"`{_format_counts(run['totals']['cap_or_block_reason_counts'])}`"
        ),
        "",
        "## Sessions",
    ]
    for session in run["sessions"]:
        lines.extend(
            [
                f"### {session['session_id']}",
                f"- artifact_loaded: `{session['artifact_loaded']}`",
                f"- source_system: `{session['source_system']}`",
                f"- asset: `{session['asset']}`",
                f"- impact_policy: `{session['external_confirmation_impact_policy']}`",
                (
                    "- boosted_size_multiplier: "
                    f"`{session['external_confirmation_boosted_size_multiplier']}`"
                ),
                f"- decision_count: {session['decision_count']}",
                (
                    "- decision_status_counts: "
                    f"`{_format_counts(session['decision_status_counts'])}`"
                ),
                (
                    "- journal_decision_status_counts: "
                    f"`{_format_counts(session['journal_decision_status_counts'])}`"
                ),
                (
                    "- dropped_by_external_confirmation_count: "
                    f"{session['dropped_by_external_confirmation_count']}"
                ),
                f"- proposal_count: {session['proposal_count']}",
                f"- orders_submitted_count: {session['orders_submitted_count']}",
                f"- fill_event_count: {session['fill_event_count']}",
                f"- sizing_evidence: `{json.dumps(session['sizing_evidence'], sort_keys=True)}`",
                "",
            ]
        )
    return "\n".join(lines)


def _sanitize_path_token(value: str) -> str:
    return "".join(char if (char.isalnum() or char in ("-", "_", ".")) else "_" for char in value)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    runs_dir = Path(args.runs_dir).resolve()
    journals_dir = Path(args.journals_dir).resolve()
    output_dir = (
        Path(args.output_dir).resolve()
        if args.output_dir is not None
        else runs_dir / "external_confirmation_reports"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    run = _aggregate_run(run_id=args.run_id, runs_dir=runs_dir, journals_dir=journals_dir)
    payload = {
        "report_kind": "forward_paper_external_confirmation_impact_report_v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "runs_dir": str(runs_dir),
        "journals_dir": str(journals_dir),
        "run": run,
    }

    base_name = _sanitize_path_token(args.run_id)
    json_path = output_dir / f"{base_name}.external_confirmation_impact.json"
    markdown_path = output_dir / f"{base_name}.external_confirmation_impact.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")

    print(
        json.dumps(
            {
                "report_kind": payload["report_kind"],
                "run_id": args.run_id,
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
