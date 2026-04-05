# Paper Run Operator Report

run_id: breakout-paper-run
mode: paper
fixture: paper_candles_breakout_long.jsonl
replay_path: tests/fixtures/paper_candles_breakout_long.jsonl
journal_path: journals/breakout-paper-run.jsonl
summary_path: runs/breakout-paper-run/summary.json
report_path: runs/breakout-paper-run/report.md
trade_ledger_path: runs/breakout-paper-run/trade_ledger.json
quality_issue_count: 0

## Event Counts
event_count: 8
alert_count: 1
kill_switch_activations: 0
review_rejected_event_count: 0
review_filled_event_count: 2
first_event_type: trade.proposal.created
last_event_type: alert.raised

## Scorecard
proposal_count: 1
approval_count: 1
denial_count: 0
halt_count: 0
order_intent_count: 1
orders_submitted_count: 1
order_reject_count: 0
fill_event_count: 2
filled_intent_count: 1
partial_fill_intent_count: 1
complete_execution_count: 1
incomplete_execution_count: 0
average_slippage_bps: 1.6883447292
max_slippage_bps: 1.6883447292
total_fill_notional_usd: 40006.7166727206
total_fee_usd: 8.0013433345

## PnL
starting_equity_usd: 100000
gross_realized_pnl_usd: 0
total_fee_usd: 8.0013433345
net_realized_pnl_usd: -8.0013433345
ending_unrealized_pnl_usd: -6.7533727206
ending_equity_usd: 99985.2452839449
return_fraction: -0.0001475472

## Review Packet
event_count: 8
filled_event_count: 2
rejected_event_count: 0
event_types: trade.proposal.created, risk.check.completed, policy.decision.made, order.intent.created, order.submitted, order.filled, order.filled, alert.raised

## Operator Summary
fixture: paper_candles_breakout_long.jsonl
run_id: breakout-paper-run
event_count: 8
proposal_count: 1
approval_count: 1
denial_count: 0
halt_count: 0
order_intent_count: 1
orders_submitted_count: 1
order_reject_count: 0
fill_event_count: 2
partial_fill_intent_count: 1
complete_execution_count: 1
incomplete_execution_count: 0
alert_count: 1
kill_switch_activations: 0
review_rejected_event_count: 0
review_filled_event_count: 2
first_event_type: trade.proposal.created
last_event_type: alert.raised
