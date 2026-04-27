# Phase L2O — Edge Qualification Reason-Code Freeze

## Status

Phase L2O is docs-only.

It does not:
- change runtime code
- change tests
- change execution behavior
- widen strategy, risk, or launch policy scope

## Purpose

Phase L2N added stricter live-gate readiness checks for edge-quality evidence:

- nonzero-request shadow sessions
- shadow `would_send` count
- configurable PnL/return floors

L2O freezes the operator meaning of the new reason codes so launch verdict and gate triage stay explicit and auditable.

## Frozen reason-code additions

The operator reason-code map now explicitly includes:

- `insufficient_shadow_nonzero_request_sessions`
- `insufficient_shadow_would_send_requests`
- `cumulative_net_realized_pnl_below_floor`
- `average_return_fraction_below_floor`

These are readiness failures, not execution-authority signals.

## Operator interpretation

- `executed` sessions alone are still insufficient for launchability.
- launch readiness requires positive edge-evidence thresholds from the existing shadow/soak artifacts.
- failures remain fail-closed and artifact-driven.

## Closeout conclusion

L2O locks the reason-code/operator contract introduced by L2N so runtime gate failures can be interpreted consistently without widening authority.
