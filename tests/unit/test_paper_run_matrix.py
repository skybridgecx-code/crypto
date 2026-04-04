from __future__ import annotations

import json
from pathlib import Path

from crypto_agent.cli.matrix import main, run_paper_replay_matrix
from crypto_agent.config import load_settings

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


def test_run_paper_replay_matrix_writes_manifest_and_per_run_artifacts(
    tmp_path: Path,
) -> None:
    manifest = run_paper_replay_matrix(
        settings=_paper_settings_for(tmp_path),
        matrix_run_id="paper-run-matrix-demo",
    )

    manifest_path = Path(manifest.manifest_path)
    manifest_payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries_by_suffix = {
        entry.run_id.removeprefix("paper-run-matrix-demo-"): entry for entry in manifest.entries
    }

    assert manifest_path.exists()
    assert manifest.entry_count == 5
    assert manifest_payload == manifest.model_dump(mode="json")
    assert set(entries_by_suffix) == {
        "breakout-paper-run",
        "mean-reversion-paper-run",
        "high-vol-no-signal-paper-run",
        "breakout-reject-low-equity-paper-run",
        "breakout-halt-drawdown-zero-paper-run",
    }
    assert all(Path(entry.journal_path).exists() for entry in manifest.entries)
    assert all(Path(entry.summary_path).exists() for entry in manifest.entries)
    assert manifest.aggregate_counts["proposal_count"] == sum(
        entry.outcome_counts["proposal_count"] for entry in manifest.entries
    )
    assert entries_by_suffix["breakout-paper-run"].outcome_counts["partial_fill_intent_count"] == 1
    assert entries_by_suffix["mean-reversion-paper-run"].outcome_counts["fill_event_count"] == 2
    assert entries_by_suffix["high-vol-no-signal-paper-run"].outcome_counts["event_count"] == 0
    assert (
        entries_by_suffix["breakout-reject-low-equity-paper-run"].outcome_counts[
            "order_reject_count"
        ]
        == 1
    )
    assert (
        entries_by_suffix["breakout-halt-drawdown-zero-paper-run"].outcome_counts["halt_count"] == 1
    )


def test_cli_matrix_main_runs_default_fixture_matrix_and_prints_manifest(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_paper_config(tmp_path)

    exit_code = main(
        [
            "--config",
            str(config_path),
            "--matrix-run-id",
            "paper-run-matrix-cli",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    manifest_path = Path(output["manifest_path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert exit_code == 0
    assert manifest_path.exists()
    assert output["matrix_run_id"] == "paper-run-matrix-cli"
    assert output["entry_count"] == 5
    assert output["aggregate_counts"] == manifest["aggregate_counts"]
    assert manifest["entries"][0]["fixture"] == "paper_candles_breakout_long.jsonl"
    assert manifest["entries"][1]["fixture"] == "paper_candles_mean_reversion_short.jsonl"
    assert manifest["entries"][2]["fixture"] == "paper_candles_high_volatility.jsonl"
