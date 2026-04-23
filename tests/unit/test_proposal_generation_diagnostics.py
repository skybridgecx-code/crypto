from __future__ import annotations

import json
from pathlib import Path

from crypto_agent.cli.main import run_paper_replay
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
