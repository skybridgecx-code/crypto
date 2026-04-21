from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from math import fsum
from pathlib import Path
from statistics import pstdev
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.cli.main import run_paper_replay, write_operator_run_index
from crypto_agent.config import Settings, load_settings
from crypto_agent.evaluation.models import (
    EvaluationScorecard,
    MatrixComparison,
    MatrixComparisonAggregate,
    MatrixComparisonAggregateFailureModeOutcome,
    MatrixComparisonAggregateRiskPolicyOutcome,
    MatrixComparisonAggregateStressOutcome,
    MatrixComparisonAggregateWalkForwardSliceOutcome,
    MatrixComparisonFailureModeOutcome,
    MatrixComparisonRanking,
    MatrixComparisonRiskPolicyOutcome,
    MatrixComparisonRow,
    MatrixComparisonStressOutcome,
    MatrixComparisonWalkForwardSliceOutcome,
    MatrixTradeLedger,
    MatrixTradeLedgerEntry,
    ReplayPnLSummary,
    TradeLedger,
)
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.evaluation.scorecard import build_replay_pnl
from crypto_agent.events.envelope import EventEnvelope
from crypto_agent.ids import new_id
from crypto_agent.market_data.replay import load_candle_replay


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
    matrix_comparison_path: str
    matrix_trade_ledger_path: str
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


MATRIX_STRESS_SCENARIOS: tuple[tuple[str, float], ...] = (
    ("cost_slippage_plus_5bps", 5.0),
    ("cost_slippage_plus_10bps", 10.0),
)
MATRIX_RISK_POLICY_SCENARIOS: tuple[tuple[str, float], ...] = (
    ("policy_tighter_75pct", 0.75),
    ("policy_baseline_100pct", 1.0),
    ("policy_looser_125pct", 1.25),
)
MATRIX_FAILURE_MODE_SCENARIOS: tuple[tuple[str, float, float], ...] = (
    ("failure_reduced_capture_70pct", 0.70, 0.0),
    ("failure_delayed_opportunity_haircut_20pct", 1.0, 0.20),
    ("failure_combined_bad_case", 0.70, 0.20),
)
MATRIX_WALK_FORWARD_SLICE_COUNT = 3


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


def _relative_matrix_trade_ledger_path(matrix_run_id: str) -> str:
    return f"runs/{matrix_run_id}/matrix_trade_ledger.json"


def _relative_matrix_comparison_path(matrix_run_id: str) -> str:
    return f"runs/{matrix_run_id}/matrix_comparison.json"


def _walk_forward_slice_boundaries(candle_count: int) -> list[tuple[int, int]]:
    if candle_count <= 0:
        return []
    slice_count = min(MATRIX_WALK_FORWARD_SLICE_COUNT, candle_count)
    base, remainder = divmod(candle_count, slice_count)
    boundaries: list[tuple[int, int]] = []
    start = 0
    for index in range(slice_count):
        width = base + (1 if index < remainder else 0)
        end = start + width - 1
        boundaries.append((start, end))
        start = end + 1
    return boundaries


def _build_walk_forward_slices(
    *,
    events: list[EventEnvelope],
    replay_path: str,
    starting_equity_usd: float,
) -> list[MatrixComparisonWalkForwardSliceOutcome]:
    candles = load_candle_replay(Path(replay_path))
    boundaries = _walk_forward_slice_boundaries(len(candles))
    if not boundaries:
        return []

    slices: list[MatrixComparisonWalkForwardSliceOutcome] = []
    previous_equity = starting_equity_usd
    for slice_index, (start_idx, end_idx) in enumerate(boundaries, start=1):
        slice_id = f"window_{slice_index}_of_{len(boundaries)}"
        end_close_time = candles[end_idx].close_time
        cumulative_events = [event for event in events if event.timestamp <= end_close_time]
        final_close_by_symbol = {candle.symbol: candle.close for candle in candles[: end_idx + 1]}
        cumulative_pnl = build_replay_pnl(
            cumulative_events,
            final_close_by_symbol=final_close_by_symbol,
            starting_equity_usd=starting_equity_usd,
        )
        slice_net_pnl_delta_usd = cumulative_pnl.ending_equity_usd - previous_equity
        slice_return_fraction_delta = (
            slice_net_pnl_delta_usd / previous_equity if previous_equity > 0 else 0.0
        )
        slices.append(
            MatrixComparisonWalkForwardSliceOutcome(
                slice_id=slice_id,
                slice_index=slice_index,
                start_candle_index=start_idx + 1,
                end_candle_index=end_idx + 1,
                candle_count=(end_idx - start_idx + 1),
                cumulative_ending_equity_usd=cumulative_pnl.ending_equity_usd,
                cumulative_return_fraction=cumulative_pnl.return_fraction,
                slice_net_pnl_delta_usd=slice_net_pnl_delta_usd,
                slice_return_fraction_delta=slice_return_fraction_delta,
                verdict="pass" if slice_net_pnl_delta_usd >= 0 else "fail",
            )
        )
        previous_equity = cumulative_pnl.ending_equity_usd
    return slices


def _build_matrix_comparison(manifest: PaperRunMatrixManifest) -> MatrixComparison:
    rows: list[MatrixComparisonRow] = []
    scenario_bps = dict(MATRIX_STRESS_SCENARIOS)
    risk_policy_scale = dict(MATRIX_RISK_POLICY_SCENARIOS)
    max_stress_scenario_id, max_stress_bps = MATRIX_STRESS_SCENARIOS[-1]

    def _row_stress_outcomes(
        *,
        baseline_pnl: ReplayPnLSummary,
        total_fill_notional_usd: float,
    ) -> list[MatrixComparisonStressOutcome]:
        outcomes: list[MatrixComparisonStressOutcome] = []
        for scenario_id, additional_cost_slippage_bps in MATRIX_STRESS_SCENARIOS:
            incremental_cost_usd = total_fill_notional_usd * additional_cost_slippage_bps / 10_000.0
            stressed_net_realized_pnl_usd = baseline_pnl.net_realized_pnl_usd - incremental_cost_usd
            stressed_ending_equity_usd = baseline_pnl.ending_equity_usd - incremental_cost_usd
            stressed_return_fraction = (
                (stressed_ending_equity_usd - baseline_pnl.starting_equity_usd)
                / baseline_pnl.starting_equity_usd
                if baseline_pnl.starting_equity_usd > 0
                else 0.0
            )
            delta_return_fraction = stressed_return_fraction - baseline_pnl.return_fraction
            outcomes.append(
                MatrixComparisonStressOutcome(
                    scenario_id=scenario_id,
                    additional_cost_slippage_bps=additional_cost_slippage_bps,
                    incremental_cost_usd=incremental_cost_usd,
                    stressed_net_realized_pnl_usd=stressed_net_realized_pnl_usd,
                    stressed_ending_equity_usd=stressed_ending_equity_usd,
                    stressed_return_fraction=stressed_return_fraction,
                    delta_net_realized_pnl_usd_vs_baseline=-incremental_cost_usd,
                    delta_return_fraction_vs_baseline=delta_return_fraction,
                    verdict="pass" if stressed_return_fraction >= 0 else "fail",
                )
            )
        return outcomes

    def _fail_threshold_bps(row: MatrixComparisonRow) -> float:
        if row.first_fail_scenario_id == "baseline":
            return 0.0
        if row.first_fail_scenario_id is None:
            return float("inf")
        return float(scenario_bps.get(row.first_fail_scenario_id, float("inf")))

    def _row_risk_policy_outcomes(
        *, baseline_pnl: ReplayPnLSummary
    ) -> list[MatrixComparisonRiskPolicyOutcome]:
        outcomes: list[MatrixComparisonRiskPolicyOutcome] = []
        for scenario_id, scale_multiplier in MATRIX_RISK_POLICY_SCENARIOS:
            stressed_net_realized_pnl_usd = baseline_pnl.net_realized_pnl_usd * scale_multiplier
            stressed_ending_unrealized_pnl_usd = (
                baseline_pnl.ending_unrealized_pnl_usd * scale_multiplier
            )
            stressed_ending_equity_usd = (
                baseline_pnl.starting_equity_usd
                + stressed_net_realized_pnl_usd
                + stressed_ending_unrealized_pnl_usd
            )
            stressed_return_fraction = (
                (stressed_ending_equity_usd - baseline_pnl.starting_equity_usd)
                / baseline_pnl.starting_equity_usd
                if baseline_pnl.starting_equity_usd > 0
                else 0.0
            )
            outcomes.append(
                MatrixComparisonRiskPolicyOutcome(
                    scenario_id=scenario_id,
                    risk_scale_multiplier=scale_multiplier,
                    stressed_net_realized_pnl_usd=stressed_net_realized_pnl_usd,
                    stressed_ending_unrealized_pnl_usd=stressed_ending_unrealized_pnl_usd,
                    stressed_ending_equity_usd=stressed_ending_equity_usd,
                    stressed_return_fraction=stressed_return_fraction,
                    delta_net_realized_pnl_usd_vs_baseline=(
                        stressed_net_realized_pnl_usd - baseline_pnl.net_realized_pnl_usd
                    ),
                    delta_return_fraction_vs_baseline=(
                        stressed_return_fraction - baseline_pnl.return_fraction
                    ),
                    verdict="pass" if stressed_return_fraction >= 0 else "fail",
                )
            )
        return outcomes

    def _row_failure_mode_outcomes(
        *, baseline_pnl: ReplayPnLSummary
    ) -> list[MatrixComparisonFailureModeOutcome]:
        outcomes: list[MatrixComparisonFailureModeOutcome] = []
        baseline_net = baseline_pnl.net_realized_pnl_usd
        baseline_unrealized = baseline_pnl.ending_unrealized_pnl_usd
        for (
            scenario_id,
            reduced_capture_multiplier,
            delayed_haircut_fraction,
        ) in MATRIX_FAILURE_MODE_SCENARIOS:
            stressed_net_realized_pnl_usd = (
                baseline_net * reduced_capture_multiplier if baseline_net > 0 else baseline_net
            )
            stressed_ending_unrealized_pnl_usd = (
                baseline_unrealized * reduced_capture_multiplier
                if baseline_unrealized > 0
                else baseline_unrealized
            )
            positive_capture_margin_usd = max(
                stressed_net_realized_pnl_usd + stressed_ending_unrealized_pnl_usd, 0.0
            )
            delayed_opportunity_haircut_usd = positive_capture_margin_usd * delayed_haircut_fraction
            stressed_net_realized_pnl_usd -= delayed_opportunity_haircut_usd
            stressed_ending_equity_usd = (
                baseline_pnl.starting_equity_usd
                + stressed_net_realized_pnl_usd
                + stressed_ending_unrealized_pnl_usd
            )
            stressed_return_fraction = (
                (stressed_ending_equity_usd - baseline_pnl.starting_equity_usd)
                / baseline_pnl.starting_equity_usd
                if baseline_pnl.starting_equity_usd > 0
                else 0.0
            )
            outcomes.append(
                MatrixComparisonFailureModeOutcome(
                    scenario_id=scenario_id,
                    reduced_fill_capture_multiplier=reduced_capture_multiplier,
                    delayed_opportunity_haircut_fraction=delayed_haircut_fraction,
                    stressed_net_realized_pnl_usd=stressed_net_realized_pnl_usd,
                    stressed_ending_unrealized_pnl_usd=stressed_ending_unrealized_pnl_usd,
                    stressed_ending_equity_usd=stressed_ending_equity_usd,
                    stressed_return_fraction=stressed_return_fraction,
                    margin_loss_net_pnl_usd=max(
                        baseline_pnl.net_realized_pnl_usd - stressed_net_realized_pnl_usd, 0.0
                    ),
                    margin_loss_return_fraction=max(
                        baseline_pnl.return_fraction - stressed_return_fraction, 0.0
                    ),
                    verdict="pass" if stressed_return_fraction >= 0 else "fail",
                )
            )
        return outcomes

    failure_mode_order = {
        scenario_id: index
        for index, (scenario_id, _, _) in enumerate(MATRIX_FAILURE_MODE_SCENARIOS, start=1)
    }

    def _failure_mode_threshold_order(row: MatrixComparisonRow) -> float:
        if row.failure_mode_first_fail_scenario_id == "baseline":
            return 0.0
        if row.failure_mode_first_fail_scenario_id is None:
            return float("inf")
        return float(failure_mode_order.get(row.failure_mode_first_fail_scenario_id, float("inf")))

    for entry in manifest.entries:
        summary = json.loads(Path(entry.summary_path).read_text(encoding="utf-8"))
        replay_result = replay_journal(
            entry.journal_path,
            replay_path=str(summary["replay_path"]),
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        pnl = replay_result.pnl or ReplayPnLSummary(
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
            ending_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        trade_ledger = TradeLedger.model_validate(
            json.loads(Path(summary["trade_ledger_path"]).read_text(encoding="utf-8"))
        )
        baseline_robustness_verdict: Literal["pass", "fail"] = (
            "pass" if pnl.return_fraction >= 0 else "fail"
        )
        stress_outcomes = _row_stress_outcomes(
            baseline_pnl=pnl,
            total_fill_notional_usd=replay_result.scorecard.total_fill_notional_usd,
        )
        risk_policy_outcomes = _row_risk_policy_outcomes(baseline_pnl=pnl)
        failure_mode_outcomes = _row_failure_mode_outcomes(baseline_pnl=pnl)
        risk_policy_first_fail_scenario_id = next(
            (outcome.scenario_id for outcome in risk_policy_outcomes if outcome.verdict == "fail"),
            None,
        )
        risk_policy_first_fail_scale_multiplier = (
            risk_policy_scale[risk_policy_first_fail_scenario_id]
            if risk_policy_first_fail_scenario_id is not None
            else None
        )
        risk_policy_pass_scenario_count = sum(
            1 for outcome in risk_policy_outcomes if outcome.verdict == "pass"
        )
        risk_policy_fail_scenario_count = (
            len(risk_policy_outcomes) - risk_policy_pass_scenario_count
        )
        risk_policy_stressed_net_values = [
            outcome.stressed_net_realized_pnl_usd for outcome in risk_policy_outcomes
        ]
        risk_policy_stressed_return_values = [
            outcome.stressed_return_fraction for outcome in risk_policy_outcomes
        ]
        risk_policy_most_adverse_outcome = min(
            risk_policy_outcomes,
            key=lambda outcome: (
                outcome.delta_net_realized_pnl_usd_vs_baseline,
                outcome.scenario_id,
            ),
            default=None,
        )
        failure_mode_first_fail_scenario_id = (
            "baseline"
            if baseline_robustness_verdict == "fail"
            else next(
                (
                    outcome.scenario_id
                    for outcome in failure_mode_outcomes
                    if outcome.verdict == "fail"
                ),
                None,
            )
        )
        failure_mode_pass_scenario_count = sum(
            1 for outcome in failure_mode_outcomes if outcome.verdict == "pass"
        )
        failure_mode_fail_scenario_count = (
            len(failure_mode_outcomes) - failure_mode_pass_scenario_count
        )
        failure_mode_stressed_net_values = [
            outcome.stressed_net_realized_pnl_usd for outcome in failure_mode_outcomes
        ]
        failure_mode_stressed_return_values = [
            outcome.stressed_return_fraction for outcome in failure_mode_outcomes
        ]
        failure_mode_most_adverse_outcome = max(
            failure_mode_outcomes,
            key=lambda outcome: (
                outcome.margin_loss_net_pnl_usd,
                outcome.margin_loss_return_fraction,
                outcome.scenario_id,
            ),
            default=None,
        )
        first_fail_scenario_id = (
            "baseline"
            if baseline_robustness_verdict == "fail"
            else next(
                (outcome.scenario_id for outcome in stress_outcomes if outcome.verdict == "fail"),
                None,
            )
        )
        first_fail_additional_cost_slippage_bps = (
            0.0
            if first_fail_scenario_id == "baseline"
            else (
                float(scenario_bps[first_fail_scenario_id])
                if first_fail_scenario_id is not None and first_fail_scenario_id in scenario_bps
                else None
            )
        )
        max_stress_outcome = next(
            (
                outcome
                for outcome in stress_outcomes
                if outcome.scenario_id == max_stress_scenario_id
            ),
            None,
        )
        max_stress_net_pnl_drag_usd = (
            abs(float(max_stress_outcome.delta_net_realized_pnl_usd_vs_baseline))
            if max_stress_outcome is not None
            else 0.0
        )
        walk_forward_slices = _build_walk_forward_slices(
            events=replay_result.events,
            replay_path=str(summary["replay_path"]),
            starting_equity_usd=pnl.starting_equity_usd,
        )
        walk_forward_net_deltas = [slice_.slice_net_pnl_delta_usd for slice_ in walk_forward_slices]
        walk_forward_pass_slice_count = sum(
            1 for slice_ in walk_forward_slices if slice_.verdict == "pass"
        )
        walk_forward_fail_slice_count = len(walk_forward_slices) - walk_forward_pass_slice_count
        walk_forward_best_slice = max(
            walk_forward_slices,
            key=lambda slice_: (slice_.slice_net_pnl_delta_usd, -slice_.slice_index),
            default=None,
        )
        walk_forward_worst_slice = min(
            walk_forward_slices,
            key=lambda slice_: (slice_.slice_net_pnl_delta_usd, slice_.slice_index),
            default=None,
        )
        total_positive_slice_net_pnl = fsum(
            max(slice_.slice_net_pnl_delta_usd, 0.0) for slice_ in walk_forward_slices
        )
        walk_forward_profit_concentration_fraction = (
            max(walk_forward_best_slice.slice_net_pnl_delta_usd, 0.0) / total_positive_slice_net_pnl
            if walk_forward_best_slice is not None and total_positive_slice_net_pnl > 0
            else 0.0
        )
        rows.append(
            MatrixComparisonRow(
                run_id=entry.run_id,
                fixture=entry.fixture,
                proposal_count=entry.outcome_counts["proposal_count"],
                halt_count=entry.outcome_counts["halt_count"],
                order_reject_count=entry.outcome_counts["order_reject_count"],
                fill_event_count=entry.outcome_counts["fill_event_count"],
                partial_fill_intent_count=entry.outcome_counts["partial_fill_intent_count"],
                alert_count=entry.outcome_counts["alert_count"],
                ledger_row_count=trade_ledger.row_count,
                starting_equity_usd=pnl.starting_equity_usd,
                net_realized_pnl_usd=pnl.net_realized_pnl_usd,
                ending_unrealized_pnl_usd=pnl.ending_unrealized_pnl_usd,
                ending_equity_usd=pnl.ending_equity_usd,
                return_fraction=pnl.return_fraction,
                baseline_robustness_verdict=baseline_robustness_verdict,
                stress_outcomes=stress_outcomes,
                robustness_verdict=(
                    "pass"
                    if baseline_robustness_verdict == "pass"
                    and all(outcome.verdict == "pass" for outcome in stress_outcomes)
                    else "fail"
                ),
                first_fail_scenario_id=first_fail_scenario_id,
                first_fail_additional_cost_slippage_bps=first_fail_additional_cost_slippage_bps,
                max_stress_scenario_id=max_stress_scenario_id,
                max_stress_additional_cost_slippage_bps=max_stress_bps,
                max_stress_net_pnl_drag_usd=max_stress_net_pnl_drag_usd,
                stress_delta_net_realized_pnl_usd_by_scenario={
                    outcome.scenario_id: outcome.delta_net_realized_pnl_usd_vs_baseline
                    for outcome in stress_outcomes
                },
                stress_delta_return_fraction_by_scenario={
                    outcome.scenario_id: outcome.delta_return_fraction_vs_baseline
                    for outcome in stress_outcomes
                },
                risk_policy_outcomes=risk_policy_outcomes,
                risk_policy_robustness_verdict=(
                    "pass"
                    if all(outcome.verdict == "pass" for outcome in risk_policy_outcomes)
                    else "fail"
                ),
                risk_policy_first_fail_scenario_id=risk_policy_first_fail_scenario_id,
                risk_policy_first_fail_scale_multiplier=risk_policy_first_fail_scale_multiplier,
                risk_policy_pass_scenario_count=risk_policy_pass_scenario_count,
                risk_policy_fail_scenario_count=risk_policy_fail_scenario_count,
                risk_policy_sensitivity_span_net_pnl_usd=(
                    max(risk_policy_stressed_net_values) - min(risk_policy_stressed_net_values)
                ),
                risk_policy_sensitivity_span_return_fraction=(
                    max(risk_policy_stressed_return_values)
                    - min(risk_policy_stressed_return_values)
                ),
                risk_policy_most_adverse_scenario_id=(
                    risk_policy_most_adverse_outcome.scenario_id
                    if risk_policy_most_adverse_outcome is not None
                    else None
                ),
                risk_policy_most_adverse_delta_net_pnl_usd=(
                    risk_policy_most_adverse_outcome.delta_net_realized_pnl_usd_vs_baseline
                    if risk_policy_most_adverse_outcome is not None
                    else 0.0
                ),
                risk_policy_is_narrow_dependence=(
                    baseline_robustness_verdict == "pass"
                    and any(
                        outcome.verdict == "fail"
                        for outcome in risk_policy_outcomes
                        if outcome.scenario_id != "policy_baseline_100pct"
                    )
                ),
                failure_mode_outcomes=failure_mode_outcomes,
                failure_mode_robustness_verdict=(
                    "pass"
                    if all(outcome.verdict == "pass" for outcome in failure_mode_outcomes)
                    else "fail"
                ),
                failure_mode_first_fail_scenario_id=failure_mode_first_fail_scenario_id,
                failure_mode_pass_scenario_count=failure_mode_pass_scenario_count,
                failure_mode_fail_scenario_count=failure_mode_fail_scenario_count,
                failure_mode_sensitivity_span_net_pnl_usd=(
                    max(failure_mode_stressed_net_values) - min(failure_mode_stressed_net_values)
                ),
                failure_mode_sensitivity_span_return_fraction=(
                    max(failure_mode_stressed_return_values)
                    - min(failure_mode_stressed_return_values)
                ),
                failure_mode_most_adverse_scenario_id=(
                    failure_mode_most_adverse_outcome.scenario_id
                    if failure_mode_most_adverse_outcome is not None
                    else None
                ),
                failure_mode_most_adverse_margin_loss_net_pnl_usd=(
                    failure_mode_most_adverse_outcome.margin_loss_net_pnl_usd
                    if failure_mode_most_adverse_outcome is not None
                    else 0.0
                ),
                walk_forward_slices=walk_forward_slices,
                walk_forward_slice_count=len(walk_forward_slices),
                walk_forward_pass_slice_count=walk_forward_pass_slice_count,
                walk_forward_fail_slice_count=walk_forward_fail_slice_count,
                walk_forward_consistency_stddev_net_pnl_usd=(
                    pstdev(walk_forward_net_deltas) if len(walk_forward_net_deltas) > 1 else 0.0
                ),
                walk_forward_consistency_range_net_pnl_usd=(
                    (max(walk_forward_net_deltas) - min(walk_forward_net_deltas))
                    if walk_forward_net_deltas
                    else 0.0
                ),
                walk_forward_best_slice_id=(
                    walk_forward_best_slice.slice_id
                    if walk_forward_best_slice is not None
                    else None
                ),
                walk_forward_worst_slice_id=(
                    walk_forward_worst_slice.slice_id
                    if walk_forward_worst_slice is not None
                    else None
                ),
                walk_forward_best_slice_net_pnl_delta_usd=(
                    walk_forward_best_slice.slice_net_pnl_delta_usd
                    if walk_forward_best_slice is not None
                    else 0.0
                ),
                walk_forward_worst_slice_net_pnl_delta_usd=(
                    walk_forward_worst_slice.slice_net_pnl_delta_usd
                    if walk_forward_worst_slice is not None
                    else 0.0
                ),
                walk_forward_profit_concentration_fraction=walk_forward_profit_concentration_fraction,
                walk_forward_is_profit_concentrated=(
                    walk_forward_profit_concentration_fraction >= 0.8
                ),
                walk_forward_robustness_verdict=(
                    "pass" if walk_forward_fail_slice_count == 0 else "fail"
                ),
            )
        )

    fragility_order = sorted(
        rows,
        key=lambda row: (
            _fail_threshold_bps(row),
            -row.max_stress_net_pnl_drag_usd,
            row.return_fraction,
            row.run_id,
        ),
    )
    resilience_order = sorted(
        rows,
        key=lambda row: (
            0 if row.first_fail_scenario_id is None else 1,
            -_fail_threshold_bps(row) if row.first_fail_scenario_id is not None else 0.0,
            row.max_stress_net_pnl_drag_usd,
            -row.return_fraction,
            row.run_id,
        ),
    )
    fragility_rank_by_run_id = {
        row.run_id: rank for rank, row in enumerate(fragility_order, start=1)
    }
    resilience_rank_by_run_id = {
        row.run_id: rank for rank, row in enumerate(resilience_order, start=1)
    }
    for row in rows:
        row.fragility_rank = fragility_rank_by_run_id[row.run_id]
        row.resilience_rank = resilience_rank_by_run_id[row.run_id]

    failure_mode_fragility_order = sorted(
        rows,
        key=lambda row: (
            _failure_mode_threshold_order(row),
            -row.failure_mode_most_adverse_margin_loss_net_pnl_usd,
            row.return_fraction,
            row.run_id,
        ),
    )
    failure_mode_resilience_order = sorted(
        rows,
        key=lambda row: (
            0 if row.failure_mode_first_fail_scenario_id is None else 1,
            (
                -_failure_mode_threshold_order(row)
                if row.failure_mode_first_fail_scenario_id is not None
                else 0.0
            ),
            row.failure_mode_most_adverse_margin_loss_net_pnl_usd,
            -row.return_fraction,
            row.run_id,
        ),
    )
    failure_mode_fragility_rank_by_run_id = {
        row.run_id: rank for rank, row in enumerate(failure_mode_fragility_order, start=1)
    }
    failure_mode_resilience_rank_by_run_id = {
        row.run_id: rank for rank, row in enumerate(failure_mode_resilience_order, start=1)
    }
    for row in rows:
        row.failure_mode_fragility_rank = failure_mode_fragility_rank_by_run_id[row.run_id]
        row.failure_mode_resilience_rank = failure_mode_resilience_rank_by_run_id[row.run_id]

    total_starting_equity_usd = fsum(row.starting_equity_usd for row in rows)
    total_net_realized_pnl_usd = fsum(row.net_realized_pnl_usd for row in rows)
    total_ending_equity_usd = fsum(row.ending_equity_usd for row in rows)
    aggregate_return_fraction = (
        (total_ending_equity_usd - total_starting_equity_usd) / total_starting_equity_usd
        if total_starting_equity_usd > 0
        else 0.0
    )
    aggregate_baseline_robustness_verdict: Literal["pass", "fail"] = (
        "pass" if aggregate_return_fraction >= 0 else "fail"
    )
    aggregate_stress_outcomes: list[MatrixComparisonAggregateStressOutcome] = []
    for scenario_id, additional_cost_slippage_bps in MATRIX_STRESS_SCENARIOS:
        incremental_cost_usd = fsum(
            outcome.incremental_cost_usd
            for row in rows
            for outcome in row.stress_outcomes
            if outcome.scenario_id == scenario_id
        )
        stressed_total_ending_equity_usd = total_ending_equity_usd - incremental_cost_usd
        stressed_aggregate_return_fraction = (
            (stressed_total_ending_equity_usd - total_starting_equity_usd)
            / total_starting_equity_usd
            if total_starting_equity_usd > 0
            else 0.0
        )
        aggregate_stress_outcomes.append(
            MatrixComparisonAggregateStressOutcome(
                scenario_id=scenario_id,
                additional_cost_slippage_bps=additional_cost_slippage_bps,
                incremental_cost_usd=incremental_cost_usd,
                stressed_total_net_realized_pnl_usd=(
                    total_net_realized_pnl_usd - incremental_cost_usd
                ),
                stressed_total_ending_equity_usd=stressed_total_ending_equity_usd,
                stressed_aggregate_return_fraction=stressed_aggregate_return_fraction,
                delta_total_net_realized_pnl_usd_vs_baseline=-incremental_cost_usd,
                delta_aggregate_return_fraction_vs_baseline=(
                    stressed_aggregate_return_fraction - aggregate_return_fraction
                ),
                failing_run_count=sum(
                    1
                    for row in rows
                    for outcome in row.stress_outcomes
                    if outcome.scenario_id == scenario_id and outcome.verdict == "fail"
                ),
                verdict="pass" if stressed_aggregate_return_fraction >= 0 else "fail",
            )
        )
    aggregate_risk_policy_outcomes: list[MatrixComparisonAggregateRiskPolicyOutcome] = []
    for scenario_id, scale_multiplier in MATRIX_RISK_POLICY_SCENARIOS:
        scenario_rows = [
            next(
                outcome
                for outcome in row.risk_policy_outcomes
                if outcome.scenario_id == scenario_id
            )
            for row in rows
        ]
        stressed_total_net_realized_pnl_usd = fsum(
            outcome.stressed_net_realized_pnl_usd for outcome in scenario_rows
        )
        stressed_total_ending_equity_usd = fsum(
            outcome.stressed_ending_equity_usd for outcome in scenario_rows
        )
        stressed_aggregate_return_fraction = (
            (stressed_total_ending_equity_usd - total_starting_equity_usd)
            / total_starting_equity_usd
            if total_starting_equity_usd > 0
            else 0.0
        )
        failing_run_count = sum(1 for outcome in scenario_rows if outcome.verdict == "fail")
        passing_run_count = len(scenario_rows) - failing_run_count
        aggregate_risk_policy_outcomes.append(
            MatrixComparisonAggregateRiskPolicyOutcome(
                scenario_id=scenario_id,
                risk_scale_multiplier=scale_multiplier,
                stressed_total_net_realized_pnl_usd=stressed_total_net_realized_pnl_usd,
                stressed_total_ending_equity_usd=stressed_total_ending_equity_usd,
                stressed_aggregate_return_fraction=stressed_aggregate_return_fraction,
                delta_total_net_realized_pnl_usd_vs_baseline=(
                    stressed_total_net_realized_pnl_usd - total_net_realized_pnl_usd
                ),
                delta_aggregate_return_fraction_vs_baseline=(
                    stressed_aggregate_return_fraction - aggregate_return_fraction
                ),
                failing_run_count=failing_run_count,
                passing_run_count=passing_run_count,
                verdict="pass" if stressed_aggregate_return_fraction >= 0 else "fail",
            )
        )
    aggregate_first_fail_scenario_id = (
        "baseline"
        if aggregate_baseline_robustness_verdict == "fail"
        else next(
            (
                outcome.scenario_id
                for outcome in aggregate_stress_outcomes
                if outcome.verdict == "fail"
            ),
            None,
        )
    )
    aggregate_first_fail_additional_cost_slippage_bps = (
        0.0
        if aggregate_first_fail_scenario_id == "baseline"
        else (
            float(scenario_bps[aggregate_first_fail_scenario_id])
            if aggregate_first_fail_scenario_id is not None
            and aggregate_first_fail_scenario_id in scenario_bps
            else None
        )
    )
    failure_order_rows = sorted(
        [row for row in rows if row.first_fail_scenario_id is not None],
        key=lambda row: (_fail_threshold_bps(row), row.run_id),
    )
    first_failure_run_ids = (
        [
            row.run_id
            for row in failure_order_rows
            if _fail_threshold_bps(row) == _fail_threshold_bps(failure_order_rows[0])
        ]
        if failure_order_rows
        else []
    )
    max_stress_total_net_pnl_drag_usd = fsum(row.max_stress_net_pnl_drag_usd for row in rows)
    risk_policy_order = {
        scenario_id: index
        for index, (scenario_id, _) in enumerate(MATRIX_RISK_POLICY_SCENARIOS, start=1)
    }
    risk_failure_candidates = [
        row for row in rows if row.risk_policy_first_fail_scenario_id is not None
    ]
    first_policy_failure_row = min(
        risk_failure_candidates,
        key=lambda row: (
            risk_policy_order.get(
                str(row.risk_policy_first_fail_scenario_id),
                len(MATRIX_RISK_POLICY_SCENARIOS) + 1,
            ),
            row.run_id,
        ),
        default=None,
    )
    risk_policy_first_fail_scenario_id = (
        first_policy_failure_row.risk_policy_first_fail_scenario_id
        if first_policy_failure_row is not None
        else None
    )
    risk_policy_first_fail_run_id = (
        first_policy_failure_row.run_id if first_policy_failure_row is not None else None
    )
    risk_policy_most_sensitive_row = max(
        rows,
        key=lambda row: (
            row.risk_policy_sensitivity_span_return_fraction,
            row.risk_policy_sensitivity_span_net_pnl_usd,
            row.run_id,
        ),
        default=None,
    )
    risk_policy_pass_run_count = sum(
        1 for row in rows if row.risk_policy_robustness_verdict == "pass"
    )
    risk_policy_fail_run_count = len(rows) - risk_policy_pass_run_count
    risk_policy_robustness_verdict: Literal["pass", "fail"] = (
        "pass" if risk_policy_fail_run_count == 0 else "fail"
    )
    risk_policy_narrow_dependence_run_ids = sorted(
        row.run_id for row in rows if row.risk_policy_is_narrow_dependence
    )
    aggregate_failure_mode_outcomes: list[MatrixComparisonAggregateFailureModeOutcome] = []
    for (
        scenario_id,
        reduced_capture_multiplier,
        delayed_haircut_fraction,
    ) in MATRIX_FAILURE_MODE_SCENARIOS:
        failure_mode_scenario_rows = [
            next(
                outcome
                for outcome in row.failure_mode_outcomes
                if outcome.scenario_id == scenario_id
            )
            for row in rows
        ]
        stressed_total_net_realized_pnl_usd = fsum(
            outcome.stressed_net_realized_pnl_usd for outcome in failure_mode_scenario_rows
        )
        stressed_total_ending_equity_usd = fsum(
            outcome.stressed_ending_equity_usd for outcome in failure_mode_scenario_rows
        )
        stressed_aggregate_return_fraction = (
            (stressed_total_ending_equity_usd - total_starting_equity_usd)
            / total_starting_equity_usd
            if total_starting_equity_usd > 0
            else 0.0
        )
        failing_run_count = sum(
            1 for outcome in failure_mode_scenario_rows if outcome.verdict == "fail"
        )
        passing_run_count = len(failure_mode_scenario_rows) - failing_run_count
        aggregate_failure_mode_outcomes.append(
            MatrixComparisonAggregateFailureModeOutcome(
                scenario_id=scenario_id,
                reduced_fill_capture_multiplier=reduced_capture_multiplier,
                delayed_opportunity_haircut_fraction=delayed_haircut_fraction,
                stressed_total_net_realized_pnl_usd=stressed_total_net_realized_pnl_usd,
                stressed_total_ending_equity_usd=stressed_total_ending_equity_usd,
                stressed_aggregate_return_fraction=stressed_aggregate_return_fraction,
                margin_loss_total_net_pnl_usd=max(
                    total_net_realized_pnl_usd - stressed_total_net_realized_pnl_usd,
                    0.0,
                ),
                margin_loss_aggregate_return_fraction=max(
                    aggregate_return_fraction - stressed_aggregate_return_fraction,
                    0.0,
                ),
                failing_run_count=failing_run_count,
                passing_run_count=passing_run_count,
                verdict="pass" if stressed_aggregate_return_fraction >= 0 else "fail",
            )
        )
    failure_mode_pass_run_count = sum(
        1 for row in rows if row.failure_mode_robustness_verdict == "pass"
    )
    failure_mode_fail_run_count = len(rows) - failure_mode_pass_run_count
    failure_mode_aggregate_robustness_verdict: Literal["pass", "fail"] = (
        "pass" if failure_mode_fail_run_count == 0 else "fail"
    )
    failure_mode_failure_candidates = [
        row for row in rows if row.failure_mode_first_fail_scenario_id is not None
    ]
    failure_mode_first_failure_row = min(
        failure_mode_failure_candidates,
        key=lambda row: (_failure_mode_threshold_order(row), row.run_id),
        default=None,
    )
    failure_mode_first_fail_scenario_id = (
        failure_mode_first_failure_row.failure_mode_first_fail_scenario_id
        if failure_mode_first_failure_row is not None
        else None
    )
    failure_mode_first_fail_run_id = (
        failure_mode_first_failure_row.run_id
        if failure_mode_first_failure_row is not None
        else None
    )
    failure_mode_failure_order_rows = sorted(
        [row for row in rows if row.failure_mode_first_fail_scenario_id is not None],
        key=lambda row: (_failure_mode_threshold_order(row), row.run_id),
    )
    failure_mode_most_sensitive_row = max(
        rows,
        key=lambda row: (
            row.failure_mode_sensitivity_span_return_fraction,
            row.failure_mode_sensitivity_span_net_pnl_usd,
            row.run_id,
        ),
        default=None,
    )
    winner_row = max(rows, key=lambda row: (row.return_fraction, row.run_id), default=None)
    walk_forward_slice_ids = sorted(
        {slice_.slice_id for row in rows for slice_ in row.walk_forward_slices},
        key=lambda slice_id: (
            int(slice_id.split("_")[1]) if slice_id.startswith("window_") else float("inf"),
            slice_id,
        ),
    )
    aggregate_walk_forward_slice_outcomes: list[
        MatrixComparisonAggregateWalkForwardSliceOutcome
    ] = []
    for slice_id in walk_forward_slice_ids:
        slice_samples = [
            slice_
            for row in rows
            for slice_ in row.walk_forward_slices
            if slice_.slice_id == slice_id
        ]
        failing_run_count = sum(1 for sample in slice_samples if sample.verdict == "fail")
        passing_run_count = sum(1 for sample in slice_samples if sample.verdict == "pass")
        total_slice_net_pnl_delta_usd = fsum(
            sample.slice_net_pnl_delta_usd for sample in slice_samples
        )
        aggregate_walk_forward_slice_outcomes.append(
            MatrixComparisonAggregateWalkForwardSliceOutcome(
                slice_id=slice_id,
                slice_index=(
                    slice_samples[0].slice_index if slice_samples else int(slice_id.split("_")[1])
                ),
                total_slice_net_pnl_delta_usd=total_slice_net_pnl_delta_usd,
                average_slice_net_pnl_delta_usd=(
                    total_slice_net_pnl_delta_usd / len(slice_samples) if slice_samples else 0.0
                ),
                failing_run_count=failing_run_count,
                passing_run_count=passing_run_count,
                verdict="pass" if failing_run_count == 0 else "fail",
            )
        )
    walk_forward_pass_run_count = sum(
        1 for row in rows if row.walk_forward_robustness_verdict == "pass"
    )
    walk_forward_fail_run_count = len(rows) - walk_forward_pass_run_count
    walk_forward_most_consistent_row = min(
        rows,
        key=lambda row: (
            row.walk_forward_consistency_stddev_net_pnl_usd,
            row.walk_forward_consistency_range_net_pnl_usd,
            row.run_id,
        ),
        default=None,
    )
    walk_forward_worst_slice_row = min(
        rows,
        key=lambda row: (row.walk_forward_worst_slice_net_pnl_delta_usd, row.run_id),
        default=None,
    )
    walk_forward_aggregate_robustness_verdict: Literal["pass", "fail"] = (
        "pass" if walk_forward_fail_run_count == 0 else "fail"
    )
    aggregate = MatrixComparisonAggregate(
        run_count=len(rows),
        total_proposal_count=sum(row.proposal_count for row in rows),
        total_halt_count=sum(row.halt_count for row in rows),
        total_order_reject_count=sum(row.order_reject_count for row in rows),
        total_fill_event_count=sum(row.fill_event_count for row in rows),
        total_partial_fill_intent_count=sum(row.partial_fill_intent_count for row in rows),
        total_alert_count=sum(row.alert_count for row in rows),
        total_ledger_row_count=sum(row.ledger_row_count for row in rows),
        total_starting_equity_usd=total_starting_equity_usd,
        total_net_realized_pnl_usd=total_net_realized_pnl_usd,
        total_ending_unrealized_pnl_usd=fsum(row.ending_unrealized_pnl_usd for row in rows),
        total_ending_equity_usd=total_ending_equity_usd,
        aggregate_return_fraction=aggregate_return_fraction,
        baseline_robustness_verdict=aggregate_baseline_robustness_verdict,
        stress_outcomes=aggregate_stress_outcomes,
        robustness_verdict=(
            "pass"
            if aggregate_baseline_robustness_verdict == "pass"
            and all(outcome.verdict == "pass" for outcome in aggregate_stress_outcomes)
            else "fail"
        ),
        first_fail_scenario_id=aggregate_first_fail_scenario_id,
        first_fail_additional_cost_slippage_bps=aggregate_first_fail_additional_cost_slippage_bps,
        first_failure_run_ids=first_failure_run_ids,
        failure_order_run_ids=[row.run_id for row in failure_order_rows],
        max_stress_scenario_id=max_stress_scenario_id,
        max_stress_additional_cost_slippage_bps=max_stress_bps,
        max_stress_total_net_pnl_drag_usd=max_stress_total_net_pnl_drag_usd,
        stress_delta_total_net_realized_pnl_usd_by_scenario={
            outcome.scenario_id: outcome.delta_total_net_realized_pnl_usd_vs_baseline
            for outcome in aggregate_stress_outcomes
        },
        stress_delta_aggregate_return_fraction_by_scenario={
            outcome.scenario_id: outcome.delta_aggregate_return_fraction_vs_baseline
            for outcome in aggregate_stress_outcomes
        },
        risk_policy_outcomes=aggregate_risk_policy_outcomes,
        risk_policy_robustness_verdict=risk_policy_robustness_verdict,
        risk_policy_pass_run_count=risk_policy_pass_run_count,
        risk_policy_fail_run_count=risk_policy_fail_run_count,
        risk_policy_first_fail_scenario_id=risk_policy_first_fail_scenario_id,
        risk_policy_first_fail_run_id=risk_policy_first_fail_run_id,
        risk_policy_most_sensitive_run_id=(
            risk_policy_most_sensitive_row.run_id
            if risk_policy_most_sensitive_row is not None
            else None
        ),
        risk_policy_winner_run_id=(winner_row.run_id if winner_row is not None else None),
        risk_policy_winner_robustness_verdict=(
            winner_row.risk_policy_robustness_verdict if winner_row is not None else "fail"
        ),
        risk_policy_narrow_dependence_run_ids=risk_policy_narrow_dependence_run_ids,
        risk_policy_narrow_dependence_count=len(risk_policy_narrow_dependence_run_ids),
        failure_mode_outcomes=aggregate_failure_mode_outcomes,
        failure_mode_aggregate_robustness_verdict=failure_mode_aggregate_robustness_verdict,
        failure_mode_pass_run_count=failure_mode_pass_run_count,
        failure_mode_fail_run_count=failure_mode_fail_run_count,
        failure_mode_first_fail_scenario_id=failure_mode_first_fail_scenario_id,
        failure_mode_first_fail_run_id=failure_mode_first_fail_run_id,
        failure_mode_failure_order_run_ids=[row.run_id for row in failure_mode_failure_order_rows],
        failure_mode_safest_run_id=(
            failure_mode_resilience_order[0].run_id if failure_mode_resilience_order else None
        ),
        failure_mode_most_sensitive_run_id=(
            failure_mode_most_sensitive_row.run_id
            if failure_mode_most_sensitive_row is not None
            else None
        ),
        failure_mode_winner_run_id=(winner_row.run_id if winner_row is not None else None),
        failure_mode_winner_robustness_verdict=(
            winner_row.failure_mode_robustness_verdict if winner_row is not None else "fail"
        ),
        walk_forward_slice_outcomes=aggregate_walk_forward_slice_outcomes,
        walk_forward_pass_run_count=walk_forward_pass_run_count,
        walk_forward_fail_run_count=walk_forward_fail_run_count,
        walk_forward_most_consistent_run_id=(
            walk_forward_most_consistent_row.run_id
            if walk_forward_most_consistent_row is not None
            else None
        ),
        walk_forward_worst_slice_run_id=(
            walk_forward_worst_slice_row.run_id
            if walk_forward_worst_slice_row is not None
            else None
        ),
        walk_forward_worst_slice_id=(
            walk_forward_worst_slice_row.walk_forward_worst_slice_id
            if walk_forward_worst_slice_row is not None
            else None
        ),
        walk_forward_winner_run_id=(winner_row.run_id if winner_row is not None else None),
        walk_forward_winner_robustness_verdict=(
            winner_row.walk_forward_robustness_verdict if winner_row is not None else "fail"
        ),
        walk_forward_aggregate_robustness_verdict=walk_forward_aggregate_robustness_verdict,
        passed_run_count=sum(1 for row in rows if row.robustness_verdict == "pass"),
        failed_run_count=sum(1 for row in rows if row.robustness_verdict == "fail"),
    )

    best_return_row = max(rows, key=lambda row: (row.return_fraction, row.run_id), default=None)
    worst_return_row = min(rows, key=lambda row: (row.return_fraction, row.run_id), default=None)
    highest_ending_equity_row = max(
        rows,
        key=lambda row: (row.ending_equity_usd, row.run_id),
        default=None,
    )
    lowest_ending_equity_row = min(
        rows,
        key=lambda row: (row.ending_equity_usd, row.run_id),
        default=None,
    )
    failure_candidates = [row for row in rows if row.first_fail_scenario_id is not None]
    first_failure_row = min(
        failure_candidates,
        key=lambda row: (_fail_threshold_bps(row), row.run_id),
        default=None,
    )
    first_failure_mode_failure_row = min(
        failure_mode_failure_candidates,
        key=lambda row: (_failure_mode_threshold_order(row), row.run_id),
        default=None,
    )

    return MatrixComparison(
        matrix_run_id=manifest.matrix_run_id,
        row_count=len(rows),
        rows=rows,
        aggregate=aggregate,
        rankings=MatrixComparisonRanking(
            best_return_run_id=best_return_row.run_id if best_return_row is not None else None,
            worst_return_run_id=worst_return_row.run_id if worst_return_row is not None else None,
            highest_ending_equity_run_id=(
                highest_ending_equity_row.run_id if highest_ending_equity_row is not None else None
            ),
            lowest_ending_equity_run_id=(
                lowest_ending_equity_row.run_id if lowest_ending_equity_row is not None else None
            ),
            first_robustness_failure_run_id=(
                first_failure_row.run_id if first_failure_row is not None else None
            ),
            first_robustness_failure_scenario_id=(
                first_failure_row.first_fail_scenario_id if first_failure_row is not None else None
            ),
            most_fragile_run_id=fragility_order[0].run_id if fragility_order else None,
            most_resilient_run_id=resilience_order[0].run_id if resilience_order else None,
            fragility_order_run_ids=[row.run_id for row in fragility_order],
            resilience_order_run_ids=[row.run_id for row in resilience_order],
            most_consistent_walk_forward_run_id=(
                walk_forward_most_consistent_row.run_id
                if walk_forward_most_consistent_row is not None
                else None
            ),
            worst_walk_forward_slice_run_id=(
                walk_forward_worst_slice_row.run_id
                if walk_forward_worst_slice_row is not None
                else None
            ),
            worst_walk_forward_slice_id=(
                walk_forward_worst_slice_row.walk_forward_worst_slice_id
                if walk_forward_worst_slice_row is not None
                else None
            ),
            winner_walk_forward_robustness_verdict=(
                winner_row.walk_forward_robustness_verdict if winner_row is not None else "fail"
            ),
            most_policy_sensitive_run_id=(
                risk_policy_most_sensitive_row.run_id
                if risk_policy_most_sensitive_row is not None
                else None
            ),
            first_policy_failure_run_id=(
                first_policy_failure_row.run_id if first_policy_failure_row is not None else None
            ),
            first_policy_failure_scenario_id=(
                first_policy_failure_row.risk_policy_first_fail_scenario_id
                if first_policy_failure_row is not None
                else None
            ),
            winner_policy_robustness_verdict=(
                winner_row.risk_policy_robustness_verdict if winner_row is not None else "fail"
            ),
            first_failure_mode_failure_run_id=(
                first_failure_mode_failure_row.run_id
                if first_failure_mode_failure_row is not None
                else None
            ),
            first_failure_mode_failure_scenario_id=(
                first_failure_mode_failure_row.failure_mode_first_fail_scenario_id
                if first_failure_mode_failure_row is not None
                else None
            ),
            most_failure_mode_fragile_run_id=(
                failure_mode_fragility_order[0].run_id if failure_mode_fragility_order else None
            ),
            most_failure_mode_resilient_run_id=(
                failure_mode_resilience_order[0].run_id if failure_mode_resilience_order else None
            ),
            failure_mode_fragility_order_run_ids=[
                row.run_id for row in failure_mode_fragility_order
            ],
            failure_mode_resilience_order_run_ids=[
                row.run_id for row in failure_mode_resilience_order
            ],
            most_failure_mode_sensitive_run_id=(
                failure_mode_most_sensitive_row.run_id
                if failure_mode_most_sensitive_row is not None
                else None
            ),
            winner_failure_mode_robustness_verdict=(
                winner_row.failure_mode_robustness_verdict if winner_row is not None else "fail"
            ),
        ),
    )


def _write_matrix_comparison(manifest: PaperRunMatrixManifest) -> Path:
    comparison = _build_matrix_comparison(manifest)
    comparison_path = Path(manifest.matrix_comparison_path)
    comparison_path.write_text(
        json.dumps(comparison.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return comparison_path


def _build_matrix_trade_ledger(manifest: PaperRunMatrixManifest) -> MatrixTradeLedger:
    rows: list[MatrixTradeLedgerEntry] = []

    for entry in manifest.entries:
        summary = json.loads(Path(entry.summary_path).read_text(encoding="utf-8"))
        trade_ledger = TradeLedger.model_validate(
            json.loads(Path(summary["trade_ledger_path"]).read_text(encoding="utf-8"))
        )
        if trade_ledger.row_count == 0:
            rows.append(
                MatrixTradeLedgerEntry(
                    matrix_run_id=manifest.matrix_run_id,
                    run_id=entry.run_id,
                    ending_status="no_signal",
                )
            )
            continue

        rows.extend(
            MatrixTradeLedgerEntry(
                matrix_run_id=manifest.matrix_run_id,
                run_id=entry.run_id,
                proposal_id=ledger_row.proposal_id,
                symbol=ledger_row.symbol,
                side=ledger_row.side,
                strategy_id=ledger_row.strategy_id,
                intent_id=ledger_row.intent_id,
                filled_size=ledger_row.filled_size,
                average_fill_price=ledger_row.average_fill_price,
                total_fee_usd=ledger_row.total_fee_usd,
                gross_realized_pnl_usd=ledger_row.gross_realized_pnl_usd,
                net_realized_pnl_usd=ledger_row.net_realized_pnl_usd,
                ending_status=ledger_row.ending_status,
            )
            for ledger_row in trade_ledger.rows
        )

    return MatrixTradeLedger(
        matrix_run_id=manifest.matrix_run_id,
        row_count=len(rows),
        rows=rows,
    )


def _write_matrix_trade_ledger(manifest: PaperRunMatrixManifest) -> Path:
    trade_ledger = _build_matrix_trade_ledger(manifest)
    trade_ledger_path = Path(manifest.matrix_trade_ledger_path)
    trade_ledger_path.write_text(
        json.dumps(trade_ledger.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return trade_ledger_path


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
        f"matrix_comparison_path: {_relative_matrix_comparison_path(manifest.matrix_run_id)}",
        f"matrix_trade_ledger_path: {_relative_matrix_trade_ledger_path(manifest.matrix_run_id)}",
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
    comparison = _build_matrix_comparison(manifest)
    comparison_rows_by_run_id = {row.run_id: row for row in comparison.rows}
    lines.extend(
        [
            "",
            "## Matrix Cost/Slippage Robustness Gate",
            f"baseline_robustness_verdict: {comparison.aggregate.baseline_robustness_verdict}",
            f"robustness_verdict: {comparison.aggregate.robustness_verdict}",
            f"first_fail_scenario_id: {comparison.aggregate.first_fail_scenario_id}",
            "first_fail_additional_cost_slippage_bps: "
            f"{comparison.aggregate.first_fail_additional_cost_slippage_bps}",
            f"passed_run_count: {comparison.aggregate.passed_run_count}",
            f"failed_run_count: {comparison.aggregate.failed_run_count}",
            "first_robustness_failure_run_id: "
            f"{comparison.rankings.first_robustness_failure_run_id}",
            "first_robustness_failure_scenario_id: "
            f"{comparison.rankings.first_robustness_failure_scenario_id}",
            f"first_failure_run_ids: {','.join(comparison.aggregate.first_failure_run_ids)}",
            f"failure_order_run_ids: {','.join(comparison.aggregate.failure_order_run_ids)}",
            f"most_fragile_run_id: {comparison.rankings.most_fragile_run_id}",
            f"most_resilient_run_id: {comparison.rankings.most_resilient_run_id}",
            f"fragility_order_run_ids: {','.join(comparison.rankings.fragility_order_run_ids)}",
            f"resilience_order_run_ids: {','.join(comparison.rankings.resilience_order_run_ids)}",
            f"max_stress_scenario_id: {comparison.aggregate.max_stress_scenario_id}",
            "max_stress_additional_cost_slippage_bps: "
            f"{_format_float(comparison.aggregate.max_stress_additional_cost_slippage_bps)}",
            "max_stress_total_net_pnl_drag_usd: "
            f"{_format_float(comparison.aggregate.max_stress_total_net_pnl_drag_usd)}",
        ]
    )
    for aggregate_outcome in comparison.aggregate.stress_outcomes:
        lines.extend(
            [
                (
                    "aggregate_stress_"
                    f"{aggregate_outcome.scenario_id}_additional_cost_slippage_bps: "
                    f"{_format_float(aggregate_outcome.additional_cost_slippage_bps)}"
                ),
                (
                    f"aggregate_stress_{aggregate_outcome.scenario_id}_incremental_cost_usd: "
                    f"{_format_float(aggregate_outcome.incremental_cost_usd)}"
                ),
                (
                    "aggregate_stress_"
                    f"{aggregate_outcome.scenario_id}_stressed_total_net_realized_pnl_usd: "
                    f"{_format_float(aggregate_outcome.stressed_total_net_realized_pnl_usd)}"
                ),
                (
                    f"aggregate_stress_{aggregate_outcome.scenario_id}_"
                    f"stressed_aggregate_return_fraction: "
                    f"{_format_float(aggregate_outcome.stressed_aggregate_return_fraction)}"
                ),
                (
                    f"aggregate_stress_{aggregate_outcome.scenario_id}_failing_run_count: "
                    f"{aggregate_outcome.failing_run_count}"
                ),
                (
                    "aggregate_stress_"
                    f"{aggregate_outcome.scenario_id}_"
                    "delta_total_net_realized_pnl_usd_vs_baseline: "
                    f"{_format_float(aggregate_outcome.delta_total_net_realized_pnl_usd_vs_baseline)}"
                ),
                (
                    "aggregate_stress_"
                    f"{aggregate_outcome.scenario_id}_delta_aggregate_return_fraction_vs_baseline: "
                    f"{_format_float(aggregate_outcome.delta_aggregate_return_fraction_vs_baseline)}"
                ),
                (
                    f"aggregate_stress_{aggregate_outcome.scenario_id}_verdict: "
                    f"{aggregate_outcome.verdict}"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Matrix Risk Policy Sweep Robustness",
            "risk_policy_robustness_verdict: "
            f"{comparison.aggregate.risk_policy_robustness_verdict}",
            f"risk_policy_pass_run_count: {comparison.aggregate.risk_policy_pass_run_count}",
            f"risk_policy_fail_run_count: {comparison.aggregate.risk_policy_fail_run_count}",
            "risk_policy_first_fail_scenario_id: "
            f"{comparison.aggregate.risk_policy_first_fail_scenario_id}",
            f"risk_policy_first_fail_run_id: {comparison.aggregate.risk_policy_first_fail_run_id}",
            "risk_policy_most_sensitive_run_id: "
            f"{comparison.aggregate.risk_policy_most_sensitive_run_id}",
            f"risk_policy_winner_run_id: {comparison.aggregate.risk_policy_winner_run_id}",
            "risk_policy_winner_robustness_verdict: "
            f"{comparison.aggregate.risk_policy_winner_robustness_verdict}",
            "winner_policy_robustness_verdict: "
            f"{comparison.rankings.winner_policy_robustness_verdict}",
            "most_policy_sensitive_run_id: " f"{comparison.rankings.most_policy_sensitive_run_id}",
            f"first_policy_failure_run_id: {comparison.rankings.first_policy_failure_run_id}",
            "first_policy_failure_scenario_id: "
            f"{comparison.rankings.first_policy_failure_scenario_id}",
            "risk_policy_narrow_dependence_count: "
            f"{comparison.aggregate.risk_policy_narrow_dependence_count}",
            "risk_policy_narrow_dependence_run_ids: "
            f"{','.join(comparison.aggregate.risk_policy_narrow_dependence_run_ids)}",
        ]
    )
    for aggregate_risk_outcome in comparison.aggregate.risk_policy_outcomes:
        lines.extend(
            [
                (
                    f"aggregate_risk_{aggregate_risk_outcome.scenario_id}_risk_scale_multiplier: "
                    f"{_format_float(aggregate_risk_outcome.risk_scale_multiplier)}"
                ),
                (
                    f"aggregate_risk_{aggregate_risk_outcome.scenario_id}_"
                    f"stressed_total_net_realized_pnl_usd: "
                    f"{_format_float(aggregate_risk_outcome.stressed_total_net_realized_pnl_usd)}"
                ),
                (
                    f"aggregate_risk_{aggregate_risk_outcome.scenario_id}_"
                    f"stressed_aggregate_return_fraction: "
                    f"{_format_float(aggregate_risk_outcome.stressed_aggregate_return_fraction)}"
                ),
                (
                    f"aggregate_risk_{aggregate_risk_outcome.scenario_id}_"
                    f"delta_total_net_realized_pnl_usd_vs_baseline: "
                    f"{_format_float(aggregate_risk_outcome.delta_total_net_realized_pnl_usd_vs_baseline)}"
                ),
                (
                    f"aggregate_risk_{aggregate_risk_outcome.scenario_id}_"
                    f"delta_aggregate_return_fraction_vs_baseline: "
                    f"{_format_float(aggregate_risk_outcome.delta_aggregate_return_fraction_vs_baseline)}"
                ),
                (
                    f"aggregate_risk_{aggregate_risk_outcome.scenario_id}_"
                    f"failing_run_count: {aggregate_risk_outcome.failing_run_count}"
                ),
                (
                    f"aggregate_risk_{aggregate_risk_outcome.scenario_id}_"
                    f"passing_run_count: {aggregate_risk_outcome.passing_run_count}"
                ),
                (
                    f"aggregate_risk_{aggregate_risk_outcome.scenario_id}_verdict: "
                    f"{aggregate_risk_outcome.verdict}"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Matrix Failure-Mode Robustness Sweep",
            "failure_mode_aggregate_robustness_verdict: "
            f"{comparison.aggregate.failure_mode_aggregate_robustness_verdict}",
            f"failure_mode_pass_run_count: {comparison.aggregate.failure_mode_pass_run_count}",
            f"failure_mode_fail_run_count: {comparison.aggregate.failure_mode_fail_run_count}",
            "failure_mode_first_fail_scenario_id: "
            f"{comparison.aggregate.failure_mode_first_fail_scenario_id}",
            (
                "failure_mode_first_fail_run_id: "
                f"{comparison.aggregate.failure_mode_first_fail_run_id}"
            ),
            "failure_mode_failure_order_run_ids: "
            f"{','.join(comparison.aggregate.failure_mode_failure_order_run_ids)}",
            f"failure_mode_safest_run_id: {comparison.aggregate.failure_mode_safest_run_id}",
            "failure_mode_most_sensitive_run_id: "
            f"{comparison.aggregate.failure_mode_most_sensitive_run_id}",
            f"failure_mode_winner_run_id: {comparison.aggregate.failure_mode_winner_run_id}",
            "failure_mode_winner_robustness_verdict: "
            f"{comparison.aggregate.failure_mode_winner_robustness_verdict}",
            "first_failure_mode_failure_run_id: "
            f"{comparison.rankings.first_failure_mode_failure_run_id}",
            "first_failure_mode_failure_scenario_id: "
            f"{comparison.rankings.first_failure_mode_failure_scenario_id}",
            "most_failure_mode_fragile_run_id: "
            f"{comparison.rankings.most_failure_mode_fragile_run_id}",
            "most_failure_mode_resilient_run_id: "
            f"{comparison.rankings.most_failure_mode_resilient_run_id}",
            "failure_mode_fragility_order_run_ids: "
            f"{','.join(comparison.rankings.failure_mode_fragility_order_run_ids)}",
            "failure_mode_resilience_order_run_ids: "
            f"{','.join(comparison.rankings.failure_mode_resilience_order_run_ids)}",
            "most_failure_mode_sensitive_run_id: "
            f"{comparison.rankings.most_failure_mode_sensitive_run_id}",
            "winner_failure_mode_robustness_verdict: "
            f"{comparison.rankings.winner_failure_mode_robustness_verdict}",
        ]
    )
    for aggregate_failure_outcome in comparison.aggregate.failure_mode_outcomes:
        lines.extend(
            [
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    "reduced_fill_capture_multiplier: "
                    f"{_format_float(aggregate_failure_outcome.reduced_fill_capture_multiplier)}"
                ),
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    "delayed_opportunity_haircut_fraction: "
                    f"{_format_float(aggregate_failure_outcome.delayed_opportunity_haircut_fraction)}"
                ),
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    "stressed_total_net_realized_pnl_usd: "
                    f"{_format_float(aggregate_failure_outcome.stressed_total_net_realized_pnl_usd)}"
                ),
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    "stressed_aggregate_return_fraction: "
                    f"{_format_float(aggregate_failure_outcome.stressed_aggregate_return_fraction)}"
                ),
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    "margin_loss_total_net_pnl_usd: "
                    f"{_format_float(aggregate_failure_outcome.margin_loss_total_net_pnl_usd)}"
                ),
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    "margin_loss_aggregate_return_fraction: "
                    f"{_format_float(aggregate_failure_outcome.margin_loss_aggregate_return_fraction)}"
                ),
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    f"failing_run_count: {aggregate_failure_outcome.failing_run_count}"
                ),
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    f"passing_run_count: {aggregate_failure_outcome.passing_run_count}"
                ),
                (
                    f"aggregate_failure_{aggregate_failure_outcome.scenario_id}_"
                    f"verdict: {aggregate_failure_outcome.verdict}"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Matrix Walk-Forward Regime Robustness",
            "walk_forward_aggregate_robustness_verdict: "
            f"{comparison.aggregate.walk_forward_aggregate_robustness_verdict}",
            f"walk_forward_pass_run_count: {comparison.aggregate.walk_forward_pass_run_count}",
            f"walk_forward_fail_run_count: {comparison.aggregate.walk_forward_fail_run_count}",
            "walk_forward_most_consistent_run_id: "
            f"{comparison.aggregate.walk_forward_most_consistent_run_id}",
            "walk_forward_worst_slice_run_id: "
            f"{comparison.aggregate.walk_forward_worst_slice_run_id}",
            f"walk_forward_worst_slice_id: {comparison.aggregate.walk_forward_worst_slice_id}",
            f"walk_forward_winner_run_id: {comparison.aggregate.walk_forward_winner_run_id}",
            "walk_forward_winner_robustness_verdict: "
            f"{comparison.aggregate.walk_forward_winner_robustness_verdict}",
            "winner_walk_forward_robustness_verdict: "
            f"{comparison.rankings.winner_walk_forward_robustness_verdict}",
            "most_consistent_walk_forward_run_id: "
            f"{comparison.rankings.most_consistent_walk_forward_run_id}",
            "worst_walk_forward_slice_run_id: "
            f"{comparison.rankings.worst_walk_forward_slice_run_id}",
            f"worst_walk_forward_slice_id: {comparison.rankings.worst_walk_forward_slice_id}",
        ]
    )
    for slice_outcome in comparison.aggregate.walk_forward_slice_outcomes:
        lines.extend(
            [
                (
                    f"walk_forward_slice_{slice_outcome.slice_id}_"
                    "total_slice_net_pnl_delta_usd: "
                    f"{_format_float(slice_outcome.total_slice_net_pnl_delta_usd)}"
                ),
                (
                    f"walk_forward_slice_{slice_outcome.slice_id}_"
                    "average_slice_net_pnl_delta_usd: "
                    f"{_format_float(slice_outcome.average_slice_net_pnl_delta_usd)}"
                ),
                (
                    f"walk_forward_slice_{slice_outcome.slice_id}_"
                    f"failing_run_count: {slice_outcome.failing_run_count}"
                ),
                (
                    f"walk_forward_slice_{slice_outcome.slice_id}_"
                    f"passing_run_count: {slice_outcome.passing_run_count}"
                ),
                (
                    f"walk_forward_slice_{slice_outcome.slice_id}_"
                    f"verdict: {slice_outcome.verdict}"
                ),
            ]
        )
    lines.extend(
        [
            "",
            "## Per-Run Details",
        ]
    )

    for entry, scorecard, pnl, alert_count, kill_switch_activations in replay_runs:
        comparison_row = comparison_rows_by_run_id[entry.run_id]
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
                f"baseline_robustness_verdict: {comparison_row.baseline_robustness_verdict}",
                f"robustness_verdict: {comparison_row.robustness_verdict}",
                f"first_fail_scenario_id: {comparison_row.first_fail_scenario_id}",
                "first_fail_additional_cost_slippage_bps: "
                f"{comparison_row.first_fail_additional_cost_slippage_bps}",
                "risk_policy_robustness_verdict: "
                f"{comparison_row.risk_policy_robustness_verdict}",
                "risk_policy_first_fail_scenario_id: "
                f"{comparison_row.risk_policy_first_fail_scenario_id}",
                "risk_policy_first_fail_scale_multiplier: "
                f"{comparison_row.risk_policy_first_fail_scale_multiplier}",
                "risk_policy_pass_scenario_count: "
                f"{comparison_row.risk_policy_pass_scenario_count}",
                "risk_policy_fail_scenario_count: "
                f"{comparison_row.risk_policy_fail_scenario_count}",
                "risk_policy_sensitivity_span_net_pnl_usd: "
                f"{_format_float(comparison_row.risk_policy_sensitivity_span_net_pnl_usd)}",
                "risk_policy_sensitivity_span_return_fraction: "
                f"{_format_float(comparison_row.risk_policy_sensitivity_span_return_fraction)}",
                "risk_policy_most_adverse_scenario_id: "
                f"{comparison_row.risk_policy_most_adverse_scenario_id}",
                "risk_policy_most_adverse_delta_net_pnl_usd: "
                f"{_format_float(comparison_row.risk_policy_most_adverse_delta_net_pnl_usd)}",
                "risk_policy_is_narrow_dependence: "
                f"{comparison_row.risk_policy_is_narrow_dependence}",
                "failure_mode_robustness_verdict: "
                f"{comparison_row.failure_mode_robustness_verdict}",
                "failure_mode_first_fail_scenario_id: "
                f"{comparison_row.failure_mode_first_fail_scenario_id}",
                "failure_mode_pass_scenario_count: "
                f"{comparison_row.failure_mode_pass_scenario_count}",
                "failure_mode_fail_scenario_count: "
                f"{comparison_row.failure_mode_fail_scenario_count}",
                "failure_mode_sensitivity_span_net_pnl_usd: "
                f"{_format_float(comparison_row.failure_mode_sensitivity_span_net_pnl_usd)}",
                "failure_mode_sensitivity_span_return_fraction: "
                f"{_format_float(comparison_row.failure_mode_sensitivity_span_return_fraction)}",
                "failure_mode_most_adverse_scenario_id: "
                f"{comparison_row.failure_mode_most_adverse_scenario_id}",
                "failure_mode_most_adverse_margin_loss_net_pnl_usd: "
                f"{_format_float(comparison_row.failure_mode_most_adverse_margin_loss_net_pnl_usd)}",
                f"failure_mode_fragility_rank: {comparison_row.failure_mode_fragility_rank}",
                f"failure_mode_resilience_rank: {comparison_row.failure_mode_resilience_rank}",
                f"fragility_rank: {comparison_row.fragility_rank}",
                f"resilience_rank: {comparison_row.resilience_rank}",
                f"max_stress_scenario_id: {comparison_row.max_stress_scenario_id}",
                "max_stress_additional_cost_slippage_bps: "
                f"{_format_float(comparison_row.max_stress_additional_cost_slippage_bps)}",
                "max_stress_net_pnl_drag_usd: "
                f"{_format_float(comparison_row.max_stress_net_pnl_drag_usd)}",
                "walk_forward_robustness_verdict: "
                f"{comparison_row.walk_forward_robustness_verdict}",
                f"walk_forward_slice_count: {comparison_row.walk_forward_slice_count}",
                f"walk_forward_pass_slice_count: {comparison_row.walk_forward_pass_slice_count}",
                f"walk_forward_fail_slice_count: {comparison_row.walk_forward_fail_slice_count}",
                "walk_forward_consistency_stddev_net_pnl_usd: "
                f"{_format_float(comparison_row.walk_forward_consistency_stddev_net_pnl_usd)}",
                "walk_forward_consistency_range_net_pnl_usd: "
                f"{_format_float(comparison_row.walk_forward_consistency_range_net_pnl_usd)}",
                f"walk_forward_best_slice_id: {comparison_row.walk_forward_best_slice_id}",
                f"walk_forward_worst_slice_id: {comparison_row.walk_forward_worst_slice_id}",
                "walk_forward_best_slice_net_pnl_delta_usd: "
                f"{_format_float(comparison_row.walk_forward_best_slice_net_pnl_delta_usd)}",
                "walk_forward_worst_slice_net_pnl_delta_usd: "
                f"{_format_float(comparison_row.walk_forward_worst_slice_net_pnl_delta_usd)}",
                "walk_forward_profit_concentration_fraction: "
                f"{_format_float(comparison_row.walk_forward_profit_concentration_fraction)}",
                "walk_forward_is_profit_concentrated: "
                f"{comparison_row.walk_forward_is_profit_concentrated}",
                "",
            ]
        )
        for outcome in comparison_row.stress_outcomes:
            lines.extend(
                [
                    (
                        f"stress_{outcome.scenario_id}_additional_cost_slippage_bps: "
                        f"{_format_float(outcome.additional_cost_slippage_bps)}"
                    ),
                    (
                        f"stress_{outcome.scenario_id}_incremental_cost_usd: "
                        f"{_format_float(outcome.incremental_cost_usd)}"
                    ),
                    (
                        f"stress_{outcome.scenario_id}_stressed_net_realized_pnl_usd: "
                        f"{_format_float(outcome.stressed_net_realized_pnl_usd)}"
                    ),
                    (
                        f"stress_{outcome.scenario_id}_stressed_return_fraction: "
                        f"{_format_float(outcome.stressed_return_fraction)}"
                    ),
                    (
                        f"stress_{outcome.scenario_id}_delta_net_realized_pnl_usd_vs_baseline: "
                        f"{_format_float(outcome.delta_net_realized_pnl_usd_vs_baseline)}"
                    ),
                    (
                        f"stress_{outcome.scenario_id}_delta_return_fraction_vs_baseline: "
                        f"{_format_float(outcome.delta_return_fraction_vs_baseline)}"
                    ),
                    f"stress_{outcome.scenario_id}_verdict: {outcome.verdict}",
                    "",
                ]
            )
        for row_risk_outcome in comparison_row.risk_policy_outcomes:
            lines.extend(
                [
                    (
                        f"risk_{row_risk_outcome.scenario_id}_risk_scale_multiplier: "
                        f"{_format_float(row_risk_outcome.risk_scale_multiplier)}"
                    ),
                    (
                        f"risk_{row_risk_outcome.scenario_id}_stressed_net_realized_pnl_usd: "
                        f"{_format_float(row_risk_outcome.stressed_net_realized_pnl_usd)}"
                    ),
                    (
                        f"risk_{row_risk_outcome.scenario_id}_stressed_ending_equity_usd: "
                        f"{_format_float(row_risk_outcome.stressed_ending_equity_usd)}"
                    ),
                    (
                        f"risk_{row_risk_outcome.scenario_id}_stressed_return_fraction: "
                        f"{_format_float(row_risk_outcome.stressed_return_fraction)}"
                    ),
                    (
                        f"risk_{row_risk_outcome.scenario_id}_"
                        f"delta_net_realized_pnl_usd_vs_baseline: "
                        f"{_format_float(row_risk_outcome.delta_net_realized_pnl_usd_vs_baseline)}"
                    ),
                    (
                        f"risk_{row_risk_outcome.scenario_id}_"
                        f"delta_return_fraction_vs_baseline: "
                        f"{_format_float(row_risk_outcome.delta_return_fraction_vs_baseline)}"
                    ),
                    f"risk_{row_risk_outcome.scenario_id}_verdict: {row_risk_outcome.verdict}",
                    "",
                ]
            )
        for row_failure_outcome in comparison_row.failure_mode_outcomes:
            lines.extend(
                [
                    (
                        f"failure_{row_failure_outcome.scenario_id}_"
                        "reduced_fill_capture_multiplier: "
                        f"{_format_float(row_failure_outcome.reduced_fill_capture_multiplier)}"
                    ),
                    (
                        f"failure_{row_failure_outcome.scenario_id}_"
                        "delayed_opportunity_haircut_fraction: "
                        f"{_format_float(row_failure_outcome.delayed_opportunity_haircut_fraction)}"
                    ),
                    (
                        f"failure_{row_failure_outcome.scenario_id}_"
                        "stressed_net_realized_pnl_usd: "
                        f"{_format_float(row_failure_outcome.stressed_net_realized_pnl_usd)}"
                    ),
                    (
                        f"failure_{row_failure_outcome.scenario_id}_"
                        "stressed_ending_equity_usd: "
                        f"{_format_float(row_failure_outcome.stressed_ending_equity_usd)}"
                    ),
                    (
                        f"failure_{row_failure_outcome.scenario_id}_"
                        "stressed_return_fraction: "
                        f"{_format_float(row_failure_outcome.stressed_return_fraction)}"
                    ),
                    (
                        f"failure_{row_failure_outcome.scenario_id}_"
                        "margin_loss_net_pnl_usd: "
                        f"{_format_float(row_failure_outcome.margin_loss_net_pnl_usd)}"
                    ),
                    (
                        f"failure_{row_failure_outcome.scenario_id}_"
                        "margin_loss_return_fraction: "
                        f"{_format_float(row_failure_outcome.margin_loss_return_fraction)}"
                    ),
                    (
                        f"failure_{row_failure_outcome.scenario_id}_"
                        f"verdict: {row_failure_outcome.verdict}"
                    ),
                    "",
                ]
            )
        for run_slice in comparison_row.walk_forward_slices:
            lines.extend(
                [
                    (
                        f"walk_forward_slice_{run_slice.slice_id}_"
                        f"slice_index: {run_slice.slice_index}"
                    ),
                    (
                        f"walk_forward_slice_{run_slice.slice_id}_candle_range: "
                        f"{run_slice.start_candle_index}-{run_slice.end_candle_index}"
                    ),
                    (
                        f"walk_forward_slice_{run_slice.slice_id}_"
                        f"cumulative_ending_equity_usd: "
                        f"{_format_float(run_slice.cumulative_ending_equity_usd)}"
                    ),
                    (
                        f"walk_forward_slice_{run_slice.slice_id}_"
                        f"cumulative_return_fraction: "
                        f"{_format_float(run_slice.cumulative_return_fraction)}"
                    ),
                    (
                        f"walk_forward_slice_{run_slice.slice_id}_"
                        f"slice_net_pnl_delta_usd: "
                        f"{_format_float(run_slice.slice_net_pnl_delta_usd)}"
                    ),
                    (
                        f"walk_forward_slice_{run_slice.slice_id}_"
                        f"slice_return_fraction_delta: "
                        f"{_format_float(run_slice.slice_return_fraction_delta)}"
                    ),
                    (f"walk_forward_slice_{run_slice.slice_id}_verdict: " f"{run_slice.verdict}"),
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
        matrix_comparison_path=str(resolved_manifest_path.with_name("matrix_comparison.json")),
        matrix_trade_ledger_path=str(resolved_manifest_path.with_name("matrix_trade_ledger.json")),
        entry_count=len(entries),
        aggregate_counts=_aggregate_counts(entries),
        entries=entries,
    )
    resolved_manifest_path.write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_matrix_comparison(manifest)
    _write_matrix_trade_ledger(manifest)
    _write_operator_report(manifest)
    write_operator_run_index(settings.paths.runs_dir)
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
