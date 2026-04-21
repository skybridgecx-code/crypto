from __future__ import annotations

import json
from pathlib import Path

import pytest
from crypto_agent.cli.matrix import run_paper_replay_matrix
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"


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


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    return json.loads((SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8"))


def test_matrix_comparison_snapshot_and_reconciliation(tmp_path: Path) -> None:
    manifest = run_paper_replay_matrix(
        settings=_paper_settings_for(tmp_path),
        matrix_run_id="paper-run-matrix-demo",
    )

    manifest_payload = json.loads(Path(manifest.manifest_path).read_text(encoding="utf-8"))
    comparison_path = Path(manifest.matrix_comparison_path)
    comparison = json.loads(comparison_path.read_text(encoding="utf-8"))

    assert comparison_path.exists()
    assert comparison == _load_snapshot("paper_run_matrix_default.comparison.snapshot.json")

    rows = comparison["rows"]
    aggregate = comparison["aggregate"]
    rankings = comparison["rankings"]
    expected_run_ids = [str(entry["run_id"]) for entry in manifest_payload["entries"]]
    assert [str(row["run_id"]) for row in rows] == expected_run_ids

    total_starting_equity_usd = 0.0
    total_net_realized_pnl_usd = 0.0
    total_ending_unrealized_pnl_usd = 0.0
    total_ending_equity_usd = 0.0
    total_proposal_count = 0
    total_halt_count = 0
    total_order_reject_count = 0
    total_fill_event_count = 0
    total_partial_fill_intent_count = 0
    total_alert_count = 0
    total_ledger_row_count = 0
    passed_run_count = 0
    failed_run_count = 0

    best_return_row: dict[str, object] | None = None
    worst_return_row: dict[str, object] | None = None
    highest_equity_row: dict[str, object] | None = None
    lowest_equity_row: dict[str, object] | None = None
    scenario_bps = {
        "baseline": 0.0,
        "cost_slippage_plus_5bps": 5.0,
        "cost_slippage_plus_10bps": 10.0,
        None: float("inf"),
    }

    for row, raw_entry in zip(rows, manifest_payload["entries"], strict=True):
        entry = dict(raw_entry)
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

        assert row["run_id"] == entry["run_id"]
        assert row["fixture"] == entry["fixture"]
        assert row["proposal_count"] == entry["outcome_counts"]["proposal_count"]
        assert row["halt_count"] == entry["outcome_counts"]["halt_count"]
        assert row["order_reject_count"] == entry["outcome_counts"]["order_reject_count"]
        assert row["fill_event_count"] == entry["outcome_counts"]["fill_event_count"]
        assert (
            row["partial_fill_intent_count"] == entry["outcome_counts"]["partial_fill_intent_count"]
        )
        assert row["alert_count"] == entry["outcome_counts"]["alert_count"]
        assert row["ledger_row_count"] == single_run_ledger["row_count"]
        assert row["starting_equity_usd"] == pytest.approx(replay_pnl.starting_equity_usd)
        assert row["net_realized_pnl_usd"] == pytest.approx(replay_pnl.net_realized_pnl_usd)
        assert row["ending_unrealized_pnl_usd"] == pytest.approx(
            replay_pnl.ending_unrealized_pnl_usd
        )
        assert row["ending_equity_usd"] == pytest.approx(replay_pnl.ending_equity_usd)
        assert row["return_fraction"] == pytest.approx(replay_pnl.return_fraction)
        expected_baseline_verdict = "pass" if replay_pnl.return_fraction >= 0 else "fail"
        assert row["baseline_robustness_verdict"] == expected_baseline_verdict
        assert row["robustness_verdict"] in {"pass", "fail"}
        assert row["first_fail_scenario_id"] in {
            "baseline",
            "cost_slippage_plus_5bps",
            "cost_slippage_plus_10bps",
            None,
        }
        assert row["first_fail_additional_cost_slippage_bps"] in {0.0, 5.0, 10.0, None}
        assert row["max_stress_scenario_id"] == "cost_slippage_plus_10bps"
        assert float(row["max_stress_additional_cost_slippage_bps"]) == pytest.approx(10.0)
        assert float(row["max_stress_net_pnl_drag_usd"]) >= 0.0
        assert row["risk_policy_robustness_verdict"] in {"pass", "fail"}
        assert row["risk_policy_first_fail_scenario_id"] in {
            "policy_tighter_75pct",
            "policy_baseline_100pct",
            "policy_looser_125pct",
            None,
        }
        assert row["risk_policy_first_fail_scale_multiplier"] in {0.75, 1.0, 1.25, None}
        assert int(row["risk_policy_pass_scenario_count"]) >= 0
        assert int(row["risk_policy_fail_scenario_count"]) >= 0
        assert int(row["risk_policy_pass_scenario_count"]) + int(
            row["risk_policy_fail_scenario_count"]
        ) == len(row["risk_policy_outcomes"])
        assert float(row["risk_policy_sensitivity_span_net_pnl_usd"]) >= 0.0
        assert float(row["risk_policy_sensitivity_span_return_fraction"]) >= 0.0
        assert row["risk_policy_most_adverse_scenario_id"] in {
            "policy_tighter_75pct",
            "policy_baseline_100pct",
            "policy_looser_125pct",
            None,
        }
        assert row["risk_policy_is_narrow_dependence"] in {True, False}
        risk_policy_outcomes = row["risk_policy_outcomes"]
        assert [outcome["scenario_id"] for outcome in risk_policy_outcomes] == [
            "policy_tighter_75pct",
            "policy_baseline_100pct",
            "policy_looser_125pct",
        ]
        for outcome in risk_policy_outcomes:
            assert outcome["verdict"] in {"pass", "fail"}
            assert float(outcome["risk_scale_multiplier"]) in {0.75, 1.0, 1.25}
            assert float(outcome["stressed_ending_equity_usd"]) >= 0.0
        assert int(row["fragility_rank"]) >= 1
        assert int(row["resilience_rank"]) >= 1
        assert row["walk_forward_robustness_verdict"] in {"pass", "fail"}
        assert int(row["walk_forward_slice_count"]) >= 1
        assert int(row["walk_forward_pass_slice_count"]) >= 0
        assert int(row["walk_forward_fail_slice_count"]) >= 0
        assert int(row["walk_forward_slice_count"]) == (
            int(row["walk_forward_pass_slice_count"]) + int(row["walk_forward_fail_slice_count"])
        )
        assert float(row["walk_forward_consistency_stddev_net_pnl_usd"]) >= 0.0
        assert float(row["walk_forward_consistency_range_net_pnl_usd"]) >= 0.0
        assert row["walk_forward_best_slice_id"] is not None
        assert row["walk_forward_worst_slice_id"] is not None
        assert float(row["walk_forward_profit_concentration_fraction"]) >= 0.0
        assert row["walk_forward_is_profit_concentrated"] in {True, False}
        walk_forward_slices = row["walk_forward_slices"]
        assert len(walk_forward_slices) == int(row["walk_forward_slice_count"])
        assert [slice_["slice_index"] for slice_ in walk_forward_slices] == list(
            range(1, len(walk_forward_slices) + 1)
        )
        for slice_ in walk_forward_slices:
            assert int(slice_["start_candle_index"]) <= int(slice_["end_candle_index"])
            assert int(slice_["candle_count"]) >= 1
            assert float(slice_["cumulative_ending_equity_usd"]) >= 0.0
            assert slice_["verdict"] in {"pass", "fail"}
        stress_outcomes = row["stress_outcomes"]
        assert [outcome["scenario_id"] for outcome in stress_outcomes] == [
            "cost_slippage_plus_5bps",
            "cost_slippage_plus_10bps",
        ]
        for outcome in stress_outcomes:
            expected_incremental_cost_usd = (
                replay_result.scorecard.total_fill_notional_usd
                * float(outcome["additional_cost_slippage_bps"])
                / 10_000.0
            )
            assert float(outcome["incremental_cost_usd"]) == pytest.approx(
                expected_incremental_cost_usd
            )
            assert float(outcome["stressed_net_realized_pnl_usd"]) == pytest.approx(
                replay_pnl.net_realized_pnl_usd - expected_incremental_cost_usd
            )
            assert float(outcome["delta_net_realized_pnl_usd_vs_baseline"]) == pytest.approx(
                -expected_incremental_cost_usd
            )
            assert outcome["verdict"] in {"pass", "fail"}
            assert float(
                row["stress_delta_net_realized_pnl_usd_by_scenario"][outcome["scenario_id"]]
            ) == pytest.approx(  # noqa: E501
                float(outcome["delta_net_realized_pnl_usd_vs_baseline"])
            )
            assert float(
                row["stress_delta_return_fraction_by_scenario"][outcome["scenario_id"]]
            ) == pytest.approx(  # noqa: E501
                float(outcome["delta_return_fraction_vs_baseline"])
            )

        total_proposal_count += int(row["proposal_count"])
        total_halt_count += int(row["halt_count"])
        total_order_reject_count += int(row["order_reject_count"])
        total_fill_event_count += int(row["fill_event_count"])
        total_partial_fill_intent_count += int(row["partial_fill_intent_count"])
        total_alert_count += int(row["alert_count"])
        total_ledger_row_count += int(row["ledger_row_count"])
        total_starting_equity_usd += float(row["starting_equity_usd"])
        total_net_realized_pnl_usd += float(row["net_realized_pnl_usd"])
        total_ending_unrealized_pnl_usd += float(row["ending_unrealized_pnl_usd"])
        total_ending_equity_usd += float(row["ending_equity_usd"])
        if row["robustness_verdict"] == "pass":
            passed_run_count += 1
        else:
            failed_run_count += 1

        if best_return_row is None or (
            float(row["return_fraction"]),
            str(row["run_id"]),
        ) > (
            float(best_return_row["return_fraction"]),
            str(best_return_row["run_id"]),
        ):
            best_return_row = row
        if worst_return_row is None or (
            float(row["return_fraction"]),
            str(row["run_id"]),
        ) < (
            float(worst_return_row["return_fraction"]),
            str(worst_return_row["run_id"]),
        ):
            worst_return_row = row
        if highest_equity_row is None or (
            float(row["ending_equity_usd"]),
            str(row["run_id"]),
        ) > (
            float(highest_equity_row["ending_equity_usd"]),
            str(highest_equity_row["run_id"]),
        ):
            highest_equity_row = row
        if lowest_equity_row is None or (
            float(row["ending_equity_usd"]),
            str(row["run_id"]),
        ) < (
            float(lowest_equity_row["ending_equity_usd"]),
            str(lowest_equity_row["run_id"]),
        ):
            lowest_equity_row = row

    assert aggregate["run_count"] == comparison["row_count"]
    assert aggregate["total_proposal_count"] == total_proposal_count
    assert aggregate["total_halt_count"] == total_halt_count
    assert aggregate["total_order_reject_count"] == total_order_reject_count
    assert aggregate["total_fill_event_count"] == total_fill_event_count
    assert aggregate["total_partial_fill_intent_count"] == total_partial_fill_intent_count
    assert aggregate["total_alert_count"] == total_alert_count
    assert aggregate["total_ledger_row_count"] == total_ledger_row_count
    assert aggregate["total_starting_equity_usd"] == pytest.approx(total_starting_equity_usd)
    assert aggregate["total_net_realized_pnl_usd"] == pytest.approx(total_net_realized_pnl_usd)
    assert aggregate["total_ending_unrealized_pnl_usd"] == pytest.approx(
        total_ending_unrealized_pnl_usd
    )
    assert aggregate["total_ending_equity_usd"] == pytest.approx(total_ending_equity_usd)

    expected_aggregate_return_fraction = (
        (total_ending_equity_usd - total_starting_equity_usd) / total_starting_equity_usd
        if total_starting_equity_usd > 0
        else 0.0
    )
    assert aggregate["aggregate_return_fraction"] == pytest.approx(
        expected_aggregate_return_fraction
    )
    expected_aggregate_baseline_verdict = (
        "pass" if expected_aggregate_return_fraction >= 0 else "fail"
    )
    assert aggregate["baseline_robustness_verdict"] == expected_aggregate_baseline_verdict
    assert aggregate["robustness_verdict"] in {"pass", "fail"}
    assert aggregate["first_fail_scenario_id"] in {
        "baseline",
        "cost_slippage_plus_5bps",
        "cost_slippage_plus_10bps",
        None,
    }
    assert aggregate["first_fail_additional_cost_slippage_bps"] in {0.0, 5.0, 10.0, None}
    assert aggregate["passed_run_count"] == passed_run_count
    assert aggregate["failed_run_count"] == failed_run_count
    assert aggregate["max_stress_scenario_id"] == "cost_slippage_plus_10bps"
    assert float(aggregate["max_stress_additional_cost_slippage_bps"]) == pytest.approx(10.0)
    assert float(aggregate["max_stress_total_net_pnl_drag_usd"]) == pytest.approx(
        sum(float(row["max_stress_net_pnl_drag_usd"]) for row in rows)
    )
    assert aggregate["risk_policy_robustness_verdict"] in {"pass", "fail"}
    assert int(aggregate["risk_policy_pass_run_count"]) + int(
        aggregate["risk_policy_fail_run_count"]
    ) == len(rows)
    assert aggregate["risk_policy_first_fail_scenario_id"] in {
        "policy_tighter_75pct",
        "policy_baseline_100pct",
        "policy_looser_125pct",
        None,
    }
    assert aggregate["risk_policy_first_fail_run_id"] in expected_run_ids + [None]
    assert aggregate["risk_policy_most_sensitive_run_id"] in expected_run_ids + [None]
    assert aggregate["risk_policy_winner_run_id"] in expected_run_ids + [None]
    assert aggregate["risk_policy_winner_robustness_verdict"] in {"pass", "fail"}
    assert int(aggregate["risk_policy_narrow_dependence_count"]) >= 0
    assert all(
        run_id in expected_run_ids for run_id in aggregate["risk_policy_narrow_dependence_run_ids"]
    )
    risk_policy_aggregate_outcomes = aggregate["risk_policy_outcomes"]
    assert [outcome["scenario_id"] for outcome in risk_policy_aggregate_outcomes] == [
        "policy_tighter_75pct",
        "policy_baseline_100pct",
        "policy_looser_125pct",
    ]
    for outcome in risk_policy_aggregate_outcomes:
        assert float(outcome["risk_scale_multiplier"]) in {0.75, 1.0, 1.25}
        assert outcome["verdict"] in {"pass", "fail"}
        assert int(outcome["failing_run_count"]) >= 0
        assert int(outcome["passing_run_count"]) >= 0
    assert aggregate["walk_forward_aggregate_robustness_verdict"] in {"pass", "fail"}
    assert int(aggregate["walk_forward_pass_run_count"]) + int(
        aggregate["walk_forward_fail_run_count"]
    ) == len(rows)
    assert aggregate["walk_forward_winner_run_id"] in expected_run_ids + [None]
    assert aggregate["walk_forward_winner_robustness_verdict"] in {"pass", "fail"}
    assert aggregate["walk_forward_most_consistent_run_id"] in expected_run_ids + [None]
    assert aggregate["walk_forward_worst_slice_run_id"] in expected_run_ids + [None]
    assert aggregate["walk_forward_worst_slice_id"] in {
        "window_1_of_3",
        "window_2_of_3",
        "window_3_of_3",
        None,
    }
    walk_forward_aggregate_slices = aggregate["walk_forward_slice_outcomes"]
    assert [slice_["slice_index"] for slice_ in walk_forward_aggregate_slices] == list(
        range(1, len(walk_forward_aggregate_slices) + 1)
    )
    for slice_ in walk_forward_aggregate_slices:
        assert slice_["verdict"] in {"pass", "fail"}
        assert int(slice_["failing_run_count"]) >= 0
        assert int(slice_["passing_run_count"]) >= 0
        assert int(slice_["failing_run_count"]) + int(slice_["passing_run_count"]) <= len(rows)
    aggregate_stress_outcomes = aggregate["stress_outcomes"]
    assert [outcome["scenario_id"] for outcome in aggregate_stress_outcomes] == [
        "cost_slippage_plus_5bps",
        "cost_slippage_plus_10bps",
    ]
    for outcome in aggregate_stress_outcomes:
        assert outcome["verdict"] in {"pass", "fail"}
        assert int(outcome["failing_run_count"]) >= 0
        scenario_id = outcome["scenario_id"]
        assert float(
            aggregate["stress_delta_total_net_realized_pnl_usd_by_scenario"][scenario_id]
        ) == pytest.approx(float(outcome["delta_total_net_realized_pnl_usd_vs_baseline"]))
        assert float(
            aggregate["stress_delta_aggregate_return_fraction_by_scenario"][scenario_id]
        ) == pytest.approx(float(outcome["delta_aggregate_return_fraction_vs_baseline"]))

    expected_failure_order = [
        str(row["run_id"])
        for row in sorted(
            (row for row in rows if row["first_fail_scenario_id"] is not None),
            key=lambda row: (scenario_bps[row["first_fail_scenario_id"]], str(row["run_id"])),
        )
    ]
    assert aggregate["failure_order_run_ids"] == expected_failure_order
    if expected_failure_order:
        earliest_failure_bps = scenario_bps[
            next(
                row["first_fail_scenario_id"]
                for row in rows
                if str(row["run_id"]) == expected_failure_order[0]
            )
        ]
        expected_first_failure_run_ids = [
            str(row["run_id"])
            for row in rows
            if row["first_fail_scenario_id"] is not None
            and scenario_bps[row["first_fail_scenario_id"]] == earliest_failure_bps
        ]
    else:
        expected_first_failure_run_ids = []
    assert aggregate["first_failure_run_ids"] == sorted(expected_first_failure_run_ids)

    assert rankings["best_return_run_id"] == best_return_row["run_id"]
    assert rankings["worst_return_run_id"] == worst_return_row["run_id"]
    assert rankings["highest_ending_equity_run_id"] == highest_equity_row["run_id"]
    assert rankings["lowest_ending_equity_run_id"] == lowest_equity_row["run_id"]
    assert rankings["first_robustness_failure_run_id"] in expected_run_ids + [None]
    assert rankings["first_robustness_failure_scenario_id"] in {
        "baseline",
        "cost_slippage_plus_5bps",
        "cost_slippage_plus_10bps",
        None,
    }
    assert rankings["most_fragile_run_id"] in expected_run_ids + [None]
    assert rankings["most_resilient_run_id"] in expected_run_ids + [None]
    assert sorted(rankings["fragility_order_run_ids"]) == sorted(expected_run_ids)
    assert sorted(rankings["resilience_order_run_ids"]) == sorted(expected_run_ids)
    assert rankings["most_consistent_walk_forward_run_id"] in expected_run_ids + [None]
    assert rankings["worst_walk_forward_slice_run_id"] in expected_run_ids + [None]
    assert rankings["worst_walk_forward_slice_id"] in {
        "window_1_of_3",
        "window_2_of_3",
        "window_3_of_3",
        None,
    }
    assert rankings["winner_walk_forward_robustness_verdict"] in {"pass", "fail"}
    assert rankings["most_policy_sensitive_run_id"] in expected_run_ids + [None]
    assert rankings["first_policy_failure_run_id"] in expected_run_ids + [None]
    assert rankings["first_policy_failure_scenario_id"] in {
        "policy_tighter_75pct",
        "policy_baseline_100pct",
        "policy_looser_125pct",
        None,
    }
    assert rankings["winner_policy_robustness_verdict"] in {"pass", "fail"}
