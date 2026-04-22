from __future__ import annotations

import argparse
import json
from pathlib import Path

from crypto_agent.cli.forward_paper_experiment import (
    _build_parser,
    run_advisory_control_experiment,
)


def _value_for_flag(command: list[str], flag: str) -> str:
    index = command.index(flag)
    return command[index + 1]


def _fake_cli_runner_factory(tmp_path: Path):
    commands: list[list[str]] = []
    deltas = {
        "btcusdt": {"proposal": 2, "event": 5, "execution_request": 1},
        "ethusdt": {"proposal": 0, "event": 1, "execution_request": 0},
    }

    def _runner(command: list[str]) -> dict[str, object]:
        commands.append(command)
        module = command[2]
        if module == "crypto_agent.cli.forward_paper":
            runtime_id = _value_for_flag(command, "--runtime-id")
            return {
                "runtime_id": runtime_id,
                "status_path": str(tmp_path / "runs" / runtime_id / "forward_paper_status.json"),
            }

        if module == "crypto_agent.cli.forward_paper_compare":
            advisory_run_id = _value_for_flag(command, "--advisory-run-id")
            control_run_id = _value_for_flag(command, "--control-run-id")
            output_dir = Path(_value_for_flag(command, "--output-dir"))
            output_dir.mkdir(parents=True, exist_ok=True)
            symbol_token = advisory_run_id.split("-")[-2]
            delta = deltas[symbol_token]
            comparison_payload = {
                "comparison_kind": "forward_paper_advisory_control_comparison_v1",
                "advisory_run_id": advisory_run_id,
                "control_run_id": control_run_id,
                "advisory_run": {
                    "advisory_decision_marker_presence": "present",
                    "session_outcome_counts": {"executed": 1},
                },
                "control_run": {
                    "advisory_decision_marker_presence": "absent",
                    "session_outcome_counts": {"executed": 1},
                },
                "delta": {
                    "proposal_count": delta["proposal"],
                    "event_count": delta["event"],
                    "execution_request_count": delta["execution_request"],
                    "execution_terminal_count": 0,
                    "net_realized_pnl_usd_total": None,
                },
            }
            json_path = output_dir / f"{advisory_run_id}_vs_{control_run_id}.comparison.json"
            report_path = output_dir / f"{advisory_run_id}_vs_{control_run_id}.comparison.md"
            json_path.write_text(json.dumps(comparison_payload), encoding="utf-8")
            report_path.write_text("# report\n", encoding="utf-8")
            return {
                "comparison_kind": comparison_payload["comparison_kind"],
                "json_path": str(json_path),
                "report_path": str(report_path),
            }

        raise AssertionError(f"unexpected module call: {module}")

    return _runner, commands


def _build_args(tmp_path: Path) -> argparse.Namespace:
    output_dir = tmp_path / "experiment-output"
    advisory_artifact = tmp_path / "advisory.json"
    advisory_artifact.write_text("{}", encoding="utf-8")
    parser = _build_parser()
    return parser.parse_args(
        [
            "--symbols",
            "BTCUSDT",
            "ETHUSDT",
            "--advisory-artifact-path",
            str(advisory_artifact),
            "--binance-base-url",
            "https://api.binance.us",
            "--run-id-prefix",
            "omega-exp",
            "--output-dir",
            str(output_dir),
            "--runs-dir",
            str(tmp_path / "runs"),
            "--session-interval-seconds",
            "120",
            "--max-sessions",
            "2",
        ]
    )


def test_run_advisory_control_experiment_builds_cli_commands_and_rows(tmp_path: Path) -> None:
    args = _build_args(tmp_path)
    runner, commands = _fake_cli_runner_factory(tmp_path)

    payload = run_advisory_control_experiment(args=args, cli_runner=runner)

    assert payload["experiment_kind"] == "forward_paper_advisory_control_experiment_index_v1"
    assert payload["symbol_count"] == 2
    rows = payload["rows"]
    assert [row["symbol"] for row in rows] == ["BTCUSDT", "ETHUSDT"]

    assert len(commands) == 6
    advisory_command = commands[0]
    control_command = commands[1]
    compare_command = commands[2]
    assert advisory_command[2] == "crypto_agent.cli.forward_paper"
    assert control_command[2] == "crypto_agent.cli.forward_paper"
    assert compare_command[2] == "crypto_agent.cli.forward_paper_compare"
    assert "--external-confirmation-path" in advisory_command
    assert "--external-confirmation-path" not in control_command
    assert _value_for_flag(advisory_command, "--live-symbol") == "BTCUSDT"
    assert _value_for_flag(control_command, "--live-symbol") == "BTCUSDT"
    assert Path(_value_for_flag(compare_command, "--output-dir")).name == "comparisons"

    assert rows[0]["proposal_count_delta"] == 2
    assert rows[0]["event_count_delta"] == 5
    assert rows[0]["execution_request_count_delta"] == 1
    assert rows[0]["advisory_marker_presence"] == "present"
    assert rows[0]["advisory_session_outcome_counts"] == {"executed": 1}
    assert rows[0]["control_session_outcome_counts"] == {"executed": 1}

    assert rows[1]["proposal_count_delta"] == 0
    assert rows[1]["event_count_delta"] == 1
    assert rows[1]["execution_request_count_delta"] == 0
