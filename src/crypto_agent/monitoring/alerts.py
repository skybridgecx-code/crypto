from __future__ import annotations

from datetime import UTC, datetime

from crypto_agent.config import Settings
from crypto_agent.execution.models import ExecutionReport
from crypto_agent.monitoring.models import AlertEvent, AlertSeverity
from crypto_agent.policy.kill_switch import KillSwitchContext, evaluate_kill_switch


def generate_execution_alerts(
    report: ExecutionReport,
    slippage_alert_bps: float = 3.0,
) -> list[AlertEvent]:
    alerts: list[AlertEvent] = []
    observed_at = report.fills[-1].timestamp if report.fills else datetime.now(UTC)

    if report.rejected:
        alerts.append(
            AlertEvent(
                code="order_rejected",
                severity=AlertSeverity.CRITICAL,
                message="Paper execution rejected the normalized order intent.",
                observed_at=observed_at,
                symbol=report.intent.symbol,
                details={
                    "intent_id": report.intent.intent_id,
                    "reject_reason": report.reject_reason or "unknown",
                },
            )
        )

    if report.estimated_slippage_bps >= slippage_alert_bps:
        alerts.append(
            AlertEvent(
                code="slippage_above_threshold",
                severity=AlertSeverity.WARNING,
                message="Estimated slippage exceeded the configured alert threshold.",
                observed_at=observed_at,
                symbol=report.intent.symbol,
                details={
                    "intent_id": report.intent.intent_id,
                    "estimated_slippage_bps": report.estimated_slippage_bps,
                },
            )
        )

    if any(fill.status.value == "partially_filled" for fill in report.fills):
        alerts.append(
            AlertEvent(
                code="partial_fill_detected",
                severity=AlertSeverity.INFO,
                message="Paper execution produced a partial fill sequence.",
                observed_at=observed_at,
                symbol=report.intent.symbol,
                details={
                    "intent_id": report.intent.intent_id,
                    "fill_count": len(report.fills),
                },
            )
        )

    return alerts


def generate_kill_switch_alerts(
    context: KillSwitchContext,
    settings: Settings,
    observed_at: datetime | None = None,
) -> list[AlertEvent]:
    state = evaluate_kill_switch(context, settings)
    if not state.active:
        return []

    when = observed_at or datetime.now(UTC)
    messages = {
        "manual_halt": ("manual_halt", AlertSeverity.CRITICAL, "Manual halt activated."),
        "missing_market_data_heartbeat": (
            "missing_market_data_heartbeat",
            AlertSeverity.CRITICAL,
            "Market data heartbeat is missing.",
        ),
        "position_mismatch": (
            "position_mismatch",
            AlertSeverity.CRITICAL,
            "Position state mismatched expected execution state.",
        ),
        "journal_write_failed": (
            "journal_write_failed",
            AlertSeverity.CRITICAL,
            "Append-only journal write failed.",
        ),
        "repeated_order_rejects": (
            "repeated_order_rejects",
            AlertSeverity.WARNING,
            "Repeated order rejects exceeded the configured threshold.",
        ),
        "slippage_breaches": (
            "slippage_breaches",
            AlertSeverity.WARNING,
            "Slippage breaches exceeded the configured threshold.",
        ),
        "drawdown_breach": (
            "drawdown_breach",
            AlertSeverity.CRITICAL,
            "Drawdown exceeded the configured threshold.",
        ),
    }

    alerts: list[AlertEvent] = []
    for reason in state.reason_codes:
        code, severity, message = messages[reason]
        alerts.append(
            AlertEvent(
                code=code,
                severity=severity,
                message=message,
                observed_at=when,
                details={"kill_switch_active": True},
            )
        )
    return alerts
