"""Deterministic trade proposal generators."""

from crypto_agent.signals.base import BreakoutSignalConfig, MeanReversionSignalConfig
from crypto_agent.signals.breakout import generate_breakout_proposal
from crypto_agent.signals.mean_reversion import generate_mean_reversion_proposal

__all__ = [
    "BreakoutSignalConfig",
    "MeanReversionSignalConfig",
    "generate_breakout_proposal",
    "generate_mean_reversion_proposal",
]
