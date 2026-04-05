from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings

FIXTURES_DIR = Path("tests/fixtures")


def _paper_settings_for(
    tmp_path: Path,
    *,
    policy_overrides: dict[str, object] | None = None,
):
    settings = load_settings(Path("config/paper.yaml"))
    policy = settings.policy
    if policy_overrides is not None:
        policy = policy.model_copy(update=policy_overrides)
    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "runs_dir": tmp_path / "runs",
                    "journals_dir": tmp_path / "journals",
                }
            ),
            "policy": policy,
        }
    )


@pytest.mark.parametrize(
    (
        "fixture_name",
        "run_id",
        "equity_usd",
        "policy_overrides",
        "expected_row_count",
        "expected_status",
    ),
    [
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-filled-paper-run",
            1_000.0,
            None,
            1,
            "filled",
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-partial-paper-run",
            100_000.0,
            None,
            1,
            "partial",
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-reject-paper-run",
            1.0,
            None,
            1,
            "rejected",
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-halt-paper-run",
            100_000.0,
            {"max_drawdown_fraction": 0.0},
            1,
            "halted",
        ),
        (
            "paper_candles_high_volatility.jsonl",
            "high-vol-no-signal-paper-run",
            100_000.0,
            None,
            0,
            None,
        ),
    ],
)
def test_single_run_trade_ledger_artifact(
    tmp_path: Path,
    fixture_name: str,
    run_id: str,
    equity_usd: float,
    policy_overrides: dict[str, object] | None,
    expected_row_count: int,
    expected_status: str | None,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / fixture_name,
        settings=_paper_settings_for(tmp_path, policy_overrides=policy_overrides),
        run_id=run_id,
        equity_usd=equity_usd,
    )

    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    ledger = json.loads(result.trade_ledger_path.read_text(encoding="utf-8"))
    report = result.report_path.read_text(encoding="utf-8")

    assert result.trade_ledger_path.exists()
    assert summary["trade_ledger_path"] == str(result.trade_ledger_path)
    assert f"trade_ledger_path: runs/{run_id}/trade_ledger.json" in report
    assert ledger["run_id"] == run_id
    assert ledger["row_count"] == expected_row_count
    assert len(ledger["rows"]) == expected_row_count

    if expected_status is None:
        assert ledger["rows"] == []
        return

    row = ledger["rows"][0]
    assert row["proposal_id"]
    assert row["symbol"] == "BTCUSDT"
    assert row["side"] == "buy"
    assert row["strategy_id"] == "breakout_v1"
    assert row["ending_status"] == expected_status

    if expected_status == "filled":
        assert row["intent_id"] is not None
        assert row["filled_size"] > 0
        assert row["average_fill_price"] is not None
        assert row["total_fee_usd"] > 0
        assert row["gross_realized_pnl_usd"] == pytest.approx(0.0)
        assert row["net_realized_pnl_usd"] == pytest.approx(-row["total_fee_usd"])
    elif expected_status == "partial":
        assert row["intent_id"] is not None
        assert row["filled_size"] > 0
        assert row["average_fill_price"] is not None
        assert row["total_fee_usd"] > 0
        assert row["gross_realized_pnl_usd"] == pytest.approx(0.0)
        assert row["net_realized_pnl_usd"] == pytest.approx(-row["total_fee_usd"])
    elif expected_status == "rejected":
        assert row["intent_id"] is not None
        assert row["filled_size"] == pytest.approx(0.0)
        assert row["average_fill_price"] is None
        assert row["total_fee_usd"] == pytest.approx(0.0)
        assert row["gross_realized_pnl_usd"] == pytest.approx(0.0)
        assert row["net_realized_pnl_usd"] == pytest.approx(0.0)
    elif expected_status == "halted":
        assert row["intent_id"] is None
        assert row["filled_size"] == pytest.approx(0.0)
        assert row["average_fill_price"] is None
        assert row["total_fee_usd"] == pytest.approx(0.0)
        assert row["gross_realized_pnl_usd"] == pytest.approx(0.0)
        assert row["net_realized_pnl_usd"] == pytest.approx(0.0)
