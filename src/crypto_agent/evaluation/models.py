from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.enums import Side
from crypto_agent.events.envelope import EventEnvelope


class EvaluationScorecard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    event_count: int = Field(ge=0)
    proposal_count: int = Field(default=0, ge=0)
    approval_count: int = Field(default=0, ge=0)
    denial_count: int = Field(default=0, ge=0)
    halt_count: int = Field(default=0, ge=0)
    order_intent_count: int = Field(default=0, ge=0)
    orders_submitted_count: int = Field(default=0, ge=0)
    order_reject_count: int = Field(default=0, ge=0)
    fill_event_count: int = Field(default=0, ge=0)
    filled_intent_count: int = Field(default=0, ge=0)
    partial_fill_intent_count: int = Field(default=0, ge=0)
    complete_execution_count: int = Field(default=0, ge=0)
    incomplete_execution_count: int = Field(default=0, ge=0)
    average_slippage_bps: float = Field(default=0.0, ge=0)
    max_slippage_bps: float = Field(default=0.0, ge=0)
    total_fill_notional_usd: float = Field(default=0.0, ge=0)
    total_fee_usd: float = Field(default=0.0, ge=0)


class ReplayPnLSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    starting_equity_usd: float = Field(gt=0)
    gross_realized_pnl_usd: float = 0.0
    total_fee_usd: float = Field(default=0.0, ge=0)
    net_realized_pnl_usd: float = 0.0
    ending_unrealized_pnl_usd: float = 0.0
    ending_equity_usd: float
    return_fraction: float = 0.0


class TradeLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    symbol: str
    side: Side
    strategy_id: str
    intent_id: str | None = None
    filled_size: float = Field(default=0.0, ge=0)
    average_fill_price: float | None = Field(default=None, gt=0)
    total_fee_usd: float = Field(default=0.0, ge=0)
    gross_realized_pnl_usd: float = 0.0
    net_realized_pnl_usd: float = 0.0
    ending_status: Literal["filled", "partial", "rejected", "halted"]


class TradeLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    row_count: int = Field(ge=0)
    rows: list[TradeLedgerEntry] = Field(default_factory=list)


class MatrixTradeLedgerEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matrix_run_id: str
    run_id: str
    proposal_id: str | None = None
    symbol: str | None = None
    side: Side | None = None
    strategy_id: str | None = None
    intent_id: str | None = None
    filled_size: float = Field(default=0.0, ge=0)
    average_fill_price: float | None = Field(default=None, gt=0)
    total_fee_usd: float = Field(default=0.0, ge=0)
    gross_realized_pnl_usd: float = 0.0
    net_realized_pnl_usd: float = 0.0
    ending_status: Literal["filled", "partial", "rejected", "halted", "no_signal"]


class MatrixTradeLedger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matrix_run_id: str
    row_count: int = Field(ge=0)
    rows: list[MatrixTradeLedgerEntry] = Field(default_factory=list)


class MatrixComparisonRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    fixture: str
    proposal_count: int = Field(default=0, ge=0)
    halt_count: int = Field(default=0, ge=0)
    order_reject_count: int = Field(default=0, ge=0)
    fill_event_count: int = Field(default=0, ge=0)
    partial_fill_intent_count: int = Field(default=0, ge=0)
    alert_count: int = Field(default=0, ge=0)
    ledger_row_count: int = Field(default=0, ge=0)
    starting_equity_usd: float = Field(ge=0)
    net_realized_pnl_usd: float = 0.0
    ending_unrealized_pnl_usd: float = 0.0
    ending_equity_usd: float = Field(ge=0)
    return_fraction: float = 0.0
    baseline_robustness_verdict: Literal["pass", "fail"] = "pass"
    stress_outcomes: list[MatrixComparisonStressOutcome] = Field(default_factory=list)
    robustness_verdict: Literal["pass", "fail"] = "pass"
    first_fail_scenario_id: str | None = None
    first_fail_additional_cost_slippage_bps: float | None = Field(default=None, ge=0)
    max_stress_scenario_id: str | None = None
    max_stress_additional_cost_slippage_bps: float = Field(default=0.0, ge=0)
    max_stress_net_pnl_drag_usd: float = Field(default=0.0, ge=0)
    stress_delta_net_realized_pnl_usd_by_scenario: dict[str, float] = Field(default_factory=dict)
    stress_delta_return_fraction_by_scenario: dict[str, float] = Field(default_factory=dict)
    fragility_rank: int = Field(default=0, ge=0)
    resilience_rank: int = Field(default=0, ge=0)


class MatrixComparisonStressOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    additional_cost_slippage_bps: float = Field(ge=0)
    incremental_cost_usd: float = Field(default=0.0, ge=0)
    stressed_net_realized_pnl_usd: float = 0.0
    stressed_ending_equity_usd: float = Field(ge=0)
    stressed_return_fraction: float = 0.0
    delta_net_realized_pnl_usd_vs_baseline: float = 0.0
    delta_return_fraction_vs_baseline: float = 0.0
    verdict: Literal["pass", "fail"] = "pass"


class MatrixComparisonAggregate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_count: int = Field(ge=0)
    total_proposal_count: int = Field(default=0, ge=0)
    total_halt_count: int = Field(default=0, ge=0)
    total_order_reject_count: int = Field(default=0, ge=0)
    total_fill_event_count: int = Field(default=0, ge=0)
    total_partial_fill_intent_count: int = Field(default=0, ge=0)
    total_alert_count: int = Field(default=0, ge=0)
    total_ledger_row_count: int = Field(default=0, ge=0)
    total_starting_equity_usd: float = Field(default=0.0, ge=0)
    total_net_realized_pnl_usd: float = 0.0
    total_ending_unrealized_pnl_usd: float = 0.0
    total_ending_equity_usd: float = Field(default=0.0, ge=0)
    aggregate_return_fraction: float = 0.0
    baseline_robustness_verdict: Literal["pass", "fail"] = "pass"
    stress_outcomes: list[MatrixComparisonAggregateStressOutcome] = Field(default_factory=list)
    robustness_verdict: Literal["pass", "fail"] = "pass"
    first_fail_scenario_id: str | None = None
    first_fail_additional_cost_slippage_bps: float | None = Field(default=None, ge=0)
    first_failure_run_ids: list[str] = Field(default_factory=list)
    failure_order_run_ids: list[str] = Field(default_factory=list)
    max_stress_scenario_id: str | None = None
    max_stress_additional_cost_slippage_bps: float = Field(default=0.0, ge=0)
    max_stress_total_net_pnl_drag_usd: float = Field(default=0.0, ge=0)
    stress_delta_total_net_realized_pnl_usd_by_scenario: dict[str, float] = Field(
        default_factory=dict
    )
    stress_delta_aggregate_return_fraction_by_scenario: dict[str, float] = Field(
        default_factory=dict
    )
    passed_run_count: int = Field(default=0, ge=0)
    failed_run_count: int = Field(default=0, ge=0)


class MatrixComparisonAggregateStressOutcome(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    additional_cost_slippage_bps: float = Field(ge=0)
    incremental_cost_usd: float = Field(default=0.0, ge=0)
    stressed_total_net_realized_pnl_usd: float = 0.0
    stressed_total_ending_equity_usd: float = Field(ge=0)
    stressed_aggregate_return_fraction: float = 0.0
    delta_total_net_realized_pnl_usd_vs_baseline: float = 0.0
    delta_aggregate_return_fraction_vs_baseline: float = 0.0
    failing_run_count: int = Field(default=0, ge=0)
    verdict: Literal["pass", "fail"] = "pass"


class MatrixComparisonRanking(BaseModel):
    model_config = ConfigDict(extra="forbid")

    best_return_run_id: str | None = None
    worst_return_run_id: str | None = None
    highest_ending_equity_run_id: str | None = None
    lowest_ending_equity_run_id: str | None = None
    first_robustness_failure_run_id: str | None = None
    first_robustness_failure_scenario_id: str | None = None
    most_fragile_run_id: str | None = None
    most_resilient_run_id: str | None = None
    fragility_order_run_ids: list[str] = Field(default_factory=list)
    resilience_order_run_ids: list[str] = Field(default_factory=list)


class MatrixComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    matrix_run_id: str
    row_count: int = Field(ge=0)
    rows: list[MatrixComparisonRow] = Field(default_factory=list)
    aggregate: MatrixComparisonAggregate
    rankings: MatrixComparisonRanking


class OperatorSingleRunIndexEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["single_run"] = "single_run"
    order: int = Field(ge=0)
    run_id: str
    journal_path: str
    summary_path: str
    report_path: str
    trade_ledger_path: str
    paths_exist: dict[str, bool] = Field(default_factory=dict)
    all_paths_exist: bool = True


class OperatorMatrixRunIndexEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["matrix_run"] = "matrix_run"
    order: int = Field(ge=0)
    matrix_run_id: str
    manifest_path: str
    report_path: str
    matrix_trade_ledger_path: str
    matrix_comparison_path: str
    paths_exist: dict[str, bool] = Field(default_factory=dict)
    all_paths_exist: bool = True


class OperatorRunIndex(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index_path: str
    single_run_count: int = Field(ge=0)
    matrix_run_count: int = Field(ge=0)
    single_runs: list[OperatorSingleRunIndexEntry] = Field(default_factory=list)
    matrix_runs: list[OperatorMatrixRunIndexEntry] = Field(default_factory=list)


class ReplayResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    events: list[EventEnvelope]
    scorecard: EvaluationScorecard
    pnl: ReplayPnLSummary | None = None
