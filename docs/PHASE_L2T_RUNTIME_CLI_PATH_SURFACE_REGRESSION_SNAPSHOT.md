# Phase L2T — Runtime CLI Path Surface Regression Snapshot

## What Changed

Phase L2T adds deterministic regression coverage for forward-paper CLI path output fields.

Added coverage:

- snapshot of normalized CLI path output fields from `crypto-agent-forward-paper-run`
- explicit inclusion of `live_gate_config_path` in the frozen CLI path-surface contract

## Scope

In scope:

- tests and snapshot fixture only
- phase bookkeeping update

Out of scope:

- no runtime behavior changes
- no gate logic changes
- no strategy, risk, or execution changes

## Operator Contract

- CLI path output remains an operator convenience view that must stay aligned with canonical runtime status surfaces.
- L2T locks this path contract against silent drift.
