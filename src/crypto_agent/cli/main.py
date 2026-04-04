from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from crypto_agent.config import Settings, load_settings
from crypto_agent.enums import EventType, Mode, PolicyAction, Side
from crypto_agent.evaluation.models import EvaluationScorecard
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.events.envelope import EventEnvelope
from crypto_agent.events.journal import (
    AppendOnlyJournal,
    build_execution_events,
    build_review_packet,
)
from crypto_agent.execution.router import ExecutionRouter
from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.ids import new_id
from crypto_agent.market_data.replay import assess_candle_quality, load_candle_replay
from crypto_agent.monitoring.alerts import generate_execution_alerts, generate_kill_switch_alerts
from crypto_agent.monitoring.models import AlertEvent
from crypto_agent.policy.kill_switch import KillSwitchContext
from crypto_agent.portfolio.positions import PortfolioState, Position
from crypto_agent.regime.rules import classify_regime
from crypto_agent.risk.checks import RiskCheckResult, evaluate_trade_proposal
from crypto_agent.signals import (
    BreakoutSignalConfig,
    MeanReversionSignalConfig,
    generate_breakout_proposal,
    generate_mean_reversion_proposal,
)
from crypto_agent.types import FillEvent, TradeProposal


class PaperRunResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    replay_path: Path
    journal_path: Path
    summary_path: Path
    report_path: Path
    scorecard: EvaluationScorecard
    review_packet: dict[str, object]
    operator_summary: dict[str, object]
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


def _format_float(value: float) -> str:
    text = f"{value:.10f}".rstrip("0").rstrip(".")
    return text or "0"


def _relative_journal_path(run_id: str) -> str:
    return f"journals/{run_id}.jsonl"


def _relative_summary_path(run_id: str) -> str:
    return f"runs/{run_id}/summary.json"


def _relative_report_path(run_id: str) -> str:
    return f"runs/{run_id}/report.md"


def _event_type_sequence(review_packet: dict[str, Any]) -> str:
    event_types = [str(event_type) for event_type in review_packet["event_types"]]
    return ", ".join(event_types) if event_types else "<none>"


def _build_operator_report(
    *,
    run_id: str,
    mode: Mode,
    replay_path: Path,
    quality_issue_count: int,
    scorecard: EvaluationScorecard,
    review_packet: dict[str, Any],
    operator_summary: dict[str, object],
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
    return "\n".join(lines)


def _write_operator_report(
    *,
    run_id: str,
    mode: Mode,
    replay_path: Path,
    report_path: Path,
    quality_issue_count: int,
    scorecard: EvaluationScorecard,
    review_packet: dict[str, Any],
    operator_summary: dict[str, object],
) -> None:
    report_path.write_text(
        _build_operator_report(
            run_id=run_id,
            mode=mode,
            replay_path=replay_path,
            quality_issue_count=quality_issue_count,
            scorecard=scorecard,
            review_packet=review_packet,
            operator_summary=operator_summary,
        ),
        encoding="utf-8",
    )


def run_paper_replay(
    replay_path: str | Path,
    *,
    settings: Settings,
    run_id: str | None = None,
    equity_usd: float = 100_000.0,
    journal_path: str | Path | None = None,
    run_dir: str | Path | None = None,
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

    if resolved_journal_path.exists():
        raise FileExistsError(f"Journal path already exists: {resolved_journal_path}")
    if resolved_run_dir.exists():
        raise FileExistsError(f"Run directory already exists: {resolved_run_dir}")

    resolved_journal_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_run_dir.mkdir(parents=True, exist_ok=False)
    resolved_journal_path.touch(exist_ok=False)

    journal = AppendOnlyJournal(resolved_journal_path)
    portfolio = PortfolioState(
        equity_usd=equity_usd,
        available_cash_usd=equity_usd,
    )
    kill_switch_context = KillSwitchContext()
    execution_router = ExecutionRouter()
    breakout_config = BreakoutSignalConfig()
    mean_reversion_config = MeanReversionSignalConfig()

    for candle_index in range(1, len(candles) + 1):
        candle_window = candles[:candle_index]
        proposals: list[TradeProposal] = []

        breakout_feature_lookback = breakout_config.lookback_candles + 1
        if len(candle_window) >= breakout_feature_lookback:
            breakout_features = build_feature_snapshot(
                candle_window,
                lookback_periods=breakout_feature_lookback,
            )
            breakout_regime = classify_regime(breakout_features)
            breakout_proposal = generate_breakout_proposal(
                candle_window,
                breakout_features,
                breakout_regime,
                breakout_config,
            )
            if breakout_proposal is not None:
                proposals.append(breakout_proposal)

        mean_reversion_feature_lookback = mean_reversion_config.lookback_candles + 1
        if len(candle_window) >= mean_reversion_feature_lookback:
            mean_reversion_features = build_feature_snapshot(
                candle_window,
                lookback_periods=mean_reversion_feature_lookback,
            )
            mean_reversion_regime = classify_regime(mean_reversion_features)
            mean_reversion_proposal = generate_mean_reversion_proposal(
                candle_window,
                mean_reversion_features,
                mean_reversion_regime,
                mean_reversion_config,
            )
            if mean_reversion_proposal is not None:
                proposals.append(mean_reversion_proposal)

        for proposal in proposals:
            risk_result = evaluate_trade_proposal(
                proposal,
                portfolio,
                settings,
                kill_switch_context=kill_switch_context,
            )

            if risk_result.decision.action is PolicyAction.ALLOW:
                report = execution_router.execute(risk_result)
                journal.append_many(
                    build_execution_events(resolved_run_id, proposal, risk_result, report)
                )
                alerts = generate_execution_alerts(report)
                journal.append_many(
                    _alert_events(
                        alerts,
                        run_id=resolved_run_id,
                        strategy_id=proposal.strategy_id,
                        symbol=proposal.symbol,
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

            journal.append_many(build_execution_events(resolved_run_id, proposal, risk_result))
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
                        proposal=proposal,
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
                        strategy_id=proposal.strategy_id,
                        symbol=proposal.symbol,
                        mode=settings.mode,
                    )
                )

    replay_result = replay_journal(resolved_journal_path)
    scorecard = replay_result.scorecard
    if not replay_result.events:
        scorecard = EvaluationScorecard(run_id=resolved_run_id, event_count=0)
    review_packet = build_review_packet(replay_result.events)
    operator_summary = _operator_summary(
        fixture_name=replay_fixture_path.name,
        scorecard=scorecard,
        review_packet=review_packet,
    )

    summary = {
        "run_id": resolved_run_id,
        "mode": settings.mode.value,
        "replay_path": str(replay_fixture_path),
        "journal_path": str(resolved_journal_path),
        "quality_issue_count": len(quality_issues),
        "scorecard": scorecard.model_dump(mode="json"),
        "review_packet": review_packet,
        "operator_summary": operator_summary,
    }
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    _write_operator_report(
        run_id=resolved_run_id,
        mode=settings.mode,
        replay_path=replay_fixture_path,
        report_path=report_path,
        quality_issue_count=len(quality_issues),
        scorecard=scorecard,
        review_packet=review_packet,
        operator_summary=operator_summary,
    )

    return PaperRunResult(
        run_id=resolved_run_id,
        replay_path=replay_fixture_path,
        journal_path=resolved_journal_path,
        summary_path=summary_path,
        report_path=report_path,
        scorecard=scorecard,
        review_packet=review_packet,
        operator_summary=operator_summary,
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
                "scorecard": result.scorecard.model_dump(mode="json"),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
