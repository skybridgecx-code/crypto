from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.enums import EventType
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.types import FillEvent

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


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


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    return json.loads((SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8"))


def _normalize_ledger(ledger: dict[str, object]) -> dict[str, object]:
    normalized = json.loads(json.dumps(ledger))
    rows = list(normalized["rows"])
    for index, row in enumerate(rows, start=1):
        row["proposal_id"] = f"proposal-{index}"
        if row["intent_id"] is not None:
            row["intent_id"] = f"intent-{index}"
    normalized["rows"] = rows
    return normalized


@pytest.mark.parametrize(
    (
        "fixture_name",
        "run_id",
        "equity_usd",
        "policy_overrides",
        "snapshot_name",
        "expected_status",
    ),
    [
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-filled-paper-run",
            1_000.0,
            None,
            "paper_run_breakout_filled.trade_ledger.snapshot.json",
            "filled",
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-partial-paper-run",
            100_000.0,
            None,
            "paper_run_breakout_partial.trade_ledger.snapshot.json",
            "partial",
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-reject-paper-run",
            1.0,
            None,
            "paper_run_breakout_reject.trade_ledger.snapshot.json",
            "rejected",
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-halt-paper-run",
            100_000.0,
            {"max_drawdown_fraction": 0.0},
            "paper_run_breakout_halt.trade_ledger.snapshot.json",
            "halted",
        ),
        (
            "paper_candles_high_volatility.jsonl",
            "high-vol-no-signal-paper-run",
            100_000.0,
            None,
            "paper_run_high_vol_no_signal.trade_ledger.snapshot.json",
            None,
        ),
    ],
)
def test_single_run_trade_ledger_snapshots_and_reconciliation(
    tmp_path: Path,
    fixture_name: str,
    run_id: str,
    equity_usd: float,
    policy_overrides: dict[str, object] | None,
    snapshot_name: str,
    expected_status: str | None,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / fixture_name,
        settings=_paper_settings_for(tmp_path, policy_overrides=policy_overrides),
        run_id=run_id,
        equity_usd=equity_usd,
    )

    replay_result = replay_journal(
        result.journal_path,
        replay_path=FIXTURES_DIR / fixture_name,
        starting_equity_usd=equity_usd,
    )
    summary = json.loads(result.summary_path.read_text(encoding="utf-8"))
    ledger = json.loads(result.trade_ledger_path.read_text(encoding="utf-8"))

    assert result.trade_ledger_path.exists()
    assert _normalize_ledger(ledger) == _load_snapshot(snapshot_name)
    assert ledger == result.trade_ledger.model_dump(mode="json")
    assert summary["trade_ledger_path"] == str(result.trade_ledger_path)
    assert replay_result.pnl is not None
    assert sum(row["total_fee_usd"] for row in ledger["rows"]) == pytest.approx(
        replay_result.pnl.total_fee_usd
    )
    assert sum(row["gross_realized_pnl_usd"] for row in ledger["rows"]) == pytest.approx(
        replay_result.pnl.gross_realized_pnl_usd
    )
    assert sum(row["net_realized_pnl_usd"] for row in ledger["rows"]) == pytest.approx(
        replay_result.pnl.net_realized_pnl_usd
    )

    if expected_status is None:
        assert ledger["row_count"] == 0
        assert ledger["rows"] == []
        assert replay_result.scorecard.event_count == 0
        assert replay_result.scorecard.proposal_count == 0
        return

    assert ledger["row_count"] == 1
    row = ledger["rows"][0]
    assert row["ending_status"] == expected_status

    if expected_status in {"filled", "partial"}:
        assert row["intent_id"] is not None
        fills = [
            FillEvent.model_validate(event.payload)
            for event in replay_result.events
            if event.event_type is EventType.ORDER_FILLED
            and str(event.payload["intent_id"]) == row["intent_id"]
        ]
        assert fills
        assert sum(fill.quantity for fill in fills) == pytest.approx(row["filled_size"])
        assert sum(fill.fee_usd for fill in fills) == pytest.approx(row["total_fee_usd"])
        assert sum(fill.notional_usd for fill in fills) / row["filled_size"] == pytest.approx(
            row["average_fill_price"]
        )
        saw_partial_fill = any(str(fill.status) == "partially_filled" for fill in fills)
        assert saw_partial_fill is (expected_status == "partial")
    elif expected_status == "rejected":
        assert row["intent_id"] is not None
        assert row["filled_size"] == pytest.approx(0.0)
        assert row["average_fill_price"] is None
        assert any(
            event.event_type is EventType.ORDER_REJECTED
            and str(event.payload["intent"]["intent_id"]) == row["intent_id"]
            for event in replay_result.events
        )
        assert not any(
            event.event_type is EventType.ORDER_FILLED
            and str(event.payload["intent_id"]) == row["intent_id"]
            for event in replay_result.events
        )
    elif expected_status == "halted":
        assert row["intent_id"] is None
        assert row["filled_size"] == pytest.approx(0.0)
        assert row["average_fill_price"] is None
        assert replay_result.scorecard.halt_count == 1
        assert not any(
            event.event_type
            in {
                EventType.ORDER_INTENT_CREATED,
                EventType.ORDER_SUBMITTED,
                EventType.ORDER_REJECTED,
                EventType.ORDER_FILLED,
            }
            for event in replay_result.events
        )
