from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from crypto_agent.cli.forward_paper import main
from crypto_agent.cli.forward_paper_proposal_generation_report import (
    main as proposal_generation_report_main,
)
from crypto_agent.config import load_settings
from crypto_agent.regime.base import RegimeConfig
from crypto_agent.runtime.history import append_forward_paper_history
from crypto_agent.runtime.loop import (
    RuntimeAlreadyActiveError,
    build_forward_paper_runtime_paths,
    run_forward_paper_runtime,
)
from crypto_agent.runtime.models import (
    ForwardPaperHistoryEvent,
    ForwardPaperRuntimeStatus,
    ForwardPaperSessionSummary,
)
from crypto_agent.runtime.session_registry import upsert_forward_paper_registry_entry

FIXTURES_DIR = Path("tests/fixtures")
SNAPSHOTS_DIR = FIXTURES_DIR / "snapshots"
_DEFAULT_REGIME_CONFIG = RegimeConfig().model_dump(mode="json")
_FORWARD_RUNTIME_INDEX_FIELDS: tuple[str, ...] = (
    "runtime_id",
    "status_path",
    "history_path",
    "sessions_dir",
    "registry_path",
    "live_market_status_path",
    "venue_constraints_path",
    "account_state_path",
    "reconciliation_report_path",
    "recovery_status_path",
    "execution_state_dir",
    "live_control_config_path",
    "live_control_status_path",
    "readiness_status_path",
    "manual_control_state_path",
    "shadow_canary_evaluation_path",
    "soak_evaluation_path",
    "shadow_evaluation_path",
    "live_market_preflight_path",
    "live_gate_config_path",
    "live_gate_decision_path",
    "live_gate_threshold_summary_path",
    "live_gate_report_path",
    "live_launch_verdict_path",
    "live_authority_state_path",
    "live_launch_window_path",
    "live_transmission_decision_path",
    "live_transmission_result_path",
    "live_approval_state_path",
)
_FORWARD_RUNTIME_REGISTRY_PATH_FIELDS: tuple[str, ...] = (
    "runtime_id",
    "runtime_dir",
    "status_path",
    "history_path",
    "sessions_dir",
    "live_market_status_path",
    "venue_constraints_path",
    "account_state_path",
    "reconciliation_report_path",
    "recovery_status_path",
    "execution_state_dir",
    "live_control_config_path",
    "live_control_status_path",
    "readiness_status_path",
    "manual_control_state_path",
    "shadow_canary_evaluation_path",
    "soak_evaluation_path",
    "shadow_evaluation_path",
    "live_gate_config_path",
    "live_gate_decision_path",
    "live_gate_threshold_summary_path",
    "live_gate_report_path",
    "live_launch_verdict_path",
    "live_authority_state_path",
    "live_launch_window_path",
    "live_transmission_decision_path",
    "live_transmission_result_path",
    "live_approval_state_path",
)


def _load_snapshot(snapshot_name: str) -> dict[str, object]:
    return json.loads((SNAPSHOTS_DIR / snapshot_name).read_text(encoding="utf-8"))


def _normalize_runtime_index_snapshot(
    payload: dict[str, object],
    *,
    runs_dir: Path,
) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for field in _FORWARD_RUNTIME_INDEX_FIELDS:
        value = payload[field]
        if field == "runtime_id":
            normalized[field] = value
            continue
        if value is None:
            normalized[field] = None
            continue
        path_value = Path(str(value))
        normalized[field] = str(path_value.relative_to(runs_dir))
    return normalized


def _normalize_runtime_registry_entry_snapshot(
    payload: dict[str, object],
    *,
    runs_dir: Path,
) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for field in _FORWARD_RUNTIME_REGISTRY_PATH_FIELDS:
        value = payload[field]
        if field == "runtime_id":
            normalized[field] = value
            continue
        if value is None:
            normalized[field] = None
            continue
        path_value = Path(str(value))
        normalized[field] = str(path_value.relative_to(runs_dir))
    return normalized


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


def _write_xrp_discovery_config(tmp_path: Path) -> Path:
    config_payload = (
        Path("config/paper_coinbase_xrp_discovery.yaml")
        .read_text(encoding="utf-8")
        .replace("runs_dir: runs", f"runs_dir: {tmp_path / 'runs'}")
        .replace("journals_dir: journals", f"journals_dir: {tmp_path / 'journals'}")
    )
    config_path = tmp_path / "paper_coinbase_xrp_discovery.yaml"
    config_path.write_text(config_payload, encoding="utf-8")
    return config_path


def _tick(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def test_forward_paper_runtime_runs_repeated_sessions_and_persists_status(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-demo"
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=2,
        tick_times=[
            _tick(2026, 4, 5, 9, 0),
            _tick(2026, 4, 5, 9, 1),
        ],
    )

    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )
    status_payload = json.loads(result.status_path.read_text(encoding="utf-8"))
    registry = json.loads(result.registry_path.read_text(encoding="utf-8"))

    assert result.registry_path.exists()
    assert result.status_path.exists()
    assert result.history_path.exists()
    assert result.sessions_dir.exists()
    assert result.account_state_path.exists()
    assert result.reconciliation_report_path.exists()
    assert result.recovery_status_path.exists()
    assert result.session_count == 2
    assert [session.session_id for session in result.session_summaries] == [
        "session-0001",
        "session-0002",
    ]
    assert status.runtime_id == runtime_id
    assert status.status == "idle"
    assert status.completed_session_count == 2
    assert status.failed_session_count == 0
    assert status.interrupted_session_count == 0
    assert status.reconciliation_status == "clean"
    assert status.mismatch_detected is False
    assert status.regime_config_source == "default"
    assert status.regime_config == _DEFAULT_REGIME_CONFIG
    assert status.next_session_number == 3
    assert status.last_session_id == "session-0002"
    assert status.next_scheduled_at == _tick(2026, 4, 5, 9, 2)
    for field in _FORWARD_RUNTIME_INDEX_FIELDS:
        assert field in status_payload
    assert status_payload["runtime_id"] == result.runtime_id
    for field in _FORWARD_RUNTIME_INDEX_FIELDS:
        if field == "runtime_id":
            continue
        path_value = getattr(result, field)
        expected = None if path_value is None else str(path_value)
        assert status_payload[field] == expected
    assert registry["runtime_count"] == 1
    assert registry["runtimes"][0]["runtime_id"] == runtime_id
    assert registry["runtimes"][0]["status"] == "idle"

    for session in result.session_summaries:
        session_path = result.sessions_dir / f"{session.session_id}.json"
        proposal_generation_path = (
            result.sessions_dir / f"{session.session_id}.proposal_generation_summary.json"
        )
        summary = ForwardPaperSessionSummary.model_validate(
            json.loads(session_path.read_text(encoding="utf-8"))
        )
        linked_run_summary = json.loads(Path(summary.summary_path).read_text(encoding="utf-8"))
        proposal_generation_summary = json.loads(
            proposal_generation_path.read_text(encoding="utf-8")
        )
        assert summary.status == "completed"
        assert summary.run_id == f"{runtime_id}-{summary.session_id}"
        assert summary.all_artifact_paths_exist is True
        assert summary.artifact_paths_exist["proposal_generation_summary_path"] is True
        assert summary.scorecard == session.scorecard
        assert summary.pnl == session.pnl
        assert linked_run_summary["run_id"] == summary.run_id
        assert linked_run_summary["scorecard"] == summary.scorecard.model_dump(mode="json")
        assert linked_run_summary["pnl"] == summary.pnl.model_dump(mode="json")
        assert proposal_generation_summary["artifact_kind"] == (
            "forward_paper_proposal_generation_summary_v1"
        )
        assert proposal_generation_summary["session_id"] == session.session_id
        assert proposal_generation_summary["run_id"] == summary.run_id
        assert proposal_generation_summary["proposal_generation"]["run_id"] == summary.run_id

    assert result.session_summaries[1].pnl.starting_equity_usd == pytest.approx(
        result.session_summaries[0].pnl.ending_equity_usd
    )


def test_forward_runtime_status_index_snapshot(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-runtime-index-snapshot"
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_tick(2026, 4, 5, 15, 0)],
    )
    status_payload = json.loads(result.status_path.read_text(encoding="utf-8"))
    normalized_index = _normalize_runtime_index_snapshot(
        status_payload,
        runs_dir=settings.paths.runs_dir,
    )
    assert normalized_index == _load_snapshot("forward_runtime_status_index.snapshot.json")


def test_forward_runtime_registry_entry_snapshot(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-runtime-registry-snapshot"
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_tick(2026, 4, 5, 15, 1)],
    )
    registry_payload = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert registry_payload["runtime_count"] == 1
    normalized_entry = _normalize_runtime_registry_entry_snapshot(
        registry_payload["runtimes"][0],
        runs_dir=settings.paths.runs_dir,
    )
    assert normalized_entry == _load_snapshot("forward_runtime_registry_entry.snapshot.json")


def test_forward_paper_runtime_persists_regime_config_override_metadata(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-regime-override"
    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_tick(2026, 4, 5, 15, 2)],
        regime_config_override=RegimeConfig(liquidity_stress_dollar_volume_threshold=1_000.0),
    )
    status_payload = json.loads(result.status_path.read_text(encoding="utf-8"))
    registry_payload = json.loads(result.registry_path.read_text(encoding="utf-8"))
    assert status_payload["regime_config_source"] == "override"
    assert status_payload["regime_config"] == RegimeConfig(
        liquidity_stress_dollar_volume_threshold=1_000.0
    ).model_dump(mode="json")
    assert registry_payload["runtimes"][0]["regime_config_source"] == "override"
    assert (
        registry_payload["runtimes"][0]["regime_config"]["liquidity_stress_dollar_volume_threshold"]
        == 1_000.0
    )


def test_forward_paper_runtime_recovers_interrupted_session_on_restart(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-recovery"
    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.sessions_dir.mkdir(parents=True, exist_ok=True)

    started_at = _tick(2026, 4, 5, 10, 0)
    interrupted_session = ForwardPaperSessionSummary(
        runtime_id=runtime_id,
        session_id="session-0001",
        session_number=1,
        status="running",
        replay_path=FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        scheduled_at=started_at,
        started_at=started_at,
    )
    interrupted_session_path = paths.sessions_dir / "session-0001.json"
    interrupted_session_path.write_text(
        json.dumps(interrupted_session.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    status = ForwardPaperRuntimeStatus(
        runtime_id=runtime_id,
        replay_path=FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        starting_equity_usd=100_000.0,
        session_interval_seconds=60,
        status="running",
        next_session_number=2,
        active_session_id="session-0001",
        active_session_started_at=started_at,
        updated_at=started_at,
        status_path=paths.status_path,
        history_path=paths.history_path,
        sessions_dir=paths.sessions_dir,
        registry_path=paths.registry_path,
        account_state_path=paths.account_state_path,
        reconciliation_report_path=paths.reconciliation_report_path,
        recovery_status_path=paths.recovery_status_path,
        execution_state_dir=paths.execution_state_dir,
        live_control_config_path=paths.live_control_config_path,
        live_control_status_path=paths.live_control_status_path,
        readiness_status_path=paths.readiness_status_path,
        manual_control_state_path=paths.manual_control_state_path,
        shadow_canary_evaluation_path=paths.shadow_canary_evaluation_path,
        soak_evaluation_path=paths.soak_evaluation_path,
        shadow_evaluation_path=paths.shadow_evaluation_path,
        live_gate_decision_path=paths.live_gate_decision_path,
        live_gate_threshold_summary_path=paths.live_gate_threshold_summary_path,
        live_gate_report_path=paths.live_gate_report_path,
        live_launch_verdict_path=paths.live_launch_verdict_path,
        regime_config_source="default",
        regime_config=_DEFAULT_REGIME_CONFIG,
    )
    paths.status_path.write_text(
        json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    upsert_forward_paper_registry_entry(paths.registry_path, status)
    append_forward_paper_history(
        paths.history_path,
        ForwardPaperHistoryEvent(
            event_type="session.started",
            runtime_id=runtime_id,
            session_id="session-0001",
            session_number=1,
            occurred_at=started_at,
            status="running",
        ),
    )

    result = run_forward_paper_runtime(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_tick(2026, 4, 5, 10, 1)],
    )

    recovered = ForwardPaperSessionSummary.model_validate(
        json.loads(interrupted_session_path.read_text(encoding="utf-8"))
    )
    status_after = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert recovered.status == "interrupted"
    assert recovered.recovery_note == "recovered_after_restart"
    assert recovered.completed_at == _tick(2026, 4, 5, 10, 1)
    assert result.session_count == 1
    assert result.session_summaries[0].session_id == "session-0002"
    assert status_after.interrupted_session_count == 1
    assert status_after.completed_session_count == 1
    assert status_after.next_session_number == 3


def test_forward_paper_runtime_prevents_duplicate_active_session_without_recovery(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-duplicate"
    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.sessions_dir.mkdir(parents=True, exist_ok=True)

    started_at = _tick(2026, 4, 5, 11, 0)
    status = ForwardPaperRuntimeStatus(
        runtime_id=runtime_id,
        replay_path=FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        starting_equity_usd=100_000.0,
        session_interval_seconds=60,
        status="running",
        next_session_number=2,
        active_session_id="session-0001",
        active_session_started_at=started_at,
        updated_at=started_at,
        status_path=paths.status_path,
        history_path=paths.history_path,
        sessions_dir=paths.sessions_dir,
        registry_path=paths.registry_path,
        account_state_path=paths.account_state_path,
        reconciliation_report_path=paths.reconciliation_report_path,
        recovery_status_path=paths.recovery_status_path,
        execution_state_dir=paths.execution_state_dir,
        live_control_config_path=paths.live_control_config_path,
        live_control_status_path=paths.live_control_status_path,
        readiness_status_path=paths.readiness_status_path,
        manual_control_state_path=paths.manual_control_state_path,
        shadow_canary_evaluation_path=paths.shadow_canary_evaluation_path,
        soak_evaluation_path=paths.soak_evaluation_path,
        shadow_evaluation_path=paths.shadow_evaluation_path,
        live_gate_decision_path=paths.live_gate_decision_path,
        live_gate_threshold_summary_path=paths.live_gate_threshold_summary_path,
        live_gate_report_path=paths.live_gate_report_path,
        live_launch_verdict_path=paths.live_launch_verdict_path,
        regime_config_source="default",
        regime_config=_DEFAULT_REGIME_CONFIG,
    )
    paths.status_path.write_text(
        json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    upsert_forward_paper_registry_entry(paths.registry_path, status)

    with pytest.raises(RuntimeAlreadyActiveError):
        run_forward_paper_runtime(
            FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
            settings=settings,
            runtime_id=runtime_id,
            session_interval_seconds=60,
            max_sessions=1,
            tick_times=[_tick(2026, 4, 5, 11, 1)],
            recover_interrupted=False,
        )


def test_cli_forward_paper_runtime_runs_single_session_and_prints_status(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_paper_config(tmp_path)

    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_breakout_long.jsonl"),
            "--config",
            str(config_path),
            "--runtime-id",
            "forward-paper-cli",
            "--session-interval-seconds",
            "60",
            "--max-sessions",
            "1",
        ]
    )
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["runtime_id"] == "forward-paper-cli"
    assert Path(output["registry_path"]).exists()
    assert Path(output["status_path"]).exists()
    assert Path(output["history_path"]).exists()
    assert Path(output["sessions_dir"]).exists()
    assert Path(output["account_state_path"]).exists()
    assert Path(output["reconciliation_report_path"]).exists()
    assert Path(output["recovery_status_path"]).exists()
    assert Path(output["live_control_config_path"]).exists()
    assert Path(output["live_control_status_path"]).exists()
    assert Path(output["readiness_status_path"]).exists()
    assert Path(output["manual_control_state_path"]).exists()
    assert output["session_count"] == 1
    assert output["session_ids"] == ["session-0001"]


def test_cli_forward_paper_rejects_strategy_overrides_for_non_paper_mode(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_paper_config(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                str(FIXTURES_DIR / "paper_candles_breakout_long.jsonl"),
                "--config",
                str(config_path),
                "--runtime-id",
                "forward-paper-cli-non-paper-strategy-override",
                "--execution-mode",
                "shadow",
                "--mean-reversion-zscore-entry-threshold",
                "1.5",
            ]
        )
    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "Strategy config overrides are paper-only" in stderr


def test_cli_forward_paper_rejects_mean_reversion_max_atr_override_for_non_paper_mode(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_paper_config(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                str(FIXTURES_DIR / "paper_candles_breakout_long.jsonl"),
                "--config",
                str(config_path),
                "--runtime-id",
                "forward-paper-cli-non-paper-atr-override",
                "--execution-mode",
                "shadow",
                "--mean-reversion-max-atr-pct",
                "0.0025",
            ]
        )
    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "Strategy config overrides are paper-only" in stderr


def test_cli_forward_paper_applies_mean_reversion_max_atr_override_to_diagnostics(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_paper_config(tmp_path)
    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_high_volatility.jsonl"),
            "--config",
            str(config_path),
            "--runtime-id",
            "forward-paper-cli-mean-reversion-max-atr-override",
            "--execution-mode",
            "paper",
            "--mean-reversion-max-atr-pct",
            "0.0025",
            "--max-sessions",
            "1",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0

    sessions_dir = Path(output["sessions_dir"])
    proposal_generation_path = sessions_dir / "session-0001.proposal_generation_summary.json"
    proposal_generation_summary = json.loads(proposal_generation_path.read_text(encoding="utf-8"))
    mean_reversion = proposal_generation_summary["proposal_generation"]["mean_reversion"]

    assert mean_reversion["strategy_config"]["max_atr_pct"] == 0.0025
    assert mean_reversion["threshold_visibility"]["max_atr_pct_threshold_used"] == 0.0025


def test_cli_forward_paper_xrp_discovery_baseline_profile_resolves_effective_thresholds(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_xrp_discovery_config(tmp_path)
    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_high_volatility.jsonl"),
            "--config",
            str(config_path),
            "--runtime-id",
            "xrp-discovery-baseline-threshold-proof",
            "--execution-mode",
            "paper",
            "--max-sessions",
            "1",
            "--regime-liquidity-stress-dollar-volume-threshold",
            "150000",
            "--breakout-min-average-dollar-volume",
            "150000",
            "--mean-reversion-min-average-dollar-volume",
            "150000",
            "--mean-reversion-max-atr-pct",
            "0.00225",
            # Fixture symbol is BTCUSDT; keep deterministic replay path unblocked.
            "--allowed-symbol",
            "BTCUSDT",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0

    sessions_dir = Path(output["sessions_dir"])
    proposal_generation_path = sessions_dir / "session-0001.proposal_generation_summary.json"
    proposal_generation_summary = json.loads(proposal_generation_path.read_text(encoding="utf-8"))
    session_payload = json.loads((sessions_dir / "session-0001.json").read_text(encoding="utf-8"))
    summary_payload = json.loads(Path(session_payload["summary_path"]).read_text(encoding="utf-8"))
    status_payload = json.loads(Path(output["status_path"]).read_text(encoding="utf-8"))

    breakout = proposal_generation_summary["proposal_generation"]["breakout"]
    mean_reversion = proposal_generation_summary["proposal_generation"]["mean_reversion"]
    assert breakout["strategy_config"]["min_average_dollar_volume"] == 150_000.0
    assert breakout["threshold_visibility"]["min_average_dollar_volume_threshold_used"] == 150_000.0
    assert mean_reversion["strategy_config"]["min_average_dollar_volume"] == 150_000.0
    assert mean_reversion["strategy_config"]["max_atr_pct"] == 0.00225
    assert mean_reversion["strategy_config"]["zscore_entry_threshold"] == 2.0
    assert (
        mean_reversion["threshold_visibility"]["min_average_dollar_volume_threshold_used"]
        == 150_000.0
    )
    assert mean_reversion["threshold_visibility"]["max_atr_pct_threshold_used"] == 0.00225
    assert mean_reversion["threshold_visibility"]["zscore_entry_threshold_used"] == 2.0
    assert status_payload["regime_config_source"] == "override"
    assert status_payload["regime_config"]["liquidity_stress_dollar_volume_threshold"] == 150_000.0
    assert "external_confirmation" not in summary_payload


def test_cli_forward_paper_xrp_discovery_tuned_profile_resolves_zscore_threshold(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_xrp_discovery_config(tmp_path)
    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_high_volatility.jsonl"),
            "--config",
            str(config_path),
            "--runtime-id",
            "xrp-discovery-tuned-zscore-threshold-proof",
            "--execution-mode",
            "paper",
            "--max-sessions",
            "1",
            "--regime-liquidity-stress-dollar-volume-threshold",
            "150000",
            "--breakout-min-average-dollar-volume",
            "150000",
            "--mean-reversion-min-average-dollar-volume",
            "150000",
            "--mean-reversion-max-atr-pct",
            "0.00225",
            "--mean-reversion-zscore-entry-threshold",
            "1.75",
            # Fixture symbol is BTCUSDT; keep deterministic replay path unblocked.
            "--allowed-symbol",
            "BTCUSDT",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0

    sessions_dir = Path(output["sessions_dir"])
    proposal_generation_path = sessions_dir / "session-0001.proposal_generation_summary.json"
    proposal_generation_summary = json.loads(proposal_generation_path.read_text(encoding="utf-8"))
    session_payload = json.loads((sessions_dir / "session-0001.json").read_text(encoding="utf-8"))
    summary_payload = json.loads(Path(session_payload["summary_path"]).read_text(encoding="utf-8"))
    status_payload = json.loads(Path(output["status_path"]).read_text(encoding="utf-8"))

    breakout = proposal_generation_summary["proposal_generation"]["breakout"]
    mean_reversion = proposal_generation_summary["proposal_generation"]["mean_reversion"]
    assert breakout["strategy_config"]["min_average_dollar_volume"] == 150_000.0
    assert mean_reversion["strategy_config"] == {
        "lookback_candles": 4,
        "max_atr_pct": 0.00225,
        "max_realized_volatility": 0.002,
        "min_average_dollar_volume": 150_000.0,
        "stop_atr_multiple": 1.0,
        "strategy_id": "mean_reversion_v1",
        "zscore_entry_threshold": 1.75,
    }
    assert (
        mean_reversion["threshold_visibility"]["min_average_dollar_volume_threshold_used"]
        == 150_000.0
    )
    assert mean_reversion["threshold_visibility"]["max_atr_pct_threshold_used"] == 0.00225
    assert mean_reversion["threshold_visibility"]["zscore_entry_threshold_used"] == 1.75
    assert status_payload["regime_config_source"] == "override"
    assert status_payload["regime_config"]["liquidity_stress_dollar_volume_threshold"] == 150_000.0
    assert "external_confirmation" not in summary_payload


def test_cli_forward_paper_xrp_discovery_liquidity_tuning_resolves_effective_thresholds(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_xrp_discovery_config(tmp_path)
    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_high_volatility.jsonl"),
            "--config",
            str(config_path),
            "--runtime-id",
            "xrp-discovery-tuned-liquidity-threshold-proof",
            "--execution-mode",
            "paper",
            "--max-sessions",
            "1",
            "--xrp-discovery-liquidity-tuning",
            # Fixture symbol is BTCUSDT; keep deterministic replay path unblocked.
            "--allowed-symbol",
            "BTCUSDT",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0

    sessions_dir = Path(output["sessions_dir"])
    proposal_generation_path = sessions_dir / "session-0001.proposal_generation_summary.json"
    proposal_generation_summary = json.loads(proposal_generation_path.read_text(encoding="utf-8"))
    session_payload = json.loads((sessions_dir / "session-0001.json").read_text(encoding="utf-8"))
    summary_payload = json.loads(Path(session_payload["summary_path"]).read_text(encoding="utf-8"))
    status_payload = json.loads(Path(output["status_path"]).read_text(encoding="utf-8"))

    breakout = proposal_generation_summary["proposal_generation"]["breakout"]
    mean_reversion = proposal_generation_summary["proposal_generation"]["mean_reversion"]
    assert breakout["strategy_config_source"] == "override"
    assert breakout["strategy_config"]["min_average_dollar_volume"] == 50_000.0
    assert breakout["threshold_visibility"]["min_average_dollar_volume_threshold_used"] == 50_000.0
    assert mean_reversion["strategy_config_source"] == "override"
    assert mean_reversion["strategy_config"] == {
        "lookback_candles": 4,
        "max_atr_pct": 0.002,
        "max_realized_volatility": 0.002,
        "min_average_dollar_volume": 50_000.0,
        "stop_atr_multiple": 1.0,
        "strategy_id": "mean_reversion_v1",
        "zscore_entry_threshold": 2.0,
    }
    assert (
        mean_reversion["threshold_visibility"]["min_average_dollar_volume_threshold_used"]
        == 50_000.0
    )
    assert mean_reversion["threshold_visibility"]["zscore_entry_threshold_used"] == 2.0
    assert status_payload["regime_config_source"] == "override"
    assert status_payload["regime_config"]["liquidity_stress_dollar_volume_threshold"] == 50_000.0
    assert "external_confirmation" not in summary_payload

    assert (
        proposal_generation_report_main(
            [
                "--run-id",
                "xrp-discovery-tuned-liquidity-threshold-proof",
                "--runs-dir",
                str(tmp_path / "runs"),
            ]
        )
        == 0
    )
    report_output = json.loads(capsys.readouterr().out)
    aggregate_payload = json.loads(Path(report_output["json_path"]).read_text(encoding="utf-8"))
    report = Path(report_output["report_path"]).read_text(encoding="utf-8")
    run_payload = aggregate_payload["runs"][0]
    assert run_payload["strategy_aggregates"]["breakout"]["threshold_visibility"][
        "threshold_values_used"
    ]["min_average_dollar_volume_threshold_used"] == [50_000.0]
    assert run_payload["strategy_aggregates"]["mean_reversion"]["threshold_visibility"][
        "threshold_values_used"
    ] == {
        "max_atr_pct_threshold_used": [0.002],
        "max_realized_volatility_threshold_used": [0.002],
        "min_average_dollar_volume_threshold_used": [50_000.0],
        "zscore_entry_threshold_used": [2.0],
    }
    assert '"min_average_dollar_volume_threshold_used": [50000.0]' in report
    assert '"zscore_entry_threshold_used": [2.0]' in report


def test_cli_forward_paper_xrp_discovery_liquidity_tuning_is_not_default(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_xrp_discovery_config(tmp_path)
    exit_code = main(
        [
            str(FIXTURES_DIR / "paper_candles_high_volatility.jsonl"),
            "--config",
            str(config_path),
            "--runtime-id",
            "xrp-discovery-default-threshold-proof",
            "--execution-mode",
            "paper",
            "--max-sessions",
            "1",
            # Fixture symbol is BTCUSDT; keep deterministic replay path unblocked.
            "--allowed-symbol",
            "BTCUSDT",
        ]
    )
    output = json.loads(capsys.readouterr().out)
    assert exit_code == 0

    proposal_generation_path = (
        Path(output["sessions_dir"]) / "session-0001.proposal_generation_summary.json"
    )
    proposal_generation_summary = json.loads(proposal_generation_path.read_text(encoding="utf-8"))
    status_payload = json.loads(Path(output["status_path"]).read_text(encoding="utf-8"))
    breakout = proposal_generation_summary["proposal_generation"]["breakout"]
    mean_reversion = proposal_generation_summary["proposal_generation"]["mean_reversion"]

    assert breakout["strategy_config_source"] == "default"
    assert breakout["strategy_config"]["min_average_dollar_volume"] == 5_000_000.0
    assert mean_reversion["strategy_config_source"] == "default"
    assert mean_reversion["strategy_config"]["min_average_dollar_volume"] == 5_000_000.0
    assert mean_reversion["strategy_config"]["zscore_entry_threshold"] == 2.0
    assert status_payload["regime_config_source"] == "default"
    assert (
        status_payload["regime_config"]["liquidity_stress_dollar_volume_threshold"] == 5_000_000.0
    )


def test_cli_forward_paper_xrp_discovery_liquidity_tuning_rejects_zscore_combo(
    tmp_path: Path,
    capsys,
) -> None:
    config_path = _write_xrp_discovery_config(tmp_path)
    with pytest.raises(SystemExit) as exc_info:
        main(
            [
                str(FIXTURES_DIR / "paper_candles_high_volatility.jsonl"),
                "--config",
                str(config_path),
                "--runtime-id",
                "xrp-discovery-invalid-combo",
                "--execution-mode",
                "paper",
                "--xrp-discovery-liquidity-tuning",
                "--mean-reversion-zscore-entry-threshold",
                "1.75",
                "--allowed-symbol",
                "BTCUSDT",
            ]
        )

    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "--xrp-discovery-liquidity-tuning cannot be combined with zscore tuning" in stderr


def test_forward_paper_runtime_persists_interrupted_state_on_keyboard_interrupt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-paper-interrupt-during-session"
    interrupt_at = _tick(2026, 4, 6, 13, 0)

    def _raise_keyboard_interrupt(*args: object, **kwargs: object) -> object:
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "crypto_agent.runtime.loop.run_paper_replay",
        _raise_keyboard_interrupt,
    )

    with pytest.raises(KeyboardInterrupt):
        run_forward_paper_runtime(
            FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
            settings=settings,
            runtime_id=runtime_id,
            session_interval_seconds=60,
            max_sessions=1,
            tick_times=[interrupt_at],
            now_fn=lambda: interrupt_at,
        )

    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(paths.status_path.read_text(encoding="utf-8"))
    )
    session = ForwardPaperSessionSummary.model_validate(
        json.loads((paths.sessions_dir / "session-0001.json").read_text(encoding="utf-8"))
    )
    history_lines = [
        line for line in paths.history_path.read_text(encoding="utf-8").splitlines() if line
    ]

    assert status.status == "idle"
    assert status.active_session_id is None
    assert status.interrupted_session_count == 1
    assert status.last_session_id == "session-0001"
    assert session.status == "interrupted"
    assert session.recovery_note == "recovered_after_restart"
    assert session.completed_at == interrupt_at
    assert len(history_lines) == 2
    assert '"event_type": "session.started"' in history_lines[0]
    assert '"event_type": "session.interrupted"' in history_lines[1]
