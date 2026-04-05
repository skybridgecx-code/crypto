from __future__ import annotations

import json
from math import fsum
from pathlib import Path

import pytest
from crypto_agent.cli.matrix import run_paper_replay_matrix
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal


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


def test_matrix_trade_ledger_artifact_and_reconciliation(tmp_path: Path) -> None:
    manifest = run_paper_replay_matrix(
        settings=_paper_settings_for(tmp_path),
        matrix_run_id="paper-run-matrix-demo",
    )

    manifest_payload = json.loads(Path(manifest.manifest_path).read_text(encoding="utf-8"))
    matrix_trade_ledger_path = Path(manifest.matrix_trade_ledger_path)
    matrix_trade_ledger = json.loads(matrix_trade_ledger_path.read_text(encoding="utf-8"))
    report = Path(manifest.manifest_path).with_name("report.md").read_text(encoding="utf-8")

    assert matrix_trade_ledger_path.exists()
    assert (
        f"matrix_trade_ledger_path: runs/{manifest.matrix_run_id}/matrix_trade_ledger.json"
        in report
    )
    assert matrix_trade_ledger["matrix_run_id"] == manifest.matrix_run_id
    assert matrix_trade_ledger["row_count"] == len(matrix_trade_ledger["rows"])

    rows_by_run_id: dict[str, list[dict[str, object]]] = {}
    for row in matrix_trade_ledger["rows"]:
        rows_by_run_id.setdefault(str(row["run_id"]), []).append(row)

    expected_row_count = 0
    aggregate_fee_usd = 0.0
    aggregate_gross_realized_pnl_usd = 0.0
    aggregate_net_realized_pnl_usd = 0.0

    for raw_entry in manifest_payload["entries"]:
        entry = dict(raw_entry)
        run_id = str(entry["run_id"])
        summary = json.loads(Path(str(entry["summary_path"])).read_text(encoding="utf-8"))
        single_run_ledger = json.loads(
            Path(str(summary["trade_ledger_path"])).read_text(encoding="utf-8")
        )
        replay_result = replay_journal(
            str(entry["journal_path"]),
            replay_path=str(summary["replay_path"]),
            starting_equity_usd=float(summary["pnl"]["starting_equity_usd"]),
        )
        replay_pnl = replay_result.pnl
        assert replay_pnl is not None

        run_rows = rows_by_run_id.get(run_id, [])
        expected_row_count += max(1, int(single_run_ledger["row_count"]))

        if int(single_run_ledger["row_count"]) == 0:
            assert len(run_rows) == 1
            row = run_rows[0]
            assert row["ending_status"] == "no_signal"
            assert row["proposal_id"] is None
            assert row["symbol"] is None
            assert row["side"] is None
            assert row["strategy_id"] is None
            assert row["intent_id"] is None
            assert row["filled_size"] == pytest.approx(0.0)
            assert row["average_fill_price"] is None
            assert row["total_fee_usd"] == pytest.approx(0.0)
            assert row["gross_realized_pnl_usd"] == pytest.approx(0.0)
            assert row["net_realized_pnl_usd"] == pytest.approx(0.0)
        else:
            assert len(run_rows) == int(single_run_ledger["row_count"])
            for row, single_row in zip(run_rows, single_run_ledger["rows"], strict=True):
                assert row["proposal_id"] == single_row["proposal_id"]
                assert row["symbol"] == single_row["symbol"]
                assert row["side"] == single_row["side"]
                assert row["strategy_id"] == single_row["strategy_id"]
                assert row["intent_id"] == single_row["intent_id"]
                assert row["filled_size"] == pytest.approx(single_row["filled_size"])
                if single_row["average_fill_price"] is None:
                    assert row["average_fill_price"] is None
                else:
                    assert row["average_fill_price"] == pytest.approx(
                        single_row["average_fill_price"]
                    )
                assert row["total_fee_usd"] == pytest.approx(single_row["total_fee_usd"])
                assert row["gross_realized_pnl_usd"] == pytest.approx(
                    single_row["gross_realized_pnl_usd"]
                )
                assert row["net_realized_pnl_usd"] == pytest.approx(
                    single_row["net_realized_pnl_usd"]
                )
                assert row["ending_status"] == single_row["ending_status"]

        run_fee_usd = fsum(float(row["total_fee_usd"]) for row in run_rows)
        run_gross_realized_pnl_usd = fsum(float(row["gross_realized_pnl_usd"]) for row in run_rows)
        run_net_realized_pnl_usd = fsum(float(row["net_realized_pnl_usd"]) for row in run_rows)

        assert run_fee_usd == pytest.approx(replay_pnl.total_fee_usd)
        assert run_gross_realized_pnl_usd == pytest.approx(replay_pnl.gross_realized_pnl_usd)
        assert run_net_realized_pnl_usd == pytest.approx(replay_pnl.net_realized_pnl_usd)

        aggregate_fee_usd += run_fee_usd
        aggregate_gross_realized_pnl_usd += run_gross_realized_pnl_usd
        aggregate_net_realized_pnl_usd += run_net_realized_pnl_usd

    assert matrix_trade_ledger["row_count"] == expected_row_count
    assert {row["ending_status"] for row in matrix_trade_ledger["rows"]} == {
        "halted",
        "no_signal",
        "partial",
        "rejected",
    }
    assert sum(1 for row in matrix_trade_ledger["rows"] if float(row["filled_size"]) > 0) == 2
    assert sum(1 for row in matrix_trade_ledger["rows"] if row["ending_status"] == "partial") == 2
    assert sum(1 for row in matrix_trade_ledger["rows"] if row["ending_status"] == "rejected") == 1
    assert sum(1 for row in matrix_trade_ledger["rows"] if row["ending_status"] == "halted") == 1
    assert sum(1 for row in matrix_trade_ledger["rows"] if row["ending_status"] == "no_signal") == 1
    assert fsum(float(row["total_fee_usd"]) for row in matrix_trade_ledger["rows"]) == (
        pytest.approx(aggregate_fee_usd)
    )
    assert fsum(
        float(row["gross_realized_pnl_usd"]) for row in matrix_trade_ledger["rows"]
    ) == pytest.approx(aggregate_gross_realized_pnl_usd)
    assert fsum(
        float(row["net_realized_pnl_usd"]) for row in matrix_trade_ledger["rows"]
    ) == pytest.approx(aggregate_net_realized_pnl_usd)
