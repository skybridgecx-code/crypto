from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.config import Settings, load_settings
from crypto_agent.enums import EventType, Mode, PolicyAction, Side
from crypto_agent.evaluation.models import EvaluationScorecard, ReplayPnLSummary, TradeLedger
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.evaluation.scorecard import build_trade_ledger
from crypto_agent.events.envelope import EventEnvelope
from crypto_agent.events.journal import (
    AppendOnlyJournal,
    build_execution_events,
    build_review_packet,
)
from crypto_agent.execution.router import ExecutionRouter
from crypto_agent.external_signals.loader import (
    apply_external_confirmation_to_proposal,
    load_external_confirmation_artifact,
)
from crypto_agent.external_signals.models import ExternalConfirmationDecision
from crypto_agent.features.models import FeatureSnapshot
from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.ids import new_id
from crypto_agent.market_data.models import Candle
from crypto_agent.market_data.replay import assess_candle_quality, load_candle_replay
from crypto_agent.monitoring.alerts import generate_execution_alerts, generate_kill_switch_alerts
from crypto_agent.monitoring.models import AlertEvent
from crypto_agent.policy.kill_switch import KillSwitchContext
from crypto_agent.portfolio.positions import PortfolioState, Position
from crypto_agent.regime.base import RegimeAssessment, RegimeConfig, RegimeLabel
from crypto_agent.regime.rules import classify_regime
from crypto_agent.risk.checks import RiskCheckResult, evaluate_trade_proposal
from crypto_agent.signals import (
    BreakoutSignalConfig,
    MeanReversionSignalConfig,
    generate_breakout_proposal,
    generate_mean_reversion_proposal,
)
from crypto_agent.types import FillEvent, TradeProposal

ExternalConfirmationImpactPolicy = Literal["conservative"]


class StrategyProposalGenerationDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    required_lookback_candles: int = Field(ge=1)
    considered_window_count: int = Field(default=0, ge=0)
    insufficient_lookback_count: int = Field(default=0, ge=0)
    emitted_proposal_count: int = Field(default=0, ge=0)
    emitted_side_counts: dict[str, int] = Field(default_factory=dict)
    non_emit_reason_counts: dict[str, int] = Field(default_factory=dict)
    last_outcome_status: Literal["insufficient_lookback", "not_emitted", "emitted"] | None = None
    last_outcome_reason: str | None = None
    strategy_config_source: Literal["default", "override"] = "default"
    strategy_config: dict[str, float | int | str] = Field(default_factory=dict)
    threshold_visibility: dict[str, object] = Field(default_factory=dict)


class ProposalPipelineDiagnostics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    external_confirmation_impact_policy: ExternalConfirmationImpactPolicy | None = None
    emitted_proposal_count: int = Field(default=0, ge=0)
    dropped_by_external_confirmation_count: int = Field(default=0, ge=0)
    blocked_by_risk_or_policy_count: int = Field(default=0, ge=0)
    blocked_reason_counts: dict[str, int] = Field(default_factory=dict)
    allowed_for_execution_count: int = Field(default=0, ge=0)


class ProposalGenerationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_kind: Literal["proposal_generation_summary_v1"] = "proposal_generation_summary_v1"
    run_id: str
    replay_path: str
    candle_count: int = Field(ge=0)
    breakout: StrategyProposalGenerationDiagnostics
    mean_reversion: StrategyProposalGenerationDiagnostics
    proposal_pipeline: ProposalPipelineDiagnostics


class PaperRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    replay_path: Path
    journal_path: Path
    summary_path: Path
    report_path: Path
    trade_ledger_path: Path
    scorecard: EvaluationScorecard
    pnl: ReplayPnLSummary
    trade_ledger: TradeLedger
    review_packet: dict[str, object]
    operator_summary: dict[str, object]
    proposal_generation_summary_path: Path
    proposal_generation_summary: ProposalGenerationSummary
    quality_issue_count: int = Field(ge=0)


def _interval_seconds(interval: str) -> int:
    unit = interval[-1]
    magnitude = int(interval[:-1])
    if magnitude <= 0:
        raise ValueError("interval magnitude must be positive")
    multipliers = {"m": 60, "h": 3600, "d": 86_400}
    try:
        return magnitude * multipliers[unit]
    except KeyError as exc:
        raise ValueError(f"Unsupported candle interval: {interval}") from exc


def _alert_events(
    alerts: list[AlertEvent],
    *,
    run_id: str,
    strategy_id: str | None,
    symbol: str | None,
    mode: Mode,
) -> list[EventEnvelope]:
    return [
        EventEnvelope(
            event_type=EventType.ALERT_RAISED,
            source="monitoring",
            run_id=run_id,
            strategy_id=strategy_id,
            symbol=symbol,
            mode=mode,
            timestamp=alert.observed_at,
            payload=alert.model_dump(mode="json"),
        )
        for alert in alerts
    ]


def _external_confirmation_event(
    *,
    run_id: str,
    proposal: TradeProposal,
    settings: Settings,
    decision: ExternalConfirmationDecision,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.ALERT_RAISED,
        source="external_confirmation",
        run_id=run_id,
        strategy_id=proposal.strategy_id,
        symbol=proposal.symbol,
        mode=settings.mode,
        payload=decision.model_dump(mode="json"),
    )


def _kill_switch_event(
    *,
    run_id: str,
    proposal: TradeProposal,
    settings: Settings,
    reason_codes: list[str],
) -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.KILL_SWITCH_ACTIVATED,
        source="policy_guardrails",
        run_id=run_id,
        strategy_id=proposal.strategy_id,
        symbol=proposal.symbol,
        mode=settings.mode,
        payload={"reason_codes": reason_codes},
    )


def _update_kill_switch_context(
    context: KillSwitchContext,
    risk_result: RiskCheckResult,
    alerts: list[AlertEvent],
    report_rejected: bool,
) -> KillSwitchContext:
    slippage_breach_increment = sum(
        1 for alert in alerts if alert.code == "slippage_above_threshold"
    )
    if report_rejected:
        consecutive_order_rejects = context.consecutive_order_rejects + 1
    else:
        consecutive_order_rejects = 0

    return context.model_copy(
        update={
            "consecutive_order_rejects": consecutive_order_rejects,
            "slippage_breach_count": context.slippage_breach_count + slippage_breach_increment,
            "manual_halt": context.manual_halt
            or risk_result.decision.action is PolicyAction.HALT
            and "manual_halt" in risk_result.decision.reason_codes,
        }
    )


def _apply_fill(portfolio: PortfolioState, fill: FillEvent) -> PortfolioState:
    signed_quantity = fill.quantity if fill.side is Side.BUY else -fill.quantity
    cash_delta = (
        -(fill.notional_usd + fill.fee_usd)
        if fill.side is Side.BUY
        else fill.notional_usd - fill.fee_usd
    )
    positions_by_symbol = {position.symbol: position for position in portfolio.positions}
    existing = positions_by_symbol.get(fill.symbol)

    if existing is None:
        if signed_quantity != 0:
            positions_by_symbol[fill.symbol] = Position(
                symbol=fill.symbol,
                quantity=signed_quantity,
                entry_price=fill.price,
                mark_price=fill.price,
            )
    else:
        new_quantity = existing.quantity + signed_quantity
        if abs(new_quantity) < 1e-12:
            del positions_by_symbol[fill.symbol]
        elif existing.quantity == 0 or existing.quantity * signed_quantity > 0:
            weighted_entry_price = (
                abs(existing.quantity) * existing.entry_price + abs(signed_quantity) * fill.price
            ) / (abs(existing.quantity) + abs(signed_quantity))
            positions_by_symbol[fill.symbol] = Position(
                symbol=fill.symbol,
                quantity=new_quantity,
                entry_price=weighted_entry_price,
                mark_price=fill.price,
            )
        elif abs(signed_quantity) < abs(existing.quantity):
            positions_by_symbol[fill.symbol] = Position(
                symbol=fill.symbol,
                quantity=new_quantity,
                entry_price=existing.entry_price,
                mark_price=fill.price,
            )
        else:
            positions_by_symbol[fill.symbol] = Position(
                symbol=fill.symbol,
                quantity=new_quantity,
                entry_price=fill.price,
                mark_price=fill.price,
            )

    return portfolio.model_copy(
        update={
            "available_cash_usd": portfolio.available_cash_usd + cash_delta,
            "positions": list(positions_by_symbol.values()),
        }
    )


def _apply_execution_to_portfolio(
    portfolio: PortfolioState,
    fills: list[FillEvent],
) -> PortfolioState:
    updated = portfolio
    for fill in fills:
        updated = _apply_fill(updated, fill)
    return updated


def _operator_summary(
    *,
    fixture_name: str,
    scorecard: EvaluationScorecard,
    review_packet: dict[str, Any],
) -> dict[str, object]:
    event_types = [str(event_type) for event_type in review_packet["event_types"]]
    event_type_counts = Counter(event_types)
    return {
        "fixture": fixture_name,
        "run_id": scorecard.run_id,
        "event_count": scorecard.event_count,
        "proposal_count": scorecard.proposal_count,
        "approval_count": scorecard.approval_count,
        "denial_count": scorecard.denial_count,
        "halt_count": scorecard.halt_count,
        "order_intent_count": scorecard.order_intent_count,
        "orders_submitted_count": scorecard.orders_submitted_count,
        "order_reject_count": scorecard.order_reject_count,
        "fill_event_count": scorecard.fill_event_count,
        "partial_fill_intent_count": scorecard.partial_fill_intent_count,
        "complete_execution_count": scorecard.complete_execution_count,
        "incomplete_execution_count": scorecard.incomplete_execution_count,
        "alert_count": event_type_counts["alert.raised"],
        "kill_switch_activations": event_type_counts["kill_switch.activated"],
        "review_rejected_event_count": review_packet["rejected_event_count"],
        "review_filled_event_count": review_packet["filled_event_count"],
        "first_event_type": event_types[0] if event_types else None,
        "last_event_type": event_types[-1] if event_types else None,
    }


def _sorted_counter(counter: Counter[str]) -> dict[str, int]:
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


def _evaluate_breakout_proposal_with_reason(
    *,
    candles: list[Candle],
    features: FeatureSnapshot,
    regime: RegimeAssessment,
    config: BreakoutSignalConfig,
) -> tuple[TradeProposal | None, str]:
    proposal = generate_breakout_proposal(candles, features, regime, config)
    if proposal is not None:
        return proposal, f"emitted_{proposal.side.value.lower()}"
    if regime.label is not RegimeLabel.TREND:
        return None, "regime_not_trend"
    if features.average_dollar_volume < config.min_average_dollar_volume:
        return None, "average_dollar_volume_below_min"
    if features.average_range_bps > config.max_average_range_bps:
        return None, "average_range_bps_above_max"

    trigger_candle = candles[-1]
    reference_window = candles[-(config.lookback_candles + 1) : -1]
    reference_high = max(candle.high for candle in reference_window)
    reference_low = min(candle.low for candle in reference_window)
    if (
        trigger_candle.close > reference_high
        and features.momentum_return < config.min_momentum_return
    ):
        return None, "upside_breakout_without_momentum"
    if (
        trigger_candle.close < reference_low
        and features.momentum_return > -config.min_momentum_return
    ):
        return None, "downside_breakout_without_momentum"
    if reference_low <= trigger_candle.close <= reference_high:
        return None, "price_within_reference_range"
    return None, "no_breakout_trigger"


def _evaluate_mean_reversion_proposal_with_reason(
    *,
    candles: list[Candle],
    features: FeatureSnapshot,
    regime: RegimeAssessment,
    config: MeanReversionSignalConfig,
) -> tuple[TradeProposal | None, str]:
    proposal = generate_mean_reversion_proposal(candles, features, regime, config)
    if proposal is not None:
        return proposal, f"emitted_{proposal.side.value.lower()}"
    if regime.label is not RegimeLabel.RANGE:
        return None, "regime_not_range"
    if features.average_dollar_volume < config.min_average_dollar_volume:
        return None, "average_dollar_volume_below_min"
    if features.realized_volatility > config.max_realized_volatility:
        return None, "realized_volatility_above_max"
    if features.atr_pct > config.max_atr_pct:
        return None, "atr_pct_above_max"

    reference_window = candles[-(config.lookback_candles + 1) : -1]
    reference_closes = [candle.close for candle in reference_window]
    mean_close = sum(reference_closes) / len(reference_closes)
    variance = sum((value - mean_close) ** 2 for value in reference_closes) / len(reference_closes)
    stddev_close = variance**0.5
    if stddev_close == 0:
        return None, "reference_stddev_zero"
    zscore = (candles[-1].close - mean_close) / stddev_close
    if abs(zscore) < config.zscore_entry_threshold:
        return None, "zscore_below_entry_threshold"
    return None, "no_mean_reversion_trigger"


def _compute_mean_reversion_abs_zscore(
    candles: list[Candle],
    config: MeanReversionSignalConfig,
) -> float | None:
    reference_window = candles[-(config.lookback_candles + 1) : -1]
    reference_closes = [candle.close for candle in reference_window]
    mean_close = sum(reference_closes) / len(reference_closes)
    variance = sum((value - mean_close) ** 2 for value in reference_closes) / len(reference_closes)
    stddev_close = variance**0.5
    if stddev_close == 0:
        return None
    zscore = (candles[-1].close - mean_close) / stddev_close
    return float(abs(zscore))


def _format_float(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def _relative_journal_path(run_id: str) -> str:
    return f"journals/{run_id}.jsonl"


def _relative_summary_path(run_id: str) -> str:
    return f"runs/{run_id}/summary.json"


def _relative_report_path(run_id: str) -> str:
    return f"runs/{run_id}/report.md"


def _relative_trade_ledger_path(run_id: str) -> str:
    return f"runs/{run_id}/trade_ledger.json"


def _event_type_sequence(review_packet: dict[str, Any]) -> str:
    event_types = [str(event_type) for event_type in review_packet["event_types"]]
    return ", ".join(event_types) if event_types else "<none>"


def write_operator_run_index(runs_dir: Path) -> Path:
    from crypto_agent.evaluation.models import (
        OperatorMatrixRunIndexEntry,
        OperatorRunIndex,
        OperatorSingleRunIndexEntry,
    )

    single_runs: list[OperatorSingleRunIndexEntry] = []
    matrix_runs: list[OperatorMatrixRunIndexEntry] = []

    if not runs_dir.exists():
        runs_dir.mkdir(parents=True, exist_ok=True)

    for run_dir in sorted(path for path in runs_dir.iterdir() if path.is_dir()):
        summary_path = run_dir / "summary.json"
        manifest_path = run_dir / "manifest.json"

        if summary_path.exists():
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            report_path = run_dir / "report.md"
            trade_ledger_path = Path(str(summary["trade_ledger_path"]))
            journal_path = Path(str(summary["journal_path"]))
            path_exists = {
                "journal_path": journal_path.exists(),
                "summary_path": summary_path.exists(),
                "report_path": report_path.exists(),
                "trade_ledger_path": trade_ledger_path.exists(),
            }
            single_runs.append(
                OperatorSingleRunIndexEntry(
                    order=0,
                    run_id=str(summary["run_id"]),
                    journal_path=str(journal_path),
                    summary_path=str(summary_path),
                    report_path=str(report_path),
                    trade_ledger_path=str(trade_ledger_path),
                    paths_exist=path_exists,
                    all_paths_exist=all(path_exists.values()),
                )
            )

        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            report_path = run_dir / "report.md"
            matrix_trade_ledger_path = Path(str(manifest["matrix_trade_ledger_path"]))
            matrix_comparison_path = Path(str(manifest["matrix_comparison_path"]))
            path_exists = {
                "manifest_path": manifest_path.exists(),
                "report_path": report_path.exists(),
                "matrix_trade_ledger_path": matrix_trade_ledger_path.exists(),
                "matrix_comparison_path": matrix_comparison_path.exists(),
            }
            matrix_runs.append(
                OperatorMatrixRunIndexEntry(
                    order=0,
                    matrix_run_id=str(manifest["matrix_run_id"]),
                    manifest_path=str(manifest_path),
                    report_path=str(report_path),
                    matrix_trade_ledger_path=str(matrix_trade_ledger_path),
                    matrix_comparison_path=str(matrix_comparison_path),
                    paths_exist=path_exists,
                    all_paths_exist=all(path_exists.values()),
                )
            )

    single_runs = [
        entry.model_copy(update={"order": index})
        for index, entry in enumerate(sorted(single_runs, key=lambda entry: entry.run_id))
    ]
    matrix_runs = [
        entry.model_copy(update={"order": index})
        for index, entry in enumerate(sorted(matrix_runs, key=lambda entry: entry.matrix_run_id))
    ]

    index_path = runs_dir / "operator_run_index.json"
    operator_index = OperatorRunIndex(
        index_path=str(index_path),
        single_run_count=len(single_runs),
        matrix_run_count=len(matrix_runs),
        single_runs=single_runs,
        matrix_runs=matrix_runs,
    )
    index_path.write_text(
        json.dumps(operator_index.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return index_path


def _build_operator_report(
    *,
    run_id: str,
    mode: Mode,
    replay_path: Path,
    quality_issue_count: int,
    scorecard: EvaluationScorecard,
    pnl: ReplayPnLSummary,
    review_packet: dict[str, Any],
    operator_summary: dict[str, object],
    external_confirmation_summary: dict[str, object] | None = None,
) -> str:
    lines = [
        "# Paper Run Operator Report",
        "",
        f"run_id: {run_id}",
        f"mode: {mode.value}",
        f"fixture: {replay_path.name}",
        f"replay_path: {replay_path}",
        f"journal_path: {_relative_journal_path(run_id)}",
        f"summary_path: {_relative_summary_path(run_id)}",
        f"report_path: {_relative_report_path(run_id)}",
        f"trade_ledger_path: {_relative_trade_ledger_path(run_id)}",
        f"quality_issue_count: {quality_issue_count}",
        "",
        "## Event Counts",
        f"event_count: {scorecard.event_count}",
        f"alert_count: {operator_summary['alert_count']}",
        f"kill_switch_activations: {operator_summary['kill_switch_activations']}",
        f"review_rejected_event_count: {review_packet['rejected_event_count']}",
        f"review_filled_event_count: {review_packet['filled_event_count']}",
        f"first_event_type: {operator_summary['first_event_type']}",
        f"last_event_type: {operator_summary['last_event_type']}",
        "",
        "## Scorecard",
        f"proposal_count: {scorecard.proposal_count}",
        f"approval_count: {scorecard.approval_count}",
        f"denial_count: {scorecard.denial_count}",
        f"halt_count: {scorecard.halt_count}",
        f"order_intent_count: {scorecard.order_intent_count}",
        f"orders_submitted_count: {scorecard.orders_submitted_count}",
        f"order_reject_count: {scorecard.order_reject_count}",
        f"fill_event_count: {scorecard.fill_event_count}",
        f"filled_intent_count: {scorecard.filled_intent_count}",
        f"partial_fill_intent_count: {scorecard.partial_fill_intent_count}",
        f"complete_execution_count: {scorecard.complete_execution_count}",
        f"incomplete_execution_count: {scorecard.incomplete_execution_count}",
        f"average_slippage_bps: {_format_float(scorecard.average_slippage_bps)}",
        f"max_slippage_bps: {_format_float(scorecard.max_slippage_bps)}",
        f"total_fill_notional_usd: {_format_float(scorecard.total_fill_notional_usd)}",
        f"total_fee_usd: {_format_float(scorecard.total_fee_usd)}",
        "",
        "## PnL",
        f"starting_equity_usd: {_format_float(pnl.starting_equity_usd)}",
        f"gross_realized_pnl_usd: {_format_float(pnl.gross_realized_pnl_usd)}",
        f"total_fee_usd: {_format_float(pnl.total_fee_usd)}",
        f"net_realized_pnl_usd: {_format_float(pnl.net_realized_pnl_usd)}",
        f"ending_unrealized_pnl_usd: {_format_float(pnl.ending_unrealized_pnl_usd)}",
        f"ending_equity_usd: {_format_float(pnl.ending_equity_usd)}",
        f"return_fraction: {_format_float(pnl.return_fraction)}",
        "",
        "## Review Packet",
        f"event_count: {review_packet['event_count']}",
        f"filled_event_count: {review_packet['filled_event_count']}",
        f"rejected_event_count: {review_packet['rejected_event_count']}",
        f"event_types: {_event_type_sequence(review_packet)}",
        "",
        "## Operator Summary",
        f"fixture: {operator_summary['fixture']}",
        f"run_id: {operator_summary['run_id']}",
        f"event_count: {operator_summary['event_count']}",
        f"proposal_count: {operator_summary['proposal_count']}",
        f"approval_count: {operator_summary['approval_count']}",
        f"denial_count: {operator_summary['denial_count']}",
        f"halt_count: {operator_summary['halt_count']}",
        f"order_intent_count: {operator_summary['order_intent_count']}",
        f"orders_submitted_count: {operator_summary['orders_submitted_count']}",
        f"order_reject_count: {operator_summary['order_reject_count']}",
        f"fill_event_count: {operator_summary['fill_event_count']}",
        f"partial_fill_intent_count: {operator_summary['partial_fill_intent_count']}",
        f"complete_execution_count: {operator_summary['complete_execution_count']}",
        f"incomplete_execution_count: {operator_summary['incomplete_execution_count']}",
        f"alert_count: {operator_summary['alert_count']}",
        f"kill_switch_activations: {operator_summary['kill_switch_activations']}",
        f"review_rejected_event_count: {operator_summary['review_rejected_event_count']}",
        f"review_filled_event_count: {operator_summary['review_filled_event_count']}",
        f"first_event_type: {operator_summary['first_event_type']}",
        f"last_event_type: {operator_summary['last_event_type']}",
    ]
    if external_confirmation_summary is not None:
        lines.extend(
            [
                "",
                "## External Confirmation",
                f"artifact_loaded: {external_confirmation_summary['artifact_loaded']}",
                f"asset: {external_confirmation_summary['asset']}",
                f"source_system: {external_confirmation_summary['source_system']}",
                f"decision_count: {external_confirmation_summary['decision_count']}",
                "decision_status_counts: "
                f"{external_confirmation_summary['decision_status_counts']}",
            ]
        )
        if external_confirmation_summary.get("impact_policy") is not None:
            lines.append(f"impact_policy: {external_confirmation_summary['impact_policy']}")
    return "\n".join(lines)


def _write_operator_report(
    *,
    run_id: str,
    mode: Mode,
    replay_path: Path,
    report_path: Path,
    quality_issue_count: int,
    scorecard: EvaluationScorecard,
    pnl: ReplayPnLSummary,
    review_packet: dict[str, Any],
    operator_summary: dict[str, object],
    external_confirmation_summary: dict[str, object] | None = None,
) -> None:
    report_path.write_text(
        _build_operator_report(
            run_id=run_id,
            mode=mode,
            replay_path=replay_path,
            quality_issue_count=quality_issue_count,
            scorecard=scorecard,
            pnl=pnl,
            review_packet=review_packet,
            operator_summary=operator_summary,
            external_confirmation_summary=external_confirmation_summary,
        ),
        encoding="utf-8",
    )


def run_paper_replay(
    replay_path: str | Path,
    *,
    settings: Settings,
    run_id: str | None = None,
    equity_usd: float = 100_000.0,
    starting_portfolio: PortfolioState | None = None,
    journal_path: str | Path | None = None,
    run_dir: str | Path | None = None,
    external_confirmation_path: str | Path | None = None,
    external_confirmation_impact_policy: ExternalConfirmationImpactPolicy | None = None,
    regime_config_override: RegimeConfig | None = None,
    breakout_config_override: BreakoutSignalConfig | None = None,
    mean_reversion_config_override: MeanReversionSignalConfig | None = None,
) -> PaperRunResult:
    if settings.mode is not Mode.PAPER:
        raise ValueError("Paper replay harness requires settings.mode to be paper.")

    replay_fixture_path = Path(replay_path)
    candles = load_candle_replay(replay_fixture_path)
    if not candles:
        raise ValueError("Replay fixture must contain at least one candle.")

    quality_issues = assess_candle_quality(
        candles,
        expected_interval_seconds=_interval_seconds(candles[0].interval),
    )
    if quality_issues:
        raise ValueError("Replay fixture contains candle quality issues.")

    resolved_run_id = run_id or f"{replay_fixture_path.stem}-{new_id()}"
    resolved_journal_path = (
        Path(journal_path)
        if journal_path is not None
        else settings.paths.journals_dir / f"{resolved_run_id}.jsonl"
    )
    resolved_run_dir = (
        Path(run_dir) if run_dir is not None else settings.paths.runs_dir / resolved_run_id
    )
    summary_path = resolved_run_dir / "summary.json"
    report_path = resolved_run_dir / "report.md"
    trade_ledger_path = resolved_run_dir / "trade_ledger.json"
    proposal_generation_summary_path = resolved_run_dir / "proposal_generation_summary.json"

    if resolved_journal_path.exists():
        raise FileExistsError(f"Journal path already exists: {resolved_journal_path}")
    if resolved_run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {resolved_run_dir}")

    resolved_journal_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_run_dir.mkdir(parents=True, exist_ok=False)
    resolved_journal_path.touch(exist_ok=False)

    journal = AppendOnlyJournal(resolved_journal_path)
    initial_portfolio = (
        starting_portfolio.model_copy(deep=True)
        if starting_portfolio is not None
        else PortfolioState(
            equity_usd=equity_usd,
            available_cash_usd=equity_usd,
        )
    )
    portfolio = initial_portfolio.model_copy(deep=True)
    kill_switch_context = KillSwitchContext()
    execution_router = ExecutionRouter()
    breakout_config = breakout_config_override or BreakoutSignalConfig()
    mean_reversion_config = mean_reversion_config_override or MeanReversionSignalConfig()
    breakout_config_source: Literal["default", "override"] = (
        "override" if breakout_config_override is not None else "default"
    )
    mean_reversion_config_source: Literal["default", "override"] = (
        "override" if mean_reversion_config_override is not None else "default"
    )
    external_confirmation = load_external_confirmation_artifact(external_confirmation_path)
    external_confirmation_decisions: list[ExternalConfirmationDecision] = []
    breakout_feature_lookback = breakout_config.lookback_candles + 1
    mean_reversion_feature_lookback = mean_reversion_config.lookback_candles + 1
    breakout_emitted_side_counts: Counter[str] = Counter()
    breakout_non_emit_reason_counts: Counter[str] = Counter()
    mean_reversion_emitted_side_counts: Counter[str] = Counter()
    mean_reversion_non_emit_reason_counts: Counter[str] = Counter()
    breakout_considered_window_count = 0
    mean_reversion_considered_window_count = 0
    breakout_insufficient_lookback_count = 0
    mean_reversion_insufficient_lookback_count = 0
    breakout_last_outcome_status: (
        Literal["insufficient_lookback", "not_emitted", "emitted"] | None
    ) = None
    mean_reversion_last_outcome_status: (
        Literal["insufficient_lookback", "not_emitted", "emitted"] | None
    ) = None
    breakout_last_outcome_reason: str | None = None
    mean_reversion_last_outcome_reason: str | None = None
    breakout_average_dollar_volume_observed = _NumericSummaryAccumulator()
    breakout_average_dollar_volume_gap = _NumericSummaryAccumulator()
    breakout_average_range_bps_observed = _NumericSummaryAccumulator()
    breakout_average_range_bps_gap = _NumericSummaryAccumulator()
    breakout_abs_momentum_return_observed = _NumericSummaryAccumulator()
    breakout_abs_momentum_return_gap = _NumericSummaryAccumulator()
    breakout_observed_average_dollar_volume_last: float | None = None
    breakout_gap_to_min_average_dollar_volume_last: float | None = None
    breakout_observed_average_range_bps_last: float | None = None
    breakout_gap_to_max_average_range_bps_last: float | None = None
    breakout_observed_abs_momentum_return_last: float | None = None
    breakout_gap_to_min_abs_momentum_return_last: float | None = None
    mean_reversion_average_dollar_volume_observed = _NumericSummaryAccumulator()
    mean_reversion_average_dollar_volume_gap = _NumericSummaryAccumulator()
    mean_reversion_realized_volatility_observed = _NumericSummaryAccumulator()
    mean_reversion_realized_volatility_gap = _NumericSummaryAccumulator()
    mean_reversion_atr_pct_observed = _NumericSummaryAccumulator()
    mean_reversion_atr_pct_gap = _NumericSummaryAccumulator()
    mean_reversion_abs_zscore_observed = _NumericSummaryAccumulator()
    mean_reversion_abs_zscore_gap = _NumericSummaryAccumulator()
    mean_reversion_observed_average_dollar_volume_last: float | None = None
    mean_reversion_gap_to_min_average_dollar_volume_last: float | None = None
    mean_reversion_observed_realized_volatility_last: float | None = None
    mean_reversion_gap_to_max_realized_volatility_last: float | None = None
    mean_reversion_observed_atr_pct_last: float | None = None
    mean_reversion_gap_to_max_atr_pct_last: float | None = None
    mean_reversion_observed_abs_zscore_last: float | None = None
    mean_reversion_gap_to_zscore_entry_threshold_last: float | None = None
    emitted_proposal_count = 0
    dropped_by_external_confirmation_count = 0
    blocked_by_risk_or_policy_count = 0
    allowed_for_execution_count = 0
    blocked_reason_counts: Counter[str] = Counter()

    for candle_index in range(1, len(candles) + 1):
        candle_window = candles[:candle_index]
        proposals: list[TradeProposal] = []

        if len(candle_window) >= breakout_feature_lookback:
            breakout_considered_window_count += 1
            breakout_features = build_feature_snapshot(
                candle_window,
                lookback_periods=breakout_feature_lookback,
            )
            breakout_observed_average_dollar_volume_last = breakout_features.average_dollar_volume
            breakout_gap_to_min_average_dollar_volume_last = (
                breakout_features.average_dollar_volume - breakout_config.min_average_dollar_volume
            )
            breakout_average_dollar_volume_observed.add(
                breakout_observed_average_dollar_volume_last
            )
            breakout_average_dollar_volume_gap.add(breakout_gap_to_min_average_dollar_volume_last)
            breakout_observed_average_range_bps_last = breakout_features.average_range_bps
            breakout_gap_to_max_average_range_bps_last = (
                breakout_features.average_range_bps - breakout_config.max_average_range_bps
            )
            breakout_average_range_bps_observed.add(breakout_observed_average_range_bps_last)
            breakout_average_range_bps_gap.add(breakout_gap_to_max_average_range_bps_last)
            breakout_observed_abs_momentum_return_last = abs(breakout_features.momentum_return)
            breakout_gap_to_min_abs_momentum_return_last = (
                breakout_observed_abs_momentum_return_last - breakout_config.min_momentum_return
            )
            breakout_abs_momentum_return_observed.add(breakout_observed_abs_momentum_return_last)
            breakout_abs_momentum_return_gap.add(breakout_gap_to_min_abs_momentum_return_last)
            breakout_regime = classify_regime(breakout_features, regime_config_override)
            breakout_proposal, breakout_reason = _evaluate_breakout_proposal_with_reason(
                candles=candle_window,
                features=breakout_features,
                regime=breakout_regime,
                config=breakout_config,
            )
            if breakout_proposal is not None:
                proposals.append(breakout_proposal)
                breakout_emitted_side_counts[breakout_proposal.side.value.lower()] += 1
                breakout_last_outcome_status = "emitted"
            else:
                breakout_non_emit_reason_counts[breakout_reason] += 1
                breakout_last_outcome_status = "not_emitted"
            breakout_last_outcome_reason = breakout_reason
        else:
            breakout_insufficient_lookback_count += 1
            breakout_last_outcome_status = "insufficient_lookback"
            breakout_last_outcome_reason = "insufficient_lookback"

        if len(candle_window) >= mean_reversion_feature_lookback:
            mean_reversion_considered_window_count += 1
            mean_reversion_features = build_feature_snapshot(
                candle_window,
                lookback_periods=mean_reversion_feature_lookback,
            )
            mean_reversion_observed_average_dollar_volume_last = (
                mean_reversion_features.average_dollar_volume
            )
            mean_reversion_gap_to_min_average_dollar_volume_last = (
                mean_reversion_features.average_dollar_volume
                - mean_reversion_config.min_average_dollar_volume
            )
            mean_reversion_average_dollar_volume_observed.add(
                mean_reversion_observed_average_dollar_volume_last
            )
            mean_reversion_average_dollar_volume_gap.add(
                mean_reversion_gap_to_min_average_dollar_volume_last
            )
            mean_reversion_observed_realized_volatility_last = (
                mean_reversion_features.realized_volatility
            )
            mean_reversion_gap_to_max_realized_volatility_last = (
                mean_reversion_features.realized_volatility
                - mean_reversion_config.max_realized_volatility
            )
            mean_reversion_realized_volatility_observed.add(
                mean_reversion_observed_realized_volatility_last
            )
            mean_reversion_realized_volatility_gap.add(
                mean_reversion_gap_to_max_realized_volatility_last
            )
            mean_reversion_observed_atr_pct_last = mean_reversion_features.atr_pct
            mean_reversion_gap_to_max_atr_pct_last = (
                mean_reversion_features.atr_pct - mean_reversion_config.max_atr_pct
            )
            mean_reversion_atr_pct_observed.add(mean_reversion_observed_atr_pct_last)
            mean_reversion_atr_pct_gap.add(mean_reversion_gap_to_max_atr_pct_last)
            mean_reversion_observed_abs_zscore_last = _compute_mean_reversion_abs_zscore(
                candle_window,
                mean_reversion_config,
            )
            if mean_reversion_observed_abs_zscore_last is not None:
                mean_reversion_gap_to_zscore_entry_threshold_last = (
                    mean_reversion_observed_abs_zscore_last
                    - mean_reversion_config.zscore_entry_threshold
                )
                mean_reversion_abs_zscore_observed.add(mean_reversion_observed_abs_zscore_last)
                mean_reversion_abs_zscore_gap.add(mean_reversion_gap_to_zscore_entry_threshold_last)
            else:
                mean_reversion_gap_to_zscore_entry_threshold_last = None
            mean_reversion_regime = classify_regime(
                mean_reversion_features,
                regime_config_override,
            )
            mean_reversion_proposal, mean_reversion_reason = (
                _evaluate_mean_reversion_proposal_with_reason(
                    candles=candle_window,
                    features=mean_reversion_features,
                    regime=mean_reversion_regime,
                    config=mean_reversion_config,
                )
            )
            if mean_reversion_proposal is not None:
                proposals.append(mean_reversion_proposal)
                mean_reversion_emitted_side_counts[mean_reversion_proposal.side.value.lower()] += 1
                mean_reversion_last_outcome_status = "emitted"
            else:
                mean_reversion_non_emit_reason_counts[mean_reversion_reason] += 1
                mean_reversion_last_outcome_status = "not_emitted"
            mean_reversion_last_outcome_reason = mean_reversion_reason
        else:
            mean_reversion_insufficient_lookback_count += 1
            mean_reversion_last_outcome_status = "insufficient_lookback"
            mean_reversion_last_outcome_reason = "insufficient_lookback"

        for proposal in proposals:
            emitted_proposal_count += 1
            proposal_for_evaluation: TradeProposal | None = proposal
            if external_confirmation is not None:
                proposal_for_evaluation, confirmation_decision = (
                    apply_external_confirmation_to_proposal(
                        proposal=proposal,
                        artifact=external_confirmation,
                    )
                )
                external_confirmation_decisions.append(confirmation_decision)
                journal.append(
                    _external_confirmation_event(
                        run_id=resolved_run_id,
                        proposal=proposal,
                        settings=settings,
                        decision=confirmation_decision,
                    )
                )
                if proposal_for_evaluation is None:
                    dropped_by_external_confirmation_count += 1
                    continue
                if (
                    external_confirmation_impact_policy == "conservative"
                    and confirmation_decision.status == "penalized_conflict"
                ):
                    dropped_by_external_confirmation_count += 1
                    continue
            if proposal_for_evaluation is None:
                continue
            evaluated_proposal = proposal_for_evaluation

            risk_result = evaluate_trade_proposal(
                evaluated_proposal,
                portfolio,
                settings,
                kill_switch_context=kill_switch_context,
            )

            if risk_result.decision.action is PolicyAction.ALLOW:
                allowed_for_execution_count += 1
                report = execution_router.execute(risk_result)
                journal.append_many(
                    build_execution_events(resolved_run_id, evaluated_proposal, risk_result, report)
                )
                alerts = generate_execution_alerts(report)
                journal.append_many(
                    _alert_events(
                        alerts,
                        run_id=resolved_run_id,
                        strategy_id=evaluated_proposal.strategy_id,
                        symbol=evaluated_proposal.symbol,
                        mode=settings.mode,
                    )
                )
                kill_switch_context = _update_kill_switch_context(
                    kill_switch_context,
                    risk_result,
                    alerts,
                    report_rejected=report.rejected,
                )
                if not report.rejected:
                    portfolio = _apply_execution_to_portfolio(portfolio, report.fills)
                continue

            blocked_by_risk_or_policy_count += 1
            blocked_reason_counts.update(risk_result.decision.reason_codes)
            journal.append_many(
                build_execution_events(resolved_run_id, evaluated_proposal, risk_result)
            )
            if (
                risk_result.decision.action is PolicyAction.HALT
                and "kill_switch_active" in risk_result.decision.reason_codes
            ):
                kill_reason_codes = [
                    reason
                    for reason in risk_result.decision.reason_codes
                    if reason != "kill_switch_active"
                ]
                journal.append(
                    _kill_switch_event(
                        run_id=resolved_run_id,
                        proposal=evaluated_proposal,
                        settings=settings,
                        reason_codes=kill_reason_codes,
                    )
                )
                kill_switch_alerts = generate_kill_switch_alerts(
                    kill_switch_context,
                    settings,
                    observed_at=candle_window[-1].close_time,
                )
                journal.append_many(
                    _alert_events(
                        kill_switch_alerts,
                        run_id=resolved_run_id,
                        strategy_id=evaluated_proposal.strategy_id,
                        symbol=evaluated_proposal.symbol,
                        mode=settings.mode,
                    )
                )

    replay_result = replay_journal(
        resolved_journal_path,
        replay_path=replay_fixture_path,
        starting_equity_usd=initial_portfolio.equity_usd,
        starting_positions=initial_portfolio.positions,
    )
    scorecard = replay_result.scorecard
    if not replay_result.events:
        scorecard = EvaluationScorecard(run_id=resolved_run_id, event_count=0)
    pnl = replay_result.pnl or ReplayPnLSummary(
        starting_equity_usd=initial_portfolio.equity_usd,
        ending_equity_usd=initial_portfolio.equity_usd,
    )
    trade_ledger = build_trade_ledger(replay_result.events, run_id=resolved_run_id)
    review_packet = build_review_packet(replay_result.events)
    operator_summary = _operator_summary(
        fixture_name=replay_fixture_path.name,
        scorecard=scorecard,
        review_packet=review_packet,
    )
    proposal_generation_summary = ProposalGenerationSummary(
        run_id=resolved_run_id,
        replay_path=str(replay_fixture_path),
        candle_count=len(candles),
        breakout=StrategyProposalGenerationDiagnostics(
            strategy_id=breakout_config.strategy_id,
            required_lookback_candles=breakout_feature_lookback,
            considered_window_count=breakout_considered_window_count,
            insufficient_lookback_count=breakout_insufficient_lookback_count,
            emitted_proposal_count=sum(breakout_emitted_side_counts.values()),
            emitted_side_counts=_sorted_counter(breakout_emitted_side_counts),
            non_emit_reason_counts=_sorted_counter(breakout_non_emit_reason_counts),
            last_outcome_status=breakout_last_outcome_status,
            last_outcome_reason=breakout_last_outcome_reason,
            strategy_config_source=breakout_config_source,
            strategy_config=breakout_config.model_dump(mode="json"),
            threshold_visibility={
                "min_average_dollar_volume_threshold_used": (
                    breakout_config.min_average_dollar_volume
                ),
                "observed_average_dollar_volume_last": breakout_observed_average_dollar_volume_last,
                "gap_to_min_average_dollar_volume_last": (
                    breakout_gap_to_min_average_dollar_volume_last
                ),
                "observed_average_dollar_volume_summary": (
                    breakout_average_dollar_volume_observed.to_summary()
                ),
                "gap_to_min_average_dollar_volume_summary": (
                    breakout_average_dollar_volume_gap.to_summary()
                ),
                "max_average_range_bps_threshold_used": breakout_config.max_average_range_bps,
                "observed_average_range_bps_last": breakout_observed_average_range_bps_last,
                "gap_to_max_average_range_bps_last": breakout_gap_to_max_average_range_bps_last,
                "observed_average_range_bps_summary": (
                    breakout_average_range_bps_observed.to_summary()
                ),
                "gap_to_max_average_range_bps_summary": (
                    breakout_average_range_bps_gap.to_summary()
                ),
                "min_abs_momentum_return_threshold_used": (breakout_config.min_momentum_return),
                "observed_abs_momentum_return_last": breakout_observed_abs_momentum_return_last,
                "gap_to_min_abs_momentum_return_last": (
                    breakout_gap_to_min_abs_momentum_return_last
                ),
                "observed_abs_momentum_return_summary": (
                    breakout_abs_momentum_return_observed.to_summary()
                ),
                "gap_to_min_abs_momentum_return_summary": (
                    breakout_abs_momentum_return_gap.to_summary()
                ),
            },
        ),
        mean_reversion=StrategyProposalGenerationDiagnostics(
            strategy_id=mean_reversion_config.strategy_id,
            required_lookback_candles=mean_reversion_feature_lookback,
            considered_window_count=mean_reversion_considered_window_count,
            insufficient_lookback_count=mean_reversion_insufficient_lookback_count,
            emitted_proposal_count=sum(mean_reversion_emitted_side_counts.values()),
            emitted_side_counts=_sorted_counter(mean_reversion_emitted_side_counts),
            non_emit_reason_counts=_sorted_counter(mean_reversion_non_emit_reason_counts),
            last_outcome_status=mean_reversion_last_outcome_status,
            last_outcome_reason=mean_reversion_last_outcome_reason,
            strategy_config_source=mean_reversion_config_source,
            strategy_config=mean_reversion_config.model_dump(mode="json"),
            threshold_visibility={
                "min_average_dollar_volume_threshold_used": (
                    mean_reversion_config.min_average_dollar_volume
                ),
                "observed_average_dollar_volume_last": (
                    mean_reversion_observed_average_dollar_volume_last
                ),
                "gap_to_min_average_dollar_volume_last": (
                    mean_reversion_gap_to_min_average_dollar_volume_last
                ),
                "observed_average_dollar_volume_summary": (
                    mean_reversion_average_dollar_volume_observed.to_summary()
                ),
                "gap_to_min_average_dollar_volume_summary": (
                    mean_reversion_average_dollar_volume_gap.to_summary()
                ),
                "max_realized_volatility_threshold_used": (
                    mean_reversion_config.max_realized_volatility
                ),
                "observed_realized_volatility_last": (
                    mean_reversion_observed_realized_volatility_last
                ),
                "gap_to_max_realized_volatility_last": (
                    mean_reversion_gap_to_max_realized_volatility_last
                ),
                "observed_realized_volatility_summary": (
                    mean_reversion_realized_volatility_observed.to_summary()
                ),
                "gap_to_max_realized_volatility_summary": (
                    mean_reversion_realized_volatility_gap.to_summary()
                ),
                "max_atr_pct_threshold_used": mean_reversion_config.max_atr_pct,
                "observed_atr_pct_last": mean_reversion_observed_atr_pct_last,
                "gap_to_max_atr_pct_last": mean_reversion_gap_to_max_atr_pct_last,
                "observed_atr_pct_summary": mean_reversion_atr_pct_observed.to_summary(),
                "gap_to_max_atr_pct_summary": mean_reversion_atr_pct_gap.to_summary(),
                "zscore_entry_threshold_used": mean_reversion_config.zscore_entry_threshold,
                "observed_abs_zscore_last": mean_reversion_observed_abs_zscore_last,
                "gap_to_zscore_entry_threshold_last": (
                    mean_reversion_gap_to_zscore_entry_threshold_last
                ),
                "observed_abs_zscore_summary": mean_reversion_abs_zscore_observed.to_summary(),
                "gap_to_zscore_entry_threshold_summary": (
                    mean_reversion_abs_zscore_gap.to_summary()
                ),
            },
        ),
        proposal_pipeline=ProposalPipelineDiagnostics(
            external_confirmation_impact_policy=external_confirmation_impact_policy,
            emitted_proposal_count=emitted_proposal_count,
            dropped_by_external_confirmation_count=dropped_by_external_confirmation_count,
            blocked_by_risk_or_policy_count=blocked_by_risk_or_policy_count,
            blocked_reason_counts=_sorted_counter(blocked_reason_counts),
            allowed_for_execution_count=allowed_for_execution_count,
        ),
    )

    external_confirmation_summary: dict[str, object] | None = None
    summary = {
        "run_id": resolved_run_id,
        "mode": settings.mode.value,
        "replay_path": str(replay_fixture_path),
        "journal_path": str(resolved_journal_path),
        "trade_ledger_path": str(trade_ledger_path),
        "quality_issue_count": len(quality_issues),
        "scorecard": scorecard.model_dump(mode="json"),
        "pnl": pnl.model_dump(mode="json"),
        "review_packet": review_packet,
        "operator_summary": operator_summary,
    }
    if external_confirmation_path is not None:
        external_confirmation_summary = {
            "artifact_path": str(Path(external_confirmation_path).resolve()),
            "artifact_loaded": external_confirmation is not None,
            "source_system": external_confirmation.source_system
            if external_confirmation is not None
            else None,
            "asset": external_confirmation.asset if external_confirmation is not None else None,
            "decision_count": len(external_confirmation_decisions),
            "decision_status_counts": dict(
                Counter(decision.status for decision in external_confirmation_decisions)
            ),
        }
        if external_confirmation_impact_policy is not None:
            external_confirmation_summary["impact_policy"] = external_confirmation_impact_policy
        summary["external_confirmation"] = external_confirmation_summary
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    proposal_generation_summary_path.write_text(
        json.dumps(proposal_generation_summary.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    trade_ledger_path.write_text(
        json.dumps(trade_ledger.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    _write_operator_report(
        run_id=resolved_run_id,
        mode=settings.mode,
        replay_path=replay_fixture_path,
        report_path=report_path,
        quality_issue_count=len(quality_issues),
        scorecard=scorecard,
        pnl=pnl,
        review_packet=review_packet,
        operator_summary=operator_summary,
        external_confirmation_summary=external_confirmation_summary,
    )
    write_operator_run_index(settings.paths.runs_dir)

    return PaperRunResult(
        run_id=resolved_run_id,
        replay_path=replay_fixture_path,
        journal_path=resolved_journal_path,
        summary_path=summary_path,
        report_path=report_path,
        trade_ledger_path=trade_ledger_path,
        scorecard=scorecard,
        pnl=pnl,
        trade_ledger=trade_ledger,
        review_packet=review_packet,
        operator_summary=operator_summary,
        proposal_generation_summary_path=proposal_generation_summary_path,
        proposal_generation_summary=proposal_generation_summary,
        quality_issue_count=len(quality_issues),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the validated paper replay harness.")
    parser.add_argument("replay_path", help="Path to the replay candle fixture JSONL file.")
    parser.add_argument(
        "--config",
        default="config/paper.yaml",
        help="Path to the paper-mode settings file.",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Optional explicit run identifier. Defaults to a generated replay-based id.",
    )
    parser.add_argument(
        "--equity-usd",
        type=float,
        default=100_000.0,
        help="Starting paper equity and available cash for the replay run.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    settings = load_settings(args.config)
    result = run_paper_replay(
        args.replay_path,
        settings=settings,
        run_id=args.run_id,
        equity_usd=args.equity_usd,
    )
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "journal_path": str(result.journal_path),
                "summary_path": str(result.summary_path),
                "report_path": str(result.report_path),
                "trade_ledger_path": str(result.trade_ledger_path),
                "pnl": result.pnl.model_dump(mode="json"),
                "scorecard": result.scorecard.model_dump(mode="json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
