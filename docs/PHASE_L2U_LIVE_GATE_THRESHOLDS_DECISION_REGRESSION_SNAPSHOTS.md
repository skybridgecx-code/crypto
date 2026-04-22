# Phase L2U — Live Gate Thresholds and Decision Regression Snapshots

## What Changed

Phase L2U adds deterministic regression coverage for:

- `runs/<runtime-id>/live_gate_threshold_summary.json`
- `runs/<runtime-id>/live_gate_decision.json`

Added coverage:

- fixed-fixture snapshot for threshold-check payload semantics
- normalized-path snapshot for gate decision payload

## Scope

In scope:

- tests and snapshot fixtures only
- phase bookkeeping update

Out of scope:

- no runtime behavior changes
- no live gate logic changes
- no strategy, risk, or execution changes

## Operator Contract

- L2U locks the live-gate decision semantics and reason-code emission against silent drift.
