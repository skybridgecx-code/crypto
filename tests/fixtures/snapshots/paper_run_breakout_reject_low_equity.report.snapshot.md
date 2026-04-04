# Paper Run Operator Report

run_id: breakout-reject-low-equity-paper-run
mode: paper
fixture: paper_candles_breakout_long.jsonl
replay_path: tests/fixtures/paper_candles_breakout_long.jsonl
journal_path: journals/breakout-reject-low-equity-paper-run.jsonl
summary_path: runs/breakout-reject-low-equity-paper-run/summary.json
report_path: runs/breakout-reject-low-equity-paper-run/report.md
quality_issue_count: 0

## Event Counts
event_count: 7
alert_count: 1
kill_switch_activations: 0
review_rejected_event_count: 1
review_filled_event_count: 0
first_event_type: trade.proposal.created
last_event_type: alert.raised

## Scorecard
proposal_count: 1
approval_count: 1
denial_count: 0
halt_count: 0
order_intent_count: 1
orders_submitted_count: 1
order_reject_count: 1
fill_event_count: 0
filled_intent_count: 0
partial_fill_intent_count: 0
complete_execution_count: 1
incomplete_execution_count: 0
average_slippage_bps: 0
max_slippage_bps: 0
total_fill_notional_usd: 0
total_fee_usd: 0

## Review Packet
event_count: 7
filled_event_count: 0
rejected_event_count: 1
event_types: trade.proposal.created, risk.check.completed, policy.decision.made, order.intent.created, order.submitted, order.rejected, alert.raised

## Operator Summary
fixture: paper_candles_breakout_long.jsonl
run_id: breakout-reject-low-equity-paper-run
event_count: 7
proposal_count: 1
approval_count: 1
denial_count: 0
halt_count: 0
order_intent_count: 1
orders_submitted_count: 1
order_reject_count: 1
fill_event_count: 0
partial_fill_intent_count: 0
complete_execution_count: 1
incomplete_execution_count: 0
alert_count: 1
kill_switch_activations: 0
review_rejected_event_count: 1
review_filled_event_count: 0
first_event_type: trade.proposal.created
last_event_type: alert.raised
