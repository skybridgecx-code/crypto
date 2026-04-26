# Phase 37J — Local Transport Consumer Workflow Contract (`cryp`)

## What Matters

This document aligns `cryp` with the shipped producer-side local transport contract in:

- `/Users/muhammadaatif/polymarket-arb/docs/PHASE_37I_LOCAL_TRANSPORT_WORKFLOW_CONTRACT.md`
- `/Users/muhammadaatif/polymarket-arb/docs/PHASE_37K_CROSS_REPO_CONTRACT_DRIFT_CHECKLIST.md` (cross-repo drift gate/checklist)

Scope is consumer-side docs only. No runtime behavior changes.

## Consumer Role

`cryp` acts as the local consumer of a producer-written transport request:

- input artifact: `handoff_request.json`
- producer system: `polymarket-arb`
- consumer system: `cryp`
- contract focus: local pickup plus execution-boundary intake review

`cryp` does not own producer packaging. `cryp` owns pickup receipt, intake boundary decision, and local archival.

## Canonical Local Paths (Consumer View)

Transport root is operator-configured:

- `TRANSPORT_ROOT=<absolute/local/path>`

For a specific `<correlation_id>/<attempt_id>` pair, `cryp` reads and writes only these canonical paths:

- inbound request (read):
  - `<TRANSPORT_ROOT>/inbound/<correlation_id>/<attempt_id>/handoff_request.json`
- pickup receipt (write):
  - `<TRANSPORT_ROOT>/pickup/<correlation_id>/<attempt_id>/cryp_pickup_receipt.json`
- boundary ack (write when accepted):
  - `<TRANSPORT_ROOT>/responses/<correlation_id>/<attempt_id>/<correlation_id>.execution_boundary_ack.json`
- boundary reject (write when rejected):
  - `<TRANSPORT_ROOT>/responses/<correlation_id>/<attempt_id>/<correlation_id>.execution_boundary_reject.json`
- archive location (write):
  - `<TRANSPORT_ROOT>/archive/<correlation_id>/<attempt_id>/...`

## Pickup and Review Boundary Behavior

For each attempt directory:

1. Read `handoff_request.json` from canonical inbound path.
2. Write exactly one pickup receipt at the canonical pickup path.
3. Preserve `correlation_id` and `idempotency_key` unchanged through intake.
4. Produce exactly one boundary response artifact per attempt:
   - ack: accepted for local execution review boundary
   - reject: failed boundary validation or contract checks
5. If reject:
   - stop; do not advance into runtime review/execution preparation
6. If ack:
   - continue only as bounded local execution review under existing `cryp` guardrails
7. Archive request, receipt, and boundary response under canonical archive path.

Boundary semantics:

- ack means `accepted_for_local_execution_review`
- reject means `rejected_for_local_execution_review`
- neither ack nor reject authorizes production live execution

## Required Consumer Artifacts

### Pickup receipt

Required fields:

- `contract_version` (`"37A.v1"`)
- `producer_system` (`"polymarket-arb"`)
- `consumer_system` (`"cryp"`)
- `correlation_id`
- `idempotency_key`
- `pickup_status` (`"picked_up_for_local_execution_review"`)
- `picked_up_at_epoch_ns`
- `pickup_operator`
- `source_handoff_request_path`

### Boundary response

Exactly one response artifact per attempt:

- ack artifact kind: `execution_boundary_intake_ack`
- reject artifact kind: `execution_boundary_intake_reject`

Reject responses must include:

- `reason_codes`
- `validation_error`

## Idempotency and Duplicate Handling

- idempotency tuple: `<run_id>:<updated_at_epoch_ns>:<operator_decision>`
- same `<correlation_id>/<attempt_id>` is the same attempt, not a new request
- duplicate pickup of the same attempt must not be treated as new work
- new `updated_at_epoch_ns` or decision produces a new `attempt_id` directory
- latest-attempt selection is operator policy, not automatic supersession

## Preserved Boundaries and Non-Goals

This Phase 37J consumer contract does not introduce:

- network transport
- auth, key exchange, DB, queue, worker, or scheduler
- automatic cross-repo orchestration
- production live execution expansion
- replacement of existing `cryp` runtime guardrails

This document aligns local intake boundary behavior only.

## Advisory External Confirmation (Forward-Paper Only)

Optional advisory context can be provided to forward-paper evaluation without changing
transport contract shape and without authoring executable trade parameters:

```bash
python -m crypto_agent.cli.forward_paper tests/fixtures/paper_candles_breakout_long.jsonl \
  --runtime-id phase-37j-advisory-demo \
  --execution-mode paper \
  --external-confirmation-path /absolute/path/external_confirmation.json
```

Deterministic advisory-proof command (proposal-level, no live/replay dependency):

```bash
pytest -q tests/unit/test_external_confirmation_deterministic_proof.py
```

OMEGA fixture seam-proof command (loader -> proposal evaluation seam):

```bash
pytest -q tests/unit/test_external_confirmation_deterministic_proof.py -k omega_fixture_loader_to_proposal_seam_proof
```

Advisory vs control forward-paper comparison command:

```bash
python -m crypto_agent.cli.forward_paper_compare \
  --advisory-run-id omega-advisory-btcusdt-us \
  --control-run-id omega-control-btcusdt-us \
  --runs-dir runs
```

Repeatable multi-symbol advisory/control experiment command:

```bash
python -m crypto_agent.cli.forward_paper_experiment \
  --symbols BTCUSDT ETHUSDT SOLUSDT \
  --symbol-advisory BTCUSDT=/absolute/path/btc_external_confirmation.json \
  --symbol-advisory ETHUSDT=/absolute/path/eth_external_confirmation.json \
  --symbol-advisory SOLUSDT=/absolute/path/sol_external_confirmation.json \
  --advisory-artifact-path /absolute/path/shared_fallback_external_confirmation.json \
  --binance-base-url https://api.binance.us \
  --run-id-prefix omega-us-phase37j \
  --session-interval-seconds 60 \
  --max-sessions 2 \
  --output-dir runs/advisory_control_experiments \
  --runs-dir runs
```

Paper-only lower-liquidity regime override example (diagnostic, defaults unchanged):

```bash
python -m crypto_agent.cli.forward_paper_experiment \
  --symbols BTCUSDT ETHUSDT SOLUSDT \
  --symbol-advisory BTCUSDT=/absolute/path/btc_external_confirmation.json \
  --symbol-advisory ETHUSDT=/absolute/path/eth_external_confirmation.json \
  --symbol-advisory SOLUSDT=/absolute/path/sol_external_confirmation.json \
  --binance-base-url https://api.binance.us \
  --run-id-prefix omega-btc-evidence-5 \
  --session-interval-seconds 60 \
  --max-sessions 10 \
  --execution-mode paper \
  --regime-liquidity-stress-dollar-volume-threshold 1000 \
  --output-dir runs/experiments \
  --runs-dir runs
```

Known-good Binance US live-input path command:

```bash
python -m crypto_agent.cli.forward_paper \
  --runtime-id phase-37j-binanceus-btcusdt \
  --market-source binance_spot \
  --live-symbol BTCUSDT \
  --live-interval 1m \
  --live-lookback-candles 8 \
  --feed-stale-after-seconds 120 \
  --max-sessions 1 \
  --execution-mode paper \
  --binance-base-url https://api.binance.us
```

Known-good Coinbase spot live-input probe (2 sessions, paper-only):

```bash
# Coinbase JWT auth for coinbase_spot uses coinbase-advanced-py official JWT helpers.
export COINBASE_API_KEY_NAME="organizations/<org_id>/apiKeys/<key_id>"
export COINBASE_API_KEY_SECRET="-----BEGIN EC PRIVATE KEY-----\n...\n-----END EC PRIVATE KEY-----"

python -m crypto_agent.cli.forward_paper \
  --runtime-id phase-37j-coinbase-btcusd-probe \
  --market-source coinbase_spot \
  --live-symbol BTC-USD \
  --live-interval 1m \
  --live-lookback-candles 8 \
  --feed-stale-after-seconds 120 \
  --max-sessions 2 \
  --execution-mode paper
```

Checked-in XRP discovery control baseline (default path, no advisory):

```bash
python -m crypto_agent.cli.forward_paper \
  --config config/paper_coinbase_xrp_discovery.yaml \
  --runtime-id coinbase-xrp-5m-control-baseline \
  --market-source coinbase_spot \
  --live-symbol XRP-USD \
  --live-interval 5m \
  --session-interval-seconds 300 \
  --max-sessions 4 \
  --execution-mode paper \
  --regime-liquidity-stress-dollar-volume-threshold 150000 \
  --breakout-min-average-dollar-volume 150000 \
  --mean-reversion-min-average-dollar-volume 150000 \
  --mean-reversion-max-atr-pct 0.00225
```

Tuned XRP discovery control candidate (paper-only, no advisory): use the same checked-in
baseline and lower only `mean_reversion.zscore_entry_threshold` from `2.0` to `1.75`.
This targets the repeated `zscore_below_entry_threshold` non-emit blocker without changing
liquidity thresholds, default strategy behavior, or execution authority.

```bash
python -m crypto_agent.cli.forward_paper \
  --config config/paper_coinbase_xrp_discovery.yaml \
  --runtime-id coinbase-xrp-5m-control-tuned-zscore \
  --market-source coinbase_spot \
  --live-symbol XRP-USD \
  --live-interval 5m \
  --session-interval-seconds 300 \
  --max-sessions 12 \
  --execution-mode paper \
  --regime-liquidity-stress-dollar-volume-threshold 150000 \
  --breakout-min-average-dollar-volume 150000 \
  --mean-reversion-min-average-dollar-volume 150000 \
  --mean-reversion-max-atr-pct 0.00225 \
  --mean-reversion-zscore-entry-threshold 1.75
```

Tuned XRP discovery liquidity candidate (paper-only, no advisory): use the same
checked-in baseline and lower discovery liquidity thresholds through the named
XRP liquidity preset. This aligns regime, proposal-generation, and downstream
`risk.min_average_dollar_volume_usd` to `50000.0` for this invocation only, while
keeping `mean_reversion.zscore_entry_threshold` at `2.0`.

```bash
python -m crypto_agent.cli.forward_paper \
  --config config/paper_coinbase_xrp_discovery.yaml \
  --runtime-id coinbase-xrp-5m-control-tuned-liquidity \
  --market-source coinbase_spot \
  --live-symbol XRP-USD \
  --live-interval 5m \
  --session-interval-seconds 300 \
  --max-sessions 12 \
  --execution-mode paper \
  --xrp-discovery-liquidity-tuning
```

Historical aligned-risk temp-config experiment (only needed when reproducing runs from
before `--xrp-discovery-liquidity-tuning` aligned the risk floor): copy the checked-in
XRP config to a temp file and change only `risk.min_average_dollar_volume_usd` from
`150000.0` to `50000.0`, then run the same liquidity-tuning command against that temp
config. Do not commit the temp config.

```bash
tmp_config="$(mktemp /tmp/paper_coinbase_xrp_discovery_aligned_risk.XXXXXX.yaml)"
cp config/paper_coinbase_xrp_discovery.yaml "$tmp_config"
python - <<'PY' "$tmp_config"
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(
    path.read_text(encoding="utf-8").replace(
        "min_average_dollar_volume_usd: 150000.0",
        "min_average_dollar_volume_usd: 50000.0",
    ),
    encoding="utf-8",
)
PY

python -m crypto_agent.cli.forward_paper \
  --config "$tmp_config" \
  --runtime-id coinbase-xrp-5m-control-tuned-liquidity-aligned-risk \
  --market-source coinbase_spot \
  --live-symbol XRP-USD \
  --live-interval 5m \
  --session-interval-seconds 300 \
  --max-sessions 12 \
  --execution-mode paper \
  --xrp-discovery-liquidity-tuning
```

Advisory for XRP discovery is optional/experimental (not default); only add when running an explicit A/B check:

```bash
.venv/bin/python -m crypto_agent.cli.forward_paper \
  --config config/paper_coinbase_xrp_discovery.yaml \
  --runtime-id poly-xrp-bridge-test-1 \
  --market-source coinbase_spot \
  --live-symbol XRP-USD \
  --live-interval 5m \
  --session-interval-seconds 300 \
  --max-sessions 4 \
  --execution-mode paper \
  --xrp-discovery-liquidity-tuning \
  --mean-reversion-max-atr-pct 0.00225 \
  --external-confirmation-path /Users/muhammadaatif/polymarket-arb/.tmp/cryp-xrp-bridge-demo/exports/xrp_external_confirmation.json
```

By default, the bridge loads and annotates emitted proposals with external confirmation
metadata. `boosted_confirmation` and `penalized_conflict` adjust proposal confidence, and
`vetoed_*` remains a hard advisory veto. Confidence is advisory metadata by default:
risk checks, sizing, and paper order approval do not otherwise size from confidence.

Optional conservative advisory-impact policy (paper-only, no live authority):

```bash
.venv/bin/python -m crypto_agent.cli.forward_paper \
  --config config/paper_coinbase_xrp_discovery.yaml \
  --runtime-id poly-xrp-bridge-test-1-conservative \
  --market-source coinbase_spot \
  --live-symbol XRP-USD \
  --live-interval 5m \
  --session-interval-seconds 300 \
  --max-sessions 4 \
  --execution-mode paper \
  --xrp-discovery-liquidity-tuning \
  --mean-reversion-max-atr-pct 0.00225 \
  --external-confirmation-path /Users/muhammadaatif/polymarket-arb/.tmp/cryp-xrp-bridge-demo/exports/xrp_external_confirmation.json \
  --external-confirmation-impact-policy conservative \
  --external-confirmation-boosted-size-multiplier 1.25
```

The conservative policy changes only paper replay/runtime behavior when the flag is
present:

- `penalized_conflict` blocks the proposal before risk/sizing/order submission.
- `boosted_confirmation` continues through the normal flow.
- `ignored_asset_mismatch` does not affect the proposal.
- `vetoed_conflict` or `vetoed_neutral` still hard-block the proposal.

The optional boosted sizing multiplier is also paper-only. It applies only to surviving
aligned proposals with `external_confirmation_applied=true` and
`external_confirmation_status=boosted_confirmation`. It does not apply to conflicts,
asset mismatches, vetoed proposals, or proposals without an external confirmation marker.
Existing risk, cash, exposure, and policy limits still cap the approved order notional.

The paired producer-side export command is:

```bash
cd /Users/muhammadaatif/polymarket-arb
scripts/export_xrp_cryp_bridge_demo.sh
```

Inspect the loaded artifact, per-run decision status, and outcome counts:

```bash
find runs \( \
  -path 'runs/poly-xrp-bridge-test-1/sessions/session-*.json' -o \
  -path 'runs/poly-xrp-bridge-test-1-session-*/summary.json' \
\) -print0 | xargs -0 rg -n '"external_confirmation"|"artifact_loaded"|"asset"|"source_system"|"decision_status_counts"|"proposal_count"|"orders_submitted_count"|"fill_event_count"|"session_outcome"|"message"'
```

Status interpretation:

- `boosted_confirmation`: the advisory direction aligns with the proposal side.
- `penalized_conflict`: the advisory direction conflicts with the proposal side.
- `ignored_asset_mismatch`: the advisory asset differs from the proposal asset.
- `vetoed_conflict` or `vetoed_neutral`: `veto_trade=true` blocks the proposal.
- no decision statuses with `artifact_loaded=true`: bridge loaded, but the session emitted no proposals.

Generate the operator-facing external confirmation impact report for the proven XRP
policy run:

```bash
python -m crypto_agent.cli.forward_paper_external_confirmation_report \
  --run-id poly-xrp-bridge-impact-policy-1 \
  --runs-dir runs \
  --journals-dir journals
```

The report writes deterministic JSON and Markdown artifacts under
`runs/external_confirmation_reports/`. It summarizes whether the bridge artifact loaded,
which asset/source was applied, status counts for boosted, penalized, ignored, and vetoed
decisions, per-session external-confirmation drops, proposals, submitted orders, fills,
and the active external-confirmation impact policy.

Inspect per-session proposal-generation diagnostics for an executed forward-paper session:

```bash
cat runs/omega-btc-evidence-3-btcusdt-advisory/sessions/session-0001.proposal_generation_summary.json
```

Aggregate proposal-generation summaries across advisory/control run IDs:

```bash
python -m crypto_agent.cli.forward_paper_proposal_generation_report \
  --run-id omega-btc-5m-override-1-btcusdt-advisory \
  --run-id omega-btc-5m-override-1-btcusdt-control \
  --runs-dir runs
```

5m BTC paper probe with regime + mean-reversion liquidity + zscore overrides (paper-only):

```bash
python -m crypto_agent.cli.forward_paper_experiment \
  --symbols BTCUSDT \
  --symbol-advisory BTCUSDT=/absolute/path/btc_external_confirmation.json \
  --binance-base-url https://api.binance.us \
  --run-id-prefix omega-btc-5m-override-1 \
  --execution-mode paper \
  --live-interval 5m \
  --session-interval-seconds 300 \
  --max-sessions 2 \
  --regime-liquidity-stress-dollar-volume-threshold 1000 \
  --mean-reversion-min-average-dollar-volume 2500 \
  --mean-reversion-zscore-entry-threshold 1.5 \
  --output-dir runs/experiments \
  --runs-dir runs
```

Aggregate live market-state regimes/features across advisory/control run IDs:

```bash
python -m crypto_agent.cli.forward_paper_market_state_report \
  --run-id omega-btc-evidence-5-btcusdt-advisory \
  --run-id omega-btc-evidence-5-btcusdt-control \
  --runs-dir runs
```
