from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from math import fsum
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import Settings, load_settings
from crypto_agent.evaluation.models import EvaluationScorecard, ReplayPnLSummary
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.ids import new_id


class PaperRunMatrixCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture: Path
    run_suffix: str
    equity_usd: float = Field(default=100_000.0, gt=0)
    policy_overrides: dict[str, object] = Field(default_factory=dict)


class PaperRunMatrixEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture: str
    run_id: str
    journal_path: str
    summary_path: str
    outcome_counts: dict[str, int]


class PaperRunMatrixManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matrix_run_id: str
    manifest_path: str
    entry_count: int = Field(ge=0)
    aggregate_counts: dict[str, int]
    entries: list[PaperRunMatrixEntry] = Field(default_factory=list)


MANIFEST_COUNT_KEYS: tuple[str, ...] = (
    "event_count",
    "proposal_count",
    "approval_count",
    "denial_count",
    "halt_count",
    "order_reject_count",
    "fill_event_count",
    "partial_fill_intent_count",
    "alert_count",
)

REPLAY_TOTAL_KEYS: tuple[str, ...] = (
    "event_count",
    "proposal_count",
    "approval_count",
    "denial_count",
    "halt_count",
    "order_intent_count",
    "orders_submitted_count",
    "order_reject_count",
    "fill_event_count",
    "filled_intent_count",
    "partial_fill_intent_count",
    "complete_execution_count",
    "incomplete_execution_count",
    "alert_count",
    "kill_switch_activations",
    "empty_replay_scorecard_count",
)

REPLAY_PNL_KEYS: tuple[str, ...] = (
    "starting_equity_usd",
    "gross_realized_pnl_usd",
    "total_fee_usd",
    "net_realized_pnl_usd",
    "ending_unrealized_pnl_usd",
    "ending_equity_usd",
    "return_fraction",
)


def _default_matrix_cases() -> list[PaperRunMatrixCase]:
    fixtures_dir = Path("tests/fixtures")
    return [
        PaperRunMatrixCase(
            fixture=fixtures_dir / "paper_candles_breakout_long.jsonl",
            run_suffix="breakout-paper-run",
        ),
        PaperRunMatrixCase(
            fixture=fixtures_dir / "paper_candles_mean_reversion_short.jsonl",
            run_suffix="mean-reversion-paper-run",
        ),
        PaperRunMatrixCase(
            fixture=fixtures_dir / "paper_candles_high_volatility.jsonl",
            run_suffix="high-vol-no-signal-paper-run",
        ),
        PaperRunMatrixCase(
            fixture=fixtures_dir / "paper_candles_breakout_long.jsonl",
            run_suffix="breakout-reject-low-equity-paper-run",
            equity_usd=1.0,
        ),
        PaperRunMatrixCase(
            fixture=fixtures_dir / "paper_candles_breakout_long.jsonl",
            run_suffix="breakout-halt-drawdown-zero-paper-run",
            policy_overrides={"max_drawdown_fraction": 0.0},
        ),
    ]


def _settings_for_case(settings: Settings, case: PaperRunMatrixCase) -> Settings:
    if not case.policy_overrides:
        return settings
    return settings.model_copy(
        update={
            "policy": settings.policy.model_copy(update=case.policy_overrides),
        }
    )


def _entry_from_summary(
    *,
    fixture: Path,
    run_id: str,
    journal_path: Path,
    summary_path: Path,
) -> PaperRunMatrixEntry:
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    scorecard = summary["scorecard"]
    operator_summary = summary["operator_summary"]
    return PaperRunMatrixEntry(
        fixture=fixture.name,
        run_id=run_id,
        journal_path=str(journal_path),
        summary_path=str(summary_path),
        outcome_counts={
            "event_count": int(scorecard["event_count"]),
            "proposal_count": int(scorecard["proposal_count"]),
            "approval_count": int(scorecard["approval_count"]),
            "denial_count": int(scorecard["denial_count"]),
            "halt_count": int(scorecard["halt_count"]),
            "order_reject_count": int(scorecard["order_reject_count"]),
            "fill_event_count": int(scorecard["fill_event_count"]),
            "partial_fill_intent_count": int(scorecard["partial_fill_intent_count"]),
            "alert_count": int(operator_summary["alert_count"]),
        },
    )


def _aggregate_counts(entries: list[PaperRunMatrixEntry]) -> dict[str, int]:
    return {key: sum(entry.outcome_counts[key] for entry in entries) for key in MANIFEST_COUNT_KEYS}


def _format_float(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def _relative_journal_path(run_id: str) -> str:
    return f"journals/{run_id}.jsonl"


def _relative_summary_path(run_id: str) -> str:
    return f"runs/{run_id}/summary.json"


def _build_operator_report(manifest: PaperRunMatrixManifest) -> str:
    replay_runs: list[
        tuple[PaperRunMatrixEntry, EvaluationScorecard, ReplayPnLSummary, int, int]
    ] = []
    total_fill_notionals: list[float] = []
    total_fees: list[float] = []
    max_slippages: list[float] = []
    replay_totals: dict[str, int | float] = {key: 0 for key in REPLAY_TOTAL_KEYS}
    replay_totals.update(
        {
            "total_fill_notional_usd": 0.0,
            "total_fee_usd": 0.0,
            "max_slippage_bps": 0.0,
        }
    )
    replay_pnl_totals: dict[str, float] = {key: 0.0 for key in REPLAY_PNL_KEYS}

    for entry in manifest.entries:
        summary = json.loads(Path(entry.summary_path).read_text(encoding="utf-8"))
        replay_result = replay_journal(
            entry.journal_path,
            replay_path=str(summary["replay_path"]),
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        scorecard = replay_result.scorecard
        pnl = replay_result.pnl or ReplayPnLSummary(
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
            ending_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        event_counts = Counter(event.event_type.value for event in replay_result.events)
        alert_count = int(event_counts["alert.raised"])
        kill_switch_activations = int(event_counts["kill_switch.activated"])

        replay_runs.append((entry, scorecard, pnl, alert_count, kill_switch_activations))

        replay_totals["event_count"] += scorecard.event_count
        replay_totals["proposal_count"] += scorecard.proposal_count
        replay_totals["approval_count"] += scorecard.approval_count
        replay_totals["denial_count"] += scorecard.denial_count
        replay_totals["halt_count"] += scorecard.halt_count
        replay_totals["order_intent_count"] += scorecard.order_intent_count
        replay_totals["orders_submitted_count"] += scorecard.orders_submitted_count
        replay_totals["order_reject_count"] += scorecard.order_reject_count
        replay_totals["fill_event_count"] += scorecard.fill_event_count
        replay_totals["filled_intent_count"] += scorecard.filled_intent_count
        replay_totals["partial_fill_intent_count"] += scorecard.partial_fill_intent_count
        replay_totals["complete_execution_count"] += scorecard.complete_execution_count
        replay_totals["incomplete_execution_count"] += scorecard.incomplete_execution_count
        replay_totals["alert_count"] += alert_count
        replay_totals["kill_switch_activations"] += kill_switch_activations

        if scorecard.run_id == "empty":
            replay_totals["empty_replay_scorecard_count"] += 1
        total_fill_notionals.append(scorecard.total_fill_notional_usd)
        total_fees.append(scorecard.total_fee_usd)
        max_slippages.append(scorecard.max_slippage_bps)
        replay_pnl_totals["starting_equity_usd"] += pnl.starting_equity_usd
        replay_pnl_totals["gross_realized_pnl_usd"] += pnl.gross_realized_pnl_usd
        replay_pnl_totals["total_fee_usd"] += pnl.total_fee_usd
        replay_pnl_totals["net_realized_pnl_usd"] += pnl.net_realized_pnl_usd
        replay_pnl_totals["ending_unrealized_pnl_usd"] += pnl.ending_unrealized_pnl_usd
        replay_pnl_totals["ending_equity_usd"] += pnl.ending_equity_usd

    replay_totals["total_fill_notional_usd"] = fsum(total_fill_notionals)
    replay_totals["total_fee_usd"] = fsum(total_fees)
    replay_totals["max_slippage_bps"] = max(max_slippages, default=0.0)
    if replay_pnl_totals["starting_equity_usd"] > 0:
        replay_pnl_totals["return_fraction"] = (
            replay_pnl_totals["ending_equity_usd"] - replay_pnl_totals["starting_equity_usd"]
        ) / replay_pnl_totals["starting_equity_usd"]

    lines = [
        "# Paper Run Matrix Operator Report",
        "",
        f"matrix_run_id: {manifest.matrix_run_id}",
        f"entry_count: {manifest.entry_count}",
        f"manifest_path: runs/{manifest.matrix_run_id}/manifest.json",
        f"report_path: runs/{manifest.matrix_run_id}/report.md",
        "",
        "## Aggregate Manifest Counts",
    ]
    lines.extend(f"{key}: {manifest.aggregate_counts.get(key, 0)}" for key in MANIFEST_COUNT_KEYS)
    lines.extend(["", "## Aggregate Replay Totals"])
    lines.extend(f"{key}: {int(replay_totals[key])}" for key in REPLAY_TOTAL_KEYS)
    lines.extend(
        [
            "total_fill_notional_usd: "
            f"{_format_float(float(replay_totals['total_fill_notional_usd']))}",
            f"total_fee_usd: {_format_float(float(replay_totals['total_fee_usd']))}",
            f"max_slippage_bps: {_format_float(float(replay_totals['max_slippage_bps']))}",
            "",
            "## Aggregate Replay PnL",
        ]
    )
    lines.extend(
        f"{key}: {_format_float(float(replay_pnl_totals[key]))}" for key in REPLAY_PNL_KEYS
    )
    lines.extend(
        [
            "",
            "## Per-Run Details",
        ]
    )

    for entry, scorecard, pnl, alert_count, kill_switch_activations in replay_runs:
        lines.extend(
            [
                f"### run_id: {entry.run_id}",
                f"fixture: {entry.fixture}",
                f"journal_path: {_relative_journal_path(entry.run_id)}",
                f"summary_path: {_relative_summary_path(entry.run_id)}",
                f"manifest_event_count: {entry.outcome_counts['event_count']}",
                f"manifest_proposal_count: {entry.outcome_counts['proposal_count']}",
                f"manifest_approval_count: {entry.outcome_counts['approval_count']}",
                f"manifest_denial_count: {entry.outcome_counts['denial_count']}",
                f"manifest_halt_count: {entry.outcome_counts['halt_count']}",
                f"manifest_order_reject_count: {entry.outcome_counts['order_reject_count']}",
                f"manifest_fill_event_count: {entry.outcome_counts['fill_event_count']}",
                "manifest_partial_fill_intent_count: "
                f"{entry.outcome_counts['partial_fill_intent_count']}",
                f"manifest_alert_count: {entry.outcome_counts['alert_count']}",
                f"replay_run_id: {scorecard.run_id}",
                f"replay_event_count: {scorecard.event_count}",
                f"replay_proposal_count: {scorecard.proposal_count}",
                f"replay_approval_count: {scorecard.approval_count}",
                f"replay_denial_count: {scorecard.denial_count}",
                f"replay_halt_count: {scorecard.halt_count}",
                f"replay_order_intent_count: {scorecard.order_intent_count}",
                f"replay_orders_submitted_count: {scorecard.orders_submitted_count}",
                f"replay_order_reject_count: {scorecard.order_reject_count}",
                f"replay_fill_event_count: {scorecard.fill_event_count}",
                f"replay_filled_intent_count: {scorecard.filled_intent_count}",
                f"replay_partial_fill_intent_count: {scorecard.partial_fill_intent_count}",
                f"replay_complete_execution_count: {scorecard.complete_execution_count}",
                f"replay_incomplete_execution_count: {scorecard.incomplete_execution_count}",
                f"replay_alert_count: {alert_count}",
                f"replay_kill_switch_activations: {kill_switch_activations}",
                f"replay_average_slippage_bps: {_format_float(scorecard.average_slippage_bps)}",
                f"replay_max_slippage_bps: {_format_float(scorecard.max_slippage_bps)}",
                "replay_total_fill_notional_usd: "
                f"{_format_float(scorecard.total_fill_notional_usd)}",
                f"replay_total_fee_usd: {_format_float(scorecard.total_fee_usd)}",
                f"replay_starting_equity_usd: {_format_float(pnl.starting_equity_usd)}",
                f"replay_gross_realized_pnl_usd: {_format_float(pnl.gross_realized_pnl_usd)}",
                f"replay_pnl_total_fee_usd: {_format_float(pnl.total_fee_usd)}",
                f"replay_net_realized_pnl_usd: {_format_float(pnl.net_realized_pnl_usd)}",
                f"replay_ending_unrealized_pnl_usd: {_format_float(pnl.ending_unrealized_pnl_usd)}",
                f"replay_ending_equity_usd: {_format_float(pnl.ending_equity_usd)}",
                f"replay_return_fraction: {_format_float(pnl.return_fraction)}",
                "",
            ]
        )

    return "\n".join(lines)


def _write_operator_report(manifest: PaperRunMatrixManifest) -> Path:
    report_path = Path(manifest.manifest_path).with_name("report.md")
    report_path.write_text(_build_operator_report(manifest), encoding="utf-8")
    return report_path


def run_paper_replay_matrix(
    *,
    settings: Settings,
    matrix_run_id: str | None = None,
    cases: list[PaperRunMatrixCase] | None = None,
    manifest_path: str | Path | None = None,
) -> PaperRunMatrixManifest:
    resolved_matrix_run_id = matrix_run_id or f"paper-run-matrix-{new_id()}"
    resolved_cases = cases or _default_matrix_cases()
    resolved_manifest_path = (
        Path(manifest_path)
        if manifest_path is not None
        else settings.paths.runs_dir / resolved_matrix_run_id / "manifest.json"
    )

    if resolved_manifest_path.exists():
        raise FileExistsError(f"Manifest path already exists: {resolved_manifest_path}")

    resolved_manifest_path.parent.mkdir(parents=True, exist_ok=False)
    entries: list[PaperRunMatrixEntry] = []

    for case in resolved_cases:
        run_id = f"{resolved_matrix_run_id}-{case.run_suffix}"
        result = run_paper_replay(
            case.fixture,
            settings=_settings_for_case(settings, case),
            run_id=run_id,
            equity_usd=case.equity_usd,
        )
        entries.append(
            _entry_from_summary(
                fixture=case.fixture,
                run_id=run_id,
                journal_path=result.journal_path,
                summary_path=result.summary_path,
            )
        )

    manifest = PaperRunMatrixManifest(
        matrix_run_id=resolved_matrix_run_id,
        manifest_path=str(resolved_manifest_path),
        entry_count=len(entries),
        aggregate_counts=_aggregate_counts(entries),
        entries=entries,
    )
    resolved_manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_operator_report(manifest)
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the validated paper replay harness across the default fixture matrix."
    )
    parser.add_argument(
        "--config",
        default="config/paper.yaml",
        help="Path to the paper-mode settings file.",
    )
    parser.add_argument(
        "--matrix-run-id",
        default=None,
        help="Optional explicit matrix run identifier. Defaults to a generated id.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    manifest = run_paper_replay_matrix(
        settings=load_settings(args.config),
        matrix_run_id=args.matrix_run_id,
    )
    print(
        json.dumps(
            {
                "matrix_run_id": manifest.matrix_run_id,
                "manifest_path": manifest.manifest_path,
                "entry_count": manifest.entry_count,
                "aggregate_counts": manifest.aggregate_counts,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
