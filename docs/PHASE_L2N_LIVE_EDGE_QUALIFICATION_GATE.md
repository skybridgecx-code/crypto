# Phase L2N — Live Edge Qualification Gate

## Status

Phase L2N adds bounded readiness qualification checks on top of the existing live-gate path.

This phase is intentionally narrow:
- no new execution modes
- no strategy logic changes
- no risk-policy widening
- no runtime authority widening

## Problem

A shadow session can be `executed` while producing zero normalized requests when the underlying paper run emits no order intents. That can satisfy some session-count checks while still providing weak launch evidence.

## What changed

L2N adds deterministic readiness checks using existing artifacts only:

- minimum shadow sessions with nonzero normalized requests
- minimum `would_send` shadow result count
- minimum cumulative net realized paper PnL floor
- minimum average return fraction floor

The gate remains fail-closed:
- if these checks fail, the gate state remains `not_ready`
- no live authority is enabled by these checks

## Operator meaning

`executed` still means the paper replay ran on healthy input.

Readiness now explicitly requires stronger edge evidence than session completion alone.

## Closeout conclusion

L2N hardens launch-readiness quality without changing execution behavior. It prevents session-count-only readiness from being misread as tradeable edge evidence.
