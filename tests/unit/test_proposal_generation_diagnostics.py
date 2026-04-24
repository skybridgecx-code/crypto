from __future__ import annotations

import json
from pathlib import Path

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.signals.base import MeanReversionSignalConfig

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


def test_proposal_generation_diagnostics_emitted_proposal_case(tmp_path: Path) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="proposal-diagnostics-emitted",
    )

    assert result.proposal_generation_summary_path.exists()
    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))

    assert summary["artifact_kind"] == "proposal_generation_summary_v1"
    assert summary["proposal_pipeline"]["emitted_proposal_count"] >= 1
    assert summary["proposal_pipeline"]["allowed_for_execution_count"] >= 1
    assert summary["breakout"]["emitted_proposal_count"] >= 1


def test_proposal_generation_diagnostics_no_signal_case(tmp_path: Path) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_high_volatility.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="proposal-diagnostics-no-signal",
    )

    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))

    assert summary["proposal_pipeline"]["emitted_proposal_count"] == 0
    assert summary["proposal_pipeline"]["allowed_for_execution_count"] == 0
    assert summary["breakout"]["emitted_proposal_count"] == 0
    assert summary["mean_reversion"]["emitted_proposal_count"] == 0
    assert summary["breakout"]["non_emit_reason_counts"]
    assert summary["mean_reversion"]["insufficient_lookback_count"] >= 1


def test_proposal_generation_diagnostics_blocked_by_regime_case(tmp_path: Path) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_mean_reversion_short.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="proposal-diagnostics-regime-block",
    )

    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))

    assert summary["breakout"]["non_emit_reason_counts"].get("regime_not_trend", 0) >= 1


def test_proposal_generation_diagnostics_blocked_by_policy_or_risk_case(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    blocked_settings = settings.model_copy(
        update={
            "risk": settings.risk.model_copy(
                update={
                    "max_open_positions": 0,
                }
            )
        }
    )
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_breakout_long.jsonl",
        settings=blocked_settings,
        run_id="proposal-diagnostics-policy-block",
    )

    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))

    assert summary["proposal_pipeline"]["emitted_proposal_count"] >= 1
    assert summary["proposal_pipeline"]["allowed_for_execution_count"] == 0
    assert summary["proposal_pipeline"]["blocked_by_risk_or_policy_count"] >= 1
    assert (
        summary["proposal_pipeline"]["blocked_reason_counts"].get("max_open_positions_reached", 0)
        >= 1
    )


def test_proposal_generation_diagnostics_threshold_visibility_is_surfaced(tmp_path: Path) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_high_volatility.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="proposal-diagnostics-threshold-visibility",
    )
    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))
    breakout_thresholds = summary["breakout"]["threshold_visibility"]
    mean_reversion_thresholds = summary["mean_reversion"]["threshold_visibility"]
    mean_reversion_config = summary["mean_reversion"]["strategy_config"]

    assert breakout_thresholds["min_average_dollar_volume_threshold_used"] == 5_000_000.0
    assert breakout_thresholds["max_average_range_bps_threshold_used"] == 200.0
    assert breakout_thresholds["min_abs_momentum_return_threshold_used"] == 0.003
    assert mean_reversion_thresholds["min_average_dollar_volume_threshold_used"] == 5_000_000.0
    assert mean_reversion_thresholds["max_realized_volatility_threshold_used"] == 0.002
    assert mean_reversion_thresholds["max_atr_pct_threshold_used"] == 0.002
    assert mean_reversion_thresholds["zscore_entry_threshold_used"] == 2.0
    assert mean_reversion_config["zscore_entry_threshold"] == 2.0


def test_proposal_generation_diagnostics_mean_reversion_override_is_applied(
    tmp_path: Path,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_high_volatility.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="proposal-diagnostics-mean-reversion-override",
        mean_reversion_config_override=MeanReversionSignalConfig(min_average_dollar_volume=2_500.0),
    )
    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))
    mean_reversion = summary["mean_reversion"]

    assert mean_reversion["strategy_config_source"] == "override"
    assert mean_reversion["strategy_config"]["min_average_dollar_volume"] == 2_500.0
    assert (
        mean_reversion["threshold_visibility"]["min_average_dollar_volume_threshold_used"]
        == 2_500.0
    )


def test_proposal_generation_diagnostics_mean_reversion_zscore_override_is_applied(
    tmp_path: Path,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_high_volatility.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="proposal-diagnostics-mean-reversion-zscore-override",
        mean_reversion_config_override=MeanReversionSignalConfig(zscore_entry_threshold=1.5),
    )
    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))
    mean_reversion = summary["mean_reversion"]

    assert mean_reversion["strategy_config_source"] == "override"
    assert mean_reversion["strategy_config"]["zscore_entry_threshold"] == 1.5
    assert mean_reversion["threshold_visibility"]["zscore_entry_threshold_used"] == 1.5


def test_proposal_generation_diagnostics_mean_reversion_max_atr_override_is_applied(
    tmp_path: Path,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_high_volatility.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="proposal-diagnostics-mean-reversion-max-atr-override",
        mean_reversion_config_override=MeanReversionSignalConfig(max_atr_pct=0.0025),
    )
    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))
    mean_reversion = summary["mean_reversion"]

    assert mean_reversion["strategy_config_source"] == "override"
    assert mean_reversion["strategy_config"]["max_atr_pct"] == 0.0025
    assert mean_reversion["threshold_visibility"]["max_atr_pct_threshold_used"] == 0.0025


def test_proposal_generation_diagnostics_threshold_gap_signs(tmp_path: Path) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / "paper_candles_high_volatility.jsonl",
        settings=_paper_settings_for(tmp_path),
        run_id="proposal-diagnostics-threshold-gap-signs",
    )
    summary = json.loads(result.proposal_generation_summary_path.read_text(encoding="utf-8"))
    breakout_thresholds = summary["breakout"]["threshold_visibility"]
    mean_reversion_thresholds = summary["mean_reversion"]["threshold_visibility"]

    assert breakout_thresholds["gap_to_min_average_dollar_volume_last"] == (
        breakout_thresholds["observed_average_dollar_volume_last"]
        - breakout_thresholds["min_average_dollar_volume_threshold_used"]
    )
    if mean_reversion_thresholds["gap_to_max_realized_volatility_last"] is not None:
        assert mean_reversion_thresholds["gap_to_max_realized_volatility_last"] == (
            mean_reversion_thresholds["observed_realized_volatility_last"]
            - mean_reversion_thresholds["max_realized_volatility_threshold_used"]
        )
    if mean_reversion_thresholds["gap_to_max_atr_pct_last"] is not None:
        assert mean_reversion_thresholds["gap_to_max_atr_pct_last"] == (
            mean_reversion_thresholds["observed_atr_pct_last"]
            - mean_reversion_thresholds["max_atr_pct_threshold_used"]
        )
