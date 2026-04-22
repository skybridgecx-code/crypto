# Phase L2P — Live Gate Config Artifact Surface

## What Changed

Phase L2P adds one explicit persisted gate-config artifact:

- `runs/<runtime-id>/live_gate_config.json`

The runtime now writes this artifact during gate materialization and threads its path through the canonical forward-runtime surfaces.

## Scope

In scope:

- persist `live_gate_config.json` from the existing gate-config source path
- add `live_gate_config_path` to:
  - `ForwardPaperRuntimePaths`
  - `forward_paper_status.json` / runtime status model
  - forward runtime registry entries
  - forward runtime result / CLI output shared fields
- update operator docs for the new artifact

Out of scope:

- no gate-threshold logic changes
- no strategy, signal, risk, or execution behavior changes
- no new execution mode
- no live-authority widening

## Operator Contract

- `live_gate_config.json` is an input-evidence snapshot for gate decisions.
- `live_gate_threshold_summary.json` and `live_gate_decision.json` remain the decision surfaces.
- This phase adds traceability, not new authority.
