from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_agent.cli.main import main
from crypto_agent.events.journal import AppendOnlyJournal

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


def _write_paper_config(
    tmp_path: Path,
    *,
    policy_overrides: dict[str, object] | None = None,
) -> Path:
    policy = {
        "allow_live_orders": False,
        "require_manual_approval_above_notional_usd": 1000.0,
        "kill_switch_enabled": True,
        "max_consecutive_order_rejects": 3,
        "max_slippage_breaches": 2,
        "max_drawdown_fraction": 0.03,
    }
    if policy_overrides is not None:
        policy.update(policy_overrides)

    config_path = tmp_path / "paper_test.yaml"
    config_path.write_text(
        "\n".join(
            [
                "mode: paper",
                "paths:",
                f"  runs_dir: {tmp_path / 'runs'}",
                f"  journals_dir: {tmp_path / 'journals'}",
                "venue:",
                "  default_venue: paper",
                "  allowed_symbols:",
                "    - BTCUSDT",
                "    - ETHUSDT",
                "  quote_currency: USDT",
                "risk:",
                "  risk_per_trade_fraction: 0.005",
                "  max_portfolio_gross_exposure: 1.0",
                "  max_symbol_gross_exposure: 0.4",
                "  max_daily_realized_loss: 0.015",
                "  max_open_positions: 2",
                "  max_leverage: 1.0",
                "  max_spread_bps: 12.0",
                "  max_expected_slippage_bps: 15.0",
                "  min_average_dollar_volume_usd: 5000000.0",
                "policy:",
                f"  allow_live_orders: {'true' if policy['allow_live_orders'] else 'false'}",
                "  require_manual_approval_above_notional_usd: "
                f"{policy['require_manual_approval_above_notional_usd']}",
                f"  kill_switch_enabled: {'true' if policy['kill_switch_enabled'] else 'false'}",
                f"  max_consecutive_order_rejects: {policy['max_consecutive_order_rejects']}",
                f"  max_slippage_breaches: {policy['max_slippage_breaches']}",
                f"  max_drawdown_fraction: {policy['max_drawdown_fraction']}",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    return json.loads((SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8"))


def _normalize_summary(
    summary: dict[str, object],
    *,
    run_id: str,
) -> dict[str, object]:
    normalized = dict(summary)
    normalized["journal_path"] = f"journals/{run_id}.jsonl"
    return normalized


@pytest.mark.parametrize(
    ("fixture_name", "run_id", "snapshot_name"),
    [
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-paper-run",
            "paper_run_breakout_long.summary.snapshot.json",
        ),
        (
            "paper_candles_mean_reversion_short.jsonl",
            "mean-reversion-paper-run",
            "paper_run_mean_reversion.summary.snapshot.json",
        ),
    ],
)
def test_cli_paper_run_summary_snapshots_and_journal_shape(
    tmp_path: Path,
    capsys,
    fixture_name: str,
    run_id: str,
    snapshot_name: str,
) -> None:
    config_path = _write_paper_config(tmp_path)

    exit_code = main(
        [
            str(FIXTURES_DIR / fixture_name),
            "--config",
            str(config_path),
            "--run-id",
            run_id,
        ]
    )
    output = json.loads(capsys.readouterr().out)
    journal_path = Path(str(output["journal_path"]))
    summary_path = Path(str(output["summary_path"]))

    assert exit_code == 0
    assert journal_path.exists()
    assert summary_path.exists()

    journal = AppendOnlyJournal(journal_path)
    events = journal.read_all()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert _normalize_summary(summary, run_id=run_id) == _load_snapshot(snapshot_name)
    assert summary["scorecard"] == output["scorecard"]
    assert len(events) == int(summary["scorecard"]["event_count"])
    assert events[0].event_type.value == "trade.proposal.created"
    assert events[-1].event_type.value == "alert.raised"
    assert [event.event_type.value for event in events] == list(
        summary["review_packet"]["event_types"]
    )


@pytest.mark.parametrize(
    (
        "fixture_name",
        "run_id",
        "snapshot_name",
        "equity_usd",
        "policy_overrides",
        "expected_event_types",
        "expected_order_reject_count",
        "expected_halt_count",
        "expected_alert_count",
        "expected_partial_fill_count",
    ),
    [
        (
            "paper_candles_high_volatility.jsonl",
            "high-vol-no-signal-paper-run",
            "paper_run_high_vol_no_signal.summary.snapshot.json",
            100_000.0,
            None,
            [],
            0,
            0,
            0,
            0,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-reject-low-equity-paper-run",
            "paper_run_breakout_reject_low_equity.summary.snapshot.json",
            1.0,
            None,
            [
                "trade.proposal.created",
                "risk.check.completed",
                "policy.decision.made",
                "order.intent.created",
                "order.submitted",
                "order.rejected",
                "alert.raised",
            ],
            1,
            0,
            1,
            0,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-halt-drawdown-zero-paper-run",
            "paper_run_breakout_halt_drawdown_zero.summary.snapshot.json",
            100_000.0,
            {"max_drawdown_fraction": 0.0},
            [
                "trade.proposal.created",
                "risk.check.completed",
                "policy.decision.made",
                "kill_switch.activated",
                "alert.raised",
            ],
            0,
            1,
            1,
            0,
        ),
    ],
)
def test_cli_paper_run_adverse_summary_snapshots_and_event_flags(
    tmp_path: Path,
    capsys,
    fixture_name: str,
    run_id: str,
    snapshot_name: str,
    equity_usd: float,
    policy_overrides: dict[str, object] | None,
    expected_event_types: list[str],
    expected_order_reject_count: int,
    expected_halt_count: int,
    expected_alert_count: int,
    expected_partial_fill_count: int,
) -> None:
    config_path = _write_paper_config(tmp_path, policy_overrides=policy_overrides)

    exit_code = main(
        [
            str(FIXTURES_DIR / fixture_name),
            "--config",
            str(config_path),
            "--run-id",
            run_id,
            "--equity-usd",
            str(equity_usd),
        ]
    )
    output = json.loads(capsys.readouterr().out)
    journal_path = Path(str(output["journal_path"]))
    summary_path = Path(str(output["summary_path"]))

    assert exit_code == 0
    assert journal_path.exists()
    assert summary_path.exists()

    journal = AppendOnlyJournal(journal_path)
    events = journal.read_all()
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert _normalize_summary(summary, run_id=run_id) == _load_snapshot(snapshot_name)
    assert len(events) == int(summary["scorecard"]["event_count"])
    assert [event.event_type.value for event in events] == expected_event_types
    assert summary["scorecard"]["order_reject_count"] == expected_order_reject_count
    assert summary["scorecard"]["halt_count"] == expected_halt_count
    assert summary["operator_summary"]["alert_count"] == expected_alert_count
    assert summary["scorecard"]["partial_fill_intent_count"] == expected_partial_fill_count
