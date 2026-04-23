from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
from crypto_agent.cli.forward_paper_experiment import (
    _build_parser,
    _render_index_markdown,
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
        "solusdt": {"proposal": -1, "event": -2, "execution_request": -1},
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


def _build_args(
    tmp_path: Path,
    *,
    symbols: list[str],
    shared_artifact: bool,
    symbol_advisory: list[str] | None = None,
    regime_liquidity_threshold: float | None = None,
    mean_reversion_min_average_dollar_volume: float | None = None,
    breakout_min_average_dollar_volume: float | None = None,
) -> argparse.Namespace:
    output_dir = tmp_path / "experiment-output"
    parser = _build_parser()
    argv: list[str] = [
        "--symbols",
        *symbols,
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
    if shared_artifact:
        advisory_artifact = tmp_path / "advisory-shared.json"
        advisory_artifact.write_text("{}", encoding="utf-8")
        argv.extend(["--advisory-artifact-path", str(advisory_artifact)])
    if symbol_advisory:
        for entry in symbol_advisory:
            argv.extend(["--symbol-advisory", entry])
    if regime_liquidity_threshold is not None:
        argv.extend(
            [
                "--regime-liquidity-stress-dollar-volume-threshold",
                str(regime_liquidity_threshold),
            ]
        )
    if mean_reversion_min_average_dollar_volume is not None:
        argv.extend(
            [
                "--mean-reversion-min-average-dollar-volume",
                str(mean_reversion_min_average_dollar_volume),
            ]
        )
    if breakout_min_average_dollar_volume is not None:
        argv.extend(
            [
                "--breakout-min-average-dollar-volume",
                str(breakout_min_average_dollar_volume),
            ]
        )
    return parser.parse_args(argv)


def _forward_commands(commands: list[list[str]]) -> list[list[str]]:
    return [command for command in commands if command[2] == "crypto_agent.cli.forward_paper"]


def test_per_symbol_mapping_resolution_and_index_recording(tmp_path: Path) -> None:
    btc_path = tmp_path / "btc.json"
    btc_path.write_text("{}", encoding="utf-8")
    eth_path = tmp_path / "eth.json"
    eth_path.write_text("{}", encoding="utf-8")
    args = _build_args(
        tmp_path,
        symbols=["BTCUSDT", "ETHUSDT"],
        shared_artifact=False,
        symbol_advisory=[
            f"BTCUSDT={btc_path}",
            f"ETHUSDT={eth_path}",
        ],
    )
    runner, commands = _fake_cli_runner_factory(tmp_path)

    payload = run_advisory_control_experiment(args=args, cli_runner=runner)
    rows = payload["rows"]
    assert rows[0]["advisory_artifact_resolution"] == "per_symbol"
    assert rows[0]["advisory_artifact_path_used"] == str(btc_path.resolve())
    assert rows[0]["advisory_lane_skipped"] is False
    assert rows[1]["advisory_artifact_resolution"] == "per_symbol"
    assert rows[1]["advisory_artifact_path_used"] == str(eth_path.resolve())
    assert rows[1]["advisory_lane_skipped"] is False

    forward_commands = _forward_commands(commands)
    advisory_command_1 = forward_commands[0]
    advisory_command_2 = forward_commands[2]
    assert _value_for_flag(advisory_command_1, "--external-confirmation-path") == str(
        btc_path.resolve()
    )
    assert _value_for_flag(advisory_command_2, "--external-confirmation-path") == str(
        eth_path.resolve()
    )

    report = _render_index_markdown(payload)
    assert "advisory_artifact_resolution: `per_symbol`" in report
    assert "advisory_lane_skipped: False" in report


def test_shared_fallback_resolution_when_per_symbol_missing(tmp_path: Path) -> None:
    shared_path = tmp_path / "advisory-shared.json"
    shared_path.write_text("{}", encoding="utf-8")
    btc_path = tmp_path / "btc.json"
    btc_path.write_text("{}", encoding="utf-8")
    args = _build_args(
        tmp_path,
        symbols=["BTCUSDT", "ETHUSDT"],
        shared_artifact=True,
        symbol_advisory=[f"BTCUSDT={btc_path}"],
    )
    runner, commands = _fake_cli_runner_factory(tmp_path)

    payload = run_advisory_control_experiment(args=args, cli_runner=runner)
    rows = payload["rows"]
    assert rows[0]["advisory_artifact_resolution"] == "per_symbol"
    assert rows[0]["advisory_artifact_path_used"] == str(btc_path.resolve())
    assert rows[1]["advisory_artifact_resolution"] == "shared_fallback"
    assert rows[1]["advisory_artifact_path_used"] == str(shared_path.resolve())

    forward_commands = _forward_commands(commands)
    advisory_command_eth = forward_commands[2]
    assert _value_for_flag(advisory_command_eth, "--external-confirmation-path") == str(
        shared_path.resolve()
    )


def test_missing_mapping_behavior_skips_advisory_lane(tmp_path: Path) -> None:
    args = _build_args(
        tmp_path,
        symbols=["SOLUSDT"],
        shared_artifact=False,
        symbol_advisory=None,
    )
    runner, commands = _fake_cli_runner_factory(tmp_path)

    payload = run_advisory_control_experiment(args=args, cli_runner=runner)
    row = payload["rows"][0]
    assert row["advisory_artifact_resolution"] == "none"
    assert row["advisory_artifact_path_used"] is None
    assert row["advisory_lane_skipped"] is True
    assert row["advisory_skip_reason"] == "no_symbol_or_shared_advisory_artifact"
    assert row["comparison_json_path"] is None
    assert row["proposal_count_delta"] is None
    assert row["advisory_marker_presence"] == "skipped"

    assert len(commands) == 1
    assert commands[0][2] == "crypto_agent.cli.forward_paper"
    assert "--external-confirmation-path" not in commands[0]


def test_regime_override_is_threaded_into_forward_paper_commands_and_index(tmp_path: Path) -> None:
    args = _build_args(
        tmp_path,
        symbols=["BTCUSDT"],
        shared_artifact=True,
        regime_liquidity_threshold=1_000.0,
    )
    runner, commands = _fake_cli_runner_factory(tmp_path)

    payload = run_advisory_control_experiment(args=args, cli_runner=runner)

    assert payload["regime_config_override"] == {
        "liquidity_stress_dollar_volume_threshold": 1_000.0
    }
    forward_commands = _forward_commands(commands)
    advisory_command = forward_commands[0]
    control_command = forward_commands[1]
    assert (
        _value_for_flag(
            advisory_command,
            "--regime-liquidity-stress-dollar-volume-threshold",
        )
        == "1000.0"
    )
    assert (
        _value_for_flag(
            control_command,
            "--regime-liquidity-stress-dollar-volume-threshold",
        )
        == "1000.0"
    )

    report = _render_index_markdown(payload)
    assert '"liquidity_stress_dollar_volume_threshold": 1000.0' in report


def test_strategy_override_is_threaded_into_forward_paper_commands_and_index(
    tmp_path: Path,
) -> None:
    args = _build_args(
        tmp_path,
        symbols=["BTCUSDT"],
        shared_artifact=True,
        mean_reversion_min_average_dollar_volume=2_500.0,
        breakout_min_average_dollar_volume=3_000.0,
    )
    runner, commands = _fake_cli_runner_factory(tmp_path)

    payload = run_advisory_control_experiment(args=args, cli_runner=runner)
    assert payload["strategy_config_override"] == {
        "breakout": {"min_average_dollar_volume": 3_000.0},
        "mean_reversion": {"min_average_dollar_volume": 2_500.0},
    }
    forward_commands = _forward_commands(commands)
    advisory_command = forward_commands[0]
    control_command = forward_commands[1]
    assert (
        _value_for_flag(advisory_command, "--mean-reversion-min-average-dollar-volume") == "2500.0"
    )
    assert (
        _value_for_flag(
            advisory_command,
            "--breakout-min-average-dollar-volume",
        )
        == "3000.0"
    )
    assert (
        _value_for_flag(
            control_command,
            "--mean-reversion-min-average-dollar-volume",
        )
        == "2500.0"
    )
    assert (
        _value_for_flag(
            control_command,
            "--breakout-min-average-dollar-volume",
        )
        == "3000.0"
    )

    report = _render_index_markdown(payload)
    assert '"mean_reversion": {"min_average_dollar_volume": 2500.0}' in report


def test_strategy_override_requires_paper_execution_mode(tmp_path: Path) -> None:
    args = _build_args(
        tmp_path,
        symbols=["BTCUSDT"],
        shared_artifact=True,
        mean_reversion_min_average_dollar_volume=2_500.0,
    )
    args.execution_mode = "shadow"
    runner, _ = _fake_cli_runner_factory(tmp_path)
    with pytest.raises(
        ValueError,
        match="forward_paper_experiment_strategy_overrides_require_execution_mode_paper",
    ):
        run_advisory_control_experiment(args=args, cli_runner=runner)
