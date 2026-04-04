"""Deterministic monitoring and alerting for paper execution."""

from crypto_agent.monitoring.alerts import generate_execution_alerts, generate_kill_switch_alerts
from crypto_agent.monitoring.health import HealthSnapshot, build_health_snapshot
from crypto_agent.monitoring.models import AlertEvent, AlertSeverity

__all__ = [
    "AlertEvent",
    "AlertSeverity",
    "HealthSnapshot",
    "build_health_snapshot",
    "generate_execution_alerts",
    "generate_kill_switch_alerts",
]
