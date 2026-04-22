# Phase L2R — Runtime Status Index Regression Snapshot

## What Changed

Phase L2R adds deterministic regression coverage for canonical `forward_paper_status.json` index fields.

Added coverage:

- snapshot of normalized runtime index paths from `forward_paper_status.json`
- explicit inclusion of `live_gate_config_path` in the frozen status-index snapshot contract

## Scope

In scope:

- tests and snapshot fixture only
- phase bookkeeping update

Out of scope:

- no runtime behavior changes
- no gate logic changes
- no strategy, risk, or execution changes

## Operator Contract

- `forward_paper_status.json` remains the canonical per-runtime artifact index.
- L2R locks the index field-to-path contract against silent drift.
