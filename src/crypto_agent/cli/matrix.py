from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import Settings, load_settings
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
    keys = (
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
    return {key: sum(entry.outcome_counts[key] for entry in entries) for key in keys}


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
