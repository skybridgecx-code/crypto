# Risk Policy

## Capital Preservation First

The system exists to preserve capital before it attempts to capture edge. Any ambiguous condition should resolve toward reduction, rejection, or halt.

## Hard Guards

- maximum portfolio gross exposure
- maximum symbol exposure
- maximum daily realized loss
- maximum open positions
- maximum leverage
- stale data veto
- missing balance veto
- duplicate order veto
- minimum liquidity threshold
- maximum spread threshold
- maximum expected slippage threshold

## Kill Switch Triggers

- repeated order rejections above threshold
- slippage breach
- drawdown breach
- missing market-data heartbeat
- position mismatch
- journal write failure
- manual operator halt

## Authority Model

- Signals propose.
- Risk resizes or rejects.
- Policy allows or denies.
- Execution follows approved intents only.
- LLM outputs are advisory and never override deterministic limits.

## Phase 1 Boundary

This file defines policy intent only. Guardrail implementation, invariants, and kill-switch behavior land in later phases and must be backed by tests before any increase in execution authority.
