from __future__ import annotations

from crypto_agent.enums import Mode
from crypto_agent.execution.models import ExecutionReport
from crypto_agent.execution.simulator import PaperExecutionSimulator
from crypto_agent.risk.checks import RiskCheckResult


class ExecutionRouter:
    def __init__(self, paper_simulator: PaperExecutionSimulator | None = None) -> None:
        self.paper_simulator = paper_simulator or PaperExecutionSimulator()

    def execute(self, risk_result: RiskCheckResult) -> ExecutionReport:
        if risk_result.decision.mode is not Mode.PAPER:
            raise ValueError("Phase 7 execution router supports paper mode only.")
        return self.paper_simulator.submit(risk_result)
