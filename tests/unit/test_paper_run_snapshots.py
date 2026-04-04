from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.main import main
from crypto_agent.events.journal import AppendOnlyJournal

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


def _write_paper_config(tmp_path: Path) -> Path:
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
                "  allow_live_orders: false",
                "  require_manual_approval_above_notional_usd: 1000.0",
                "  kill_switch_enabled: true",
                "  max_consecutive_order_rejects: 3",
                "  max_slippage_breaches: 2",
                "  max_drawdown_fraction: 0.03",
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
