from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from crypto_agent.runtime.models import ForwardPaperSessionSummary

_CANONICAL_SESSION_FILENAME_RE = re.compile(r"^session-([0-9]{4})\.json$")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compare two forward-paper runtime IDs (advisory vs control) "
            "from existing local artifacts."
        )
    )
    parser.add_argument("--advisory-run-id", required=True)
    parser.add_argument("--control-run-id", required=True)
    parser.add_argument("--runs-dir", default="runs")
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Directory for comparison outputs (default: <runs_dir>/comparisons).",
    )
    return parser


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise ValueError(f"forward_paper_compare_missing_artifact:{path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"forward_paper_compare_invalid_json:{path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"forward_paper_compare_invalid_object:{path}")
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


def _load_session_summaries(run_dir: Path) -> list[ForwardPaperSessionSummary]:
    sessions_dir = run_dir / "sessions"
    if not sessions_dir.is_dir():
        raise ValueError(f"forward_paper_compare_missing_sessions_dir:{sessions_dir}")
    canonical_paths: list[tuple[int, Path]] = []
    for path in sorted(sessions_dir.iterdir()):
        if not path.is_file():
            continue
        match = _CANONICAL_SESSION_FILENAME_RE.match(path.name)
        if match is None:
            continue
        canonical_paths.append((int(match.group(1)), path))

    summaries: list[ForwardPaperSessionSummary] = []
    for _, path in sorted(canonical_paths, key=lambda item: item[0]):
        payload = _read_json_object(path)
        try:
            summaries.append(ForwardPaperSessionSummary.model_validate(payload))
        except Exception as exc:
            raise ValueError(f"forward_paper_compare_invalid_session:{path}:{exc}") from exc
    return summaries


def _summarize_run(*, run_id: str, runs_dir: Path) -> dict[str, Any]:
    run_dir = runs_dir / run_id
    if not run_dir.is_dir():
        raise ValueError(f"forward_paper_compare_missing_run_dir:{run_dir}")

    status_payload = _read_json_object(run_dir / "forward_paper_status.json")
    sessions = _load_session_summaries(run_dir)

    session_outcome_counts: Counter[str] = Counter()
    control_action_counts: Counter[str] = Counter()
    control_reason_counts: Counter[str] = Counter()
    advisory_decision_status_counts: Counter[str] = Counter()

    proposal_count = 0
    event_count = 0
    execution_request_count = 0
    execution_terminal_count = 0

    advisory_marker_session_count = 0
    advisory_decision_count = 0

    pnl_session_count = 0
    pnl_net_realized_total = 0.0
    pnl_total_fee_total = 0.0
    pnl_return_fraction_total = 0.0
    pnl_ending_equity_latest: float | None = None
    latest_pnl_session_number = -1

    ordered_sessions = sorted(sessions, key=lambda item: item.session_number)
    for session in ordered_sessions:
        session_outcome_counts.update([session.session_outcome or "none"])
        if session.control_action is not None:
            control_action_counts.update([session.control_action])
        control_reason_counts.update(session.control_reason_codes)
        execution_request_count += session.execution_request_count or 0
        execution_terminal_count += session.execution_terminal_count or 0

        if session.scorecard is not None:
            proposal_count += session.scorecard.proposal_count
            event_count += session.scorecard.event_count

        if session.pnl is not None:
            pnl_session_count += 1
            pnl_net_realized_total += session.pnl.net_realized_pnl_usd
            pnl_total_fee_total += session.pnl.total_fee_usd
            pnl_return_fraction_total += session.pnl.return_fraction
            if session.session_number >= latest_pnl_session_number:
                latest_pnl_session_number = session.session_number
                pnl_ending_equity_latest = session.pnl.ending_equity_usd

        if session.summary_path is None:
            continue
        summary_payload = _read_json_object(Path(session.summary_path))
        advisory_payload = summary_payload.get("external_confirmation")
        if not isinstance(advisory_payload, dict):
            continue
        advisory_marker_session_count += 1
        advisory_decision_count += _safe_non_negative_int(advisory_payload.get("decision_count"))
        status_counts = advisory_payload.get("decision_status_counts")
        if isinstance(status_counts, dict):
            for status_key, count in status_counts.items():
                advisory_decision_status_counts.update(
                    {str(status_key): _safe_non_negative_int(count)}
                )

    session_count = len(ordered_sessions)
    marker_presence = (
        "absent"
        if advisory_marker_session_count == 0
        else "present" if advisory_marker_session_count == session_count else "mixed"
    )
    last_session_outcome = ordered_sessions[-1].session_outcome if ordered_sessions else None

    pnl_summary: dict[str, Any] | None = None
    if pnl_session_count > 0:
        pnl_summary = {
            "session_count_with_pnl": pnl_session_count,
            "net_realized_pnl_usd_total": pnl_net_realized_total,
            "total_fee_usd_total": pnl_total_fee_total,
            "average_return_fraction": pnl_return_fraction_total / pnl_session_count,
            "latest_ending_equity_usd": pnl_ending_equity_latest,
        }

    return {
        "run_id": run_id,
        "runtime_status": status_payload.get("status"),
        "control_status": status_payload.get("control_status"),
        "control_block_reasons": status_payload.get("control_block_reasons", []),
        "session_count": session_count,
        "completed_session_count": sum(
            1 for session in ordered_sessions if session.status == "completed"
        ),
        "last_session_outcome": last_session_outcome,
        "session_outcome_counts": dict(sorted(session_outcome_counts.items())),
        "proposal_count": proposal_count,
        "event_count": event_count,
        "execution_request_count": execution_request_count,
        "execution_terminal_count": execution_terminal_count,
        "control_action_counts": dict(sorted(control_action_counts.items())),
        "control_reason_counts": dict(sorted(control_reason_counts.items())),
        "advisory_decision_marker_presence": marker_presence,
        "advisory_marker_session_count": advisory_marker_session_count,
        "advisory_marker_absent_session_count": session_count - advisory_marker_session_count,
        "advisory_decision_count": advisory_decision_count,
        "advisory_decision_status_counts": dict(sorted(advisory_decision_status_counts.items())),
        "pnl_summary": pnl_summary,
    }


def _build_comparison(
    *,
    advisory_run_id: str,
    control_run_id: str,
    runs_dir: Path,
) -> dict[str, Any]:
    advisory = _summarize_run(run_id=advisory_run_id, runs_dir=runs_dir)
    control = _summarize_run(run_id=control_run_id, runs_dir=runs_dir)

    advisory_pnl = advisory.get("pnl_summary")
    control_pnl = control.get("pnl_summary")
    pnl_delta: float | None = None
    if isinstance(advisory_pnl, dict) and isinstance(control_pnl, dict):
        advisory_net = advisory_pnl.get("net_realized_pnl_usd_total")
        control_net = control_pnl.get("net_realized_pnl_usd_total")
        if isinstance(advisory_net, int | float) and isinstance(control_net, int | float):
            pnl_delta = float(advisory_net) - float(control_net)

    return {
        "comparison_kind": "forward_paper_advisory_control_comparison_v1",
        "advisory_run_id": advisory_run_id,
        "control_run_id": control_run_id,
        "advisory_run": advisory,
        "control_run": control,
        "delta": {
            "proposal_count": advisory["proposal_count"] - control["proposal_count"],
            "event_count": advisory["event_count"] - control["event_count"],
            "execution_request_count": advisory["execution_request_count"]
            - control["execution_request_count"],
            "execution_terminal_count": advisory["execution_terminal_count"]
            - control["execution_terminal_count"],
            "net_realized_pnl_usd_total": pnl_delta,
        },
    }


def _fmt_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{key}:{value}" for key, value in sorted(counts.items()))


def _fmt_list(values: list[str]) -> str:
    if not values:
        return "none"
    return ", ".join(values)


def _render_markdown(comparison: dict[str, Any]) -> str:
    advisory = comparison["advisory_run"]
    control = comparison["control_run"]
    delta = comparison["delta"]

    def _run_lines(title: str, payload: dict[str, Any]) -> list[str]:
        pnl_summary = payload.get("pnl_summary")
        lines = [
            f"## {title}",
            f"- run_id: `{payload['run_id']}`",
            f"- runtime_status: `{payload['runtime_status']}`",
            f"- session_count: {payload['session_count']}",
            f"- completed_session_count: {payload['completed_session_count']}",
            f"- last_session_outcome: `{payload['last_session_outcome']}`",
            f"- session_outcome_counts: `{_fmt_counts(payload['session_outcome_counts'])}`",
            f"- proposal_count: {payload['proposal_count']}",
            f"- event_count: {payload['event_count']}",
            f"- execution_request_count: {payload['execution_request_count']}",
            f"- execution_terminal_count: {payload['execution_terminal_count']}",
            f"- control_action_counts: `{_fmt_counts(payload['control_action_counts'])}`",
            f"- control_reason_counts: `{_fmt_counts(payload['control_reason_counts'])}`",
            f"- control_block_reasons: `{_fmt_list(payload['control_block_reasons'])}`",
            (
                "- advisory_markers: "
                f"`{payload['advisory_decision_marker_presence']}` "
                f"({payload['advisory_marker_session_count']}/{payload['session_count']} sessions)"
            ),
            (
                "- advisory_decision_status_counts: "
                f"`{_fmt_counts(payload['advisory_decision_status_counts'])}`"
            ),
        ]
        if isinstance(pnl_summary, dict):
            lines.extend(
                [
                    f"- pnl_net_realized_total_usd: {pnl_summary['net_realized_pnl_usd_total']}",
                    f"- pnl_total_fee_usd: {pnl_summary['total_fee_usd_total']}",
                    f"- pnl_average_return_fraction: {pnl_summary['average_return_fraction']}",
                    f"- pnl_latest_ending_equity_usd: {pnl_summary['latest_ending_equity_usd']}",
                ]
            )
        else:
            lines.append("- pnl_summary: `none`")
        return lines

    lines = [
        "# Forward-Paper Advisory vs Control Comparison",
        f"- advisory_run_id: `{comparison['advisory_run_id']}`",
        f"- control_run_id: `{comparison['control_run_id']}`",
        "",
        *_run_lines("Advisory Run", advisory),
        "",
        *_run_lines("Control Run", control),
        "",
        "## Delta (Advisory - Control)",
        f"- proposal_count_delta: {delta['proposal_count']}",
        f"- event_count_delta: {delta['event_count']}",
        f"- execution_request_count_delta: {delta['execution_request_count']}",
        f"- execution_terminal_count_delta: {delta['execution_terminal_count']}",
        f"- net_realized_pnl_usd_total_delta: {delta['net_realized_pnl_usd_total']}",
        "",
    ]
    return "\n".join(lines)


def _sanitize_path_token(value: str) -> str:
    return "".join(char if (char.isalnum() or char in ("-", "_", ".")) else "_" for char in value)


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    runs_dir = Path(args.runs_dir).resolve()
    output_dir = (
        Path(args.output_dir).resolve() if args.output_dir is not None else runs_dir / "comparisons"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    comparison = _build_comparison(
        advisory_run_id=args.advisory_run_id,
        control_run_id=args.control_run_id,
        runs_dir=runs_dir,
    )

    base_name = (
        f"{_sanitize_path_token(args.advisory_run_id)}"
        f"_vs_{_sanitize_path_token(args.control_run_id)}.forward_paper_comparison"
    )
    json_path = output_dir / f"{base_name}.json"
    markdown_path = output_dir / f"{base_name}.md"

    json_path.write_text(json.dumps(comparison, indent=2, sort_keys=True), encoding="utf-8")
    markdown_path.write_text(_render_markdown(comparison), encoding="utf-8")

    print(
        json.dumps(
            {
                "comparison_kind": comparison["comparison_kind"],
                "advisory_run_id": args.advisory_run_id,
                "control_run_id": args.control_run_id,
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
