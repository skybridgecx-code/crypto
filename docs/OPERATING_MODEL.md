# Operating Model

## Objective

Build a risk-aware decision-support and execution system that can be trusted incrementally through replay, paper trading, and explicit operational controls.

## Decision Flow

1. Ingest normalized market and account data.
2. Compute feature state.
3. Classify regime.
4. Generate trade proposals.
5. Apply portfolio, risk, and policy checks.
6. Simulate or execute approved order intents.
7. Monitor health, exposure, fills, and anomalies.
8. Journal all decisions and outcomes.
9. Replay and review behavior against process rules.

## Modes

- `research_only`: proposals and scorecards only, no orders
- `paper`: simulated execution only, full journaling and monitoring
- `limited_live`: explicitly whitelisted, tightly capped, operator-aware
- `halted`: no new orders, monitoring and journaling continue

Default operating progression:

1. `research_only`
2. `paper`
3. `limited_live` only after evidence-based validation

Current validated baseline:

- replay, paper-simulator, monitoring, journaling, and evaluation paths are implemented
- the paper replay harness is the validated operator command path on top of those modules
- limited-live remains a documented control boundary, not an active validated operating mode
- trust is currently grounded in replay and simulation evidence, not exchange execution

## Control Boundaries

- LLMs may summarize, rank, and explain.
- Deterministic rules decide whether a trade is allowed.
- Risk logic decides maximum size and exposure.
- Execution logic decides order construction and retries.
- Policy can veto any action.
- Kill switch can halt new orders immediately.

## Failure Posture

- no hidden state
- no silent failures
- no destructive recovery behavior
- no exchange action without pre-trade checks
- no secret material in source control
