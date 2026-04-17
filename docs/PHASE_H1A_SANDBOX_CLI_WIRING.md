# Phase H1A — Sandbox CLI Wiring

## Status

Phase H1A wires the existing sandbox execution adapter path into the CLI so bounded sandbox rehearsals can run through the normal forward runtime.

This phase does not add production live execution, live order authority, a new execution mode, strategy changes, risk changes, or account-state trust widening.

## Finding

The runtime already supported sandbox_execution_adapter, and unit tests already covered sandbox execution when an adapter was passed directly.

The CLI did not pass a sandbox adapter, so sandbox CLI rehearsal failed with:

```text
ValueError: Sandbox execution mode requires an explicit sandbox adapter.
```

## Change

src/crypto_agent/cli/forward_paper.py now builds a deterministic ScriptedSandboxExecutionAdapter when --execution-mode sandbox is selected.

The adapter is explicitly sandbox-only:

- sandbox=True
- scripted sandbox acknowledgements
- scripted terminal filled sandbox states
- no production live order transmission
- no live execution authority

## Rehearsal result

The CLI sandbox rehearsal completed and wrote normal runtime artifacts, including live_launch_verdict.json and session execution request/result/status artifacts.

The launch verdict was correctly not_launchable_here_now.

Expected reason codes included preflight_missing, shadow_canary_not_passed, not_shadow_live_runtime, readiness threshold failures, insufficient evidence, and live_gate_state_not_ready.

This is expected for a sandbox-only rehearsal without the full preflight -> canary -> longer shadow evidence workflow.

## Present-flag fix

The rehearsal exposed that live_launch_verdict.json input artifact present flags could be false for artifacts built in memory before being written to disk.

The verdict now marks these materialized in-memory artifacts as present during verdict construction:

- shadow_canary_evaluation
- live_gate_threshold_summary
- live_gate_decision

The rerun confirmed all three now show present: true.

## Important limitation

This rehearsal produced zero sandbox execution requests because the session generated no executable order intents.

H1A proves CLI sandbox mode no longer fails at adapter wiring, sandbox-mode runtime artifacts are generated, and launch verdict metadata is consistent for materialized gate artifacts.

H1A does not prove filled sandbox order behavior from the CLI. That should remain a separate bounded phase if needed.

## Boundary confirmation

No production live execution was added.

No new execution mode was added.

No trusted account state was widened.

No strategy, risk, or execution policy was rewritten.

No second accounting system was added.
