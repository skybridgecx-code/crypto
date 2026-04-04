"""Operator-facing CLI helpers."""

from crypto_agent.cli.main import PaperRunResult, main, run_paper_replay
from crypto_agent.cli.matrix import (
    PaperRunMatrixCase,
    PaperRunMatrixEntry,
    PaperRunMatrixManifest,
    run_paper_replay_matrix,
)

__all__ = [
    "PaperRunMatrixCase",
    "PaperRunMatrixEntry",
    "PaperRunMatrixManifest",
    "PaperRunResult",
    "main",
    "run_paper_replay",
    "run_paper_replay_matrix",
]
