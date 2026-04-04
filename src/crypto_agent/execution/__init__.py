"""Paper execution simulator and order normalization."""

from crypto_agent.execution.models import ExecutionReport, PaperExecutionConfig
from crypto_agent.execution.order_normalizer import normalize_order_intent
from crypto_agent.execution.router import ExecutionRouter
from crypto_agent.execution.simulator import PaperExecutionSimulator

__all__ = [
    "ExecutionReport",
    "ExecutionRouter",
    "PaperExecutionConfig",
    "PaperExecutionSimulator",
    "normalize_order_intent",
]
