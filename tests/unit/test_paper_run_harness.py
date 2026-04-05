from __future__ import annotations

import json
from pathlib import Path

from crypto_agent.cli.main import main, run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal

FIXTURES_DIR = Path("tests/fixtures")


def _paper_settings_for(tmp_path: Path):
    settings = load_settings(Path("config/paper.yaml"))
    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "runs_dir": tmp_path / "runs",
                    "journals_dir": tmp_path / "journals",
                }
            )
        }
    )


def test_run_paper_replay_writes_journal_and_summary_for_breakout_fixture(
    tmp_path: Path,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="breakout-paper-run",
    )

    replay_result = replay_journal(result.journal_path)
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))

    assert result.journal_path.exists()
    assert result.summary_path.exists()
    assert result.report_path.exists()
    assert replay_result.scorecard.run_id == "breakout-paper-run"
    assert replay_result.scorecard.proposal_count == 1
    assert replay_result.scorecard.approval_count == 1
    assert replay_result.scorecard.order_intent_count == 1
    assert replay_result.scorecard.fill_event_count == 2
    assert replay_result.scorecard.partial_fill_intent_count == 1
    assert summary["scorecard"] == replay_result.scorecard.model_dump(mode="json")
    assert summary["pnl"] == result.pnl.model_dump(mode="json")
    assert summary["review_packet"] == result.review_packet
    assert summary["operator_summary"] == result.operator_summary


def test_cli_main_runs_mean_reversion_fixture_and_prints_summary(
    tmp_path: Path,
    capsys,
) -> None:
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

    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_mean_reversion_short.jsonl"),
            "--config",
            str(config_path),
            "--run-id",
            "mean-reversion-paper-run",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["run_id"] == "mean-reversion-paper-run"
    assert Path(output["journal_path"]).exists()
    assert Path(output["summary_path"]).exists()
    assert Path(output["report_path"]).exists()
    assert output["pnl"]["starting_equity_usd"] == 100000.0
    assert output["scorecard"]["proposal_count"] == 1
    assert output["scorecard"]["approval_count"] == 1
    assert output["scorecard"]["order_intent_count"] == 1
