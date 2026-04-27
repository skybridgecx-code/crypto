# Phase L2Q — Live Gate Config Regression Snapshots

## What Changed

Phase L2Q adds regression coverage for the `live_gate_config.json` artifact introduced in L2P.

Added coverage:

- deterministic snapshot assertion for `runs/<runtime-id>/live_gate_config.json`
- explicit path reconciliation assertion:
  - `forward_paper_status.json.live_gate_config_path`
  - CLI output `live_gate_config_path`

## Scope

In scope:

- tests and snapshot fixture only
- phase bookkeeping update

Out of scope:

- no runtime behavior changes
- no live gate threshold/decision logic changes
- no strategy/risk/execution changes

## Operator Contract

- `live_gate_config.json` remains a persisted config-evidence artifact.
- L2Q locks deterministic payload shape and path threading so future refactors cannot silently drift operator surfaces.
