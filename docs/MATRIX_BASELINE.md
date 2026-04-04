# Matrix Baseline

## What Matters

The paper-run matrix is now the validated batch operator path on top of the frozen single-run harness. Future batch operator work should extend this path, not create a second batch runner.

## Operator Command Path

- console entrypoint: `crypto-agent-paper-matrix-run`
- module entrypoint: `crypto_agent.cli.matrix:main`
- core function: `crypto_agent.cli.matrix.run_paper_replay_matrix(...)`

Example:

```bash
crypto-agent-paper-matrix-run --config config/paper.yaml --matrix-run-id demo-paper-matrix
```

## Fixed Matrix Cases

- `paper_candles_breakout_long.jsonl`: positive breakout fill path
- `paper_candles_mean_reversion_short.jsonl`: positive mean-reversion fill path
- `paper_candles_high_volatility.jsonl`: no-signal / empty journal path
- `paper_candles_breakout_long.jsonl` with `equity_usd=1.0`: reject path
- `paper_candles_breakout_long.jsonl` with `max_drawdown_fraction=0.0`: halt path

## Manifest Inputs And Outputs

Inputs:

- paper-mode config path
- optional explicit `matrix_run_id`
- the existing fixed five-case fixture matrix

Outputs:

- normal per-run journals at `journals/<run-id>.jsonl`
- normal per-run summaries at `runs/<run-id>/summary.json`
- aggregate manifest at `runs/<matrix-run-id>/manifest.json`

The manifest records:

- fixture
- run id
- journal path
- summary path
- top-level outcome counts derived from existing summary surfaces

## Artifact Locations

- per-run journals:
  - [journals](/Users/muhammadaatif/cryp/journals)
- per-run summaries:
  - [runs](/Users/muhammadaatif/cryp/runs)
- checked-in matrix snapshots:
  - [tests/fixtures/snapshots](/Users/muhammadaatif/cryp/tests/fixtures/snapshots)

## Validated Snapshot Surfaces

- matrix manifest snapshots:
  - [tests/unit/test_paper_run_matrix_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_snapshots.py)
- matrix replay-aggregate snapshots rebuilt from manifest-referenced journals:
  - [tests/unit/test_paper_run_matrix_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_matrix_replay_snapshots.py)

## Validation Command Path

- `make validate`
- `make validate-check`

## Known Limits

- fixed five-case matrix only
- sequential local execution only
- no live execution
- no second batch runner
- batch outputs remain deterministic control artifacts, not live execution evidence

## Non-Goals

- do not treat the matrix runner as a scheduler, orchestrator, or production job system
- do not bypass the existing single-run harness, journal path, or replay path
- do not add API, UI, or live venue behavior under matrix work unless explicitly assigned
