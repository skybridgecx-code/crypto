# Harness Baseline

## What Matters

The paper replay harness is now the validated operator path on top of the frozen simulation-first baseline. Future operator-facing work should extend this path, not fork a second one.

## Operator Command Path

- console entrypoint: `crypto-agent-paper-run`
- module entrypoint: `crypto_agent.cli.main:main`
- core function: `crypto_agent.cli.main.run_paper_replay(...)`

Example:

```bash
crypto-agent-paper-run tests/fixtures/paper_candles_breakout_long.jsonl --config config/paper.yaml --run-id demo-paper-run
```

## Inputs

- replay candle fixture JSONL path
- paper-mode config path
- explicit or generated `run_id`
- optional starting `equity_usd`

The harness is validated only for `paper` mode and existing replay candle fixtures.

## Outputs

- append-only journal at `journals/<run-id>.jsonl`
- run summary at `runs/<run-id>/summary.json`
- replay-derived scorecard
- replay-derived review packet
- replay-derived operator summary

## Artifact Locations

- operator journal artifacts:
  - [journals](/Users/muhammadaatif/cryp/journals)
- operator run summaries:
  - [runs](/Users/muhammadaatif/cryp/runs)
- harness snapshot artifacts:
  - [tests/fixtures/snapshots](/Users/muhammadaatif/cryp/tests/fixtures/snapshots)

## Validated Fixture Matrix

Positive paths:

- `paper_candles_breakout_long.jsonl`
- `paper_candles_mean_reversion_short.jsonl`

Adverse paths:

- `paper_candles_high_volatility.jsonl`: no-signal / empty journal path
- `paper_candles_breakout_long.jsonl` with low equity: reject path
- `paper_candles_breakout_long.jsonl` with zero drawdown threshold: halt path

## Snapshot Surfaces

- summary artifact snapshots:
  - [tests/unit/test_paper_run_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_snapshots.py)
- replay-derived scorecard, review packet, and operator-summary snapshots:
  - [tests/unit/test_paper_run_replay_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_replay_snapshots.py)
- replay-derived event-count and event-sequence snapshots:
  - [tests/unit/test_paper_run_event_stream_snapshots.py](/Users/muhammadaatif/cryp/tests/unit/test_paper_run_event_stream_snapshots.py)

## Validation Command Path

- `make fix`
- `make format`
- `make lint`
- `make typecheck`
- `make test`
- `make validate`
- `make validate-check`

## Known Limits

- no live execution
- no exchange connectivity or reconciliation
- no second operator path
- harness outputs are deterministic control artifacts, not live-fill realism
- replay fixtures remain narrow and synthetic relative to real market conditions

## Non-Goals

- do not treat the harness as production trading infrastructure
- do not bypass the journal or replay path for operator outputs
- do not add UI, API, or live venue behavior under harness work unless explicitly assigned
