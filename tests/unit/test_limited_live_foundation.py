from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.config import load_settings
from crypto_agent.policy.live_controls import default_live_control_config
from crypto_agent.policy.readiness import default_live_readiness_status
from crypto_agent.runtime.loop import run_forward_paper_runtime
from crypto_agent.runtime.models import (
    ForwardPaperRuntimeStatus,
    LiveApprovalStateArtifact,
    LiveAuthorityStateArtifact,
    LiveLaunchWindowArtifact,
    LiveTransmissionDecisionArtifact,
    LiveTransmissionRuntimeResultArtifact,
)


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


def _ts(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _write_active_live_approval(*, tmp_path: Path, runtime_id: str, generated_at: datetime) -> None:
    approval_path = tmp_path / "runs" / runtime_id / "live_approval_state.json"
    approval_path.parent.mkdir(parents=True, exist_ok=True)
    approval_path.write_text(
        json.dumps(
            LiveApprovalStateArtifact(
                runtime_id=runtime_id,
                generated_at=generated_at,
                required_for_live_transmission=True,
                active_approval_count=1,
                approvals=[],
                summary="One live approval is active for bounded eligibility testing.",
                reason_codes=[],
            ).model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )


def test_forward_runtime_writes_limited_live_foundation_artifacts_for_replay_runtime(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)

    result = run_forward_paper_runtime(
        Path("tests/fixtures/paper_candles_breakout_long.jsonl"),
        settings=settings,
        runtime_id="limited-live-foundation-replay",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 10, 12, 0)],
        market_source="replay",
    )

    assert result.live_authority_state_path is not None
    assert result.live_launch_window_path is not None
    assert result.live_transmission_decision_path is not None
    assert result.live_transmission_result_path is not None
    assert result.live_approval_state_path is not None

    authority = LiveAuthorityStateArtifact.model_validate(
        json.loads(result.live_authority_state_path.read_text(encoding="utf-8"))
    )
    window = LiveLaunchWindowArtifact.model_validate(
        json.loads(result.live_launch_window_path.read_text(encoding="utf-8"))
    )
    decision = LiveTransmissionDecisionArtifact.model_validate(
        json.loads(result.live_transmission_decision_path.read_text(encoding="utf-8"))
    )
    transmission_result = LiveTransmissionRuntimeResultArtifact.model_validate(
        json.loads(result.live_transmission_result_path.read_text(encoding="utf-8"))
    )
    approval = LiveApprovalStateArtifact.model_validate(
        json.loads(result.live_approval_state_path.read_text(encoding="utf-8"))
    )
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert authority.authority_enabled is False
    assert authority.execution_authority == "none"
    assert window.state == "not_configured"
    assert approval.active_approval_count == 0
    assert approval.approvals == []
    assert decision.transmission_authorized is False
    assert "live_authority_disabled_by_default" in decision.reason_codes
    assert "no_active_live_approval" in decision.reason_codes
    assert decision.approval_state_path == result.live_approval_state_path
    assert transmission_result.transmission_attempted is False
    assert transmission_result.adapter_submission_attempted is False
    assert transmission_result.transmission_eligible is False
    assert transmission_result.eligibility_state == "ineligible"
    assert transmission_result.final_state == "not_attempted"
    assert transmission_result.reason_codes == decision.reason_codes
    assert transmission_result.transmission_decision_path == result.live_transmission_decision_path
    assert status.live_authority_state_path == result.live_authority_state_path
    assert status.live_launch_window_path == result.live_launch_window_path
    assert status.live_transmission_decision_path == result.live_transmission_decision_path
    assert status.live_transmission_result_path == result.live_transmission_result_path
    assert status.live_approval_state_path == result.live_approval_state_path


def test_forward_runtime_materializes_active_limited_live_launch_window_when_in_window(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)

    result = run_forward_paper_runtime(
        Path("tests/fixtures/paper_candles_breakout_long.jsonl"),
        settings=settings,
        runtime_id="limited-live-window-active",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 12, 12, 0)],
        market_source="replay",
        live_launch_window_starts_at=_ts(2026, 4, 12, 11, 55),
        live_launch_window_ends_at=_ts(2026, 4, 12, 12, 5),
    )

    window = LiveLaunchWindowArtifact.model_validate(
        json.loads(result.live_launch_window_path.read_text(encoding="utf-8"))
    )

    assert window.configured is True
    assert window.state == "active"
    assert window.reason_codes == []


def test_forward_runtime_materializes_enabled_limited_live_authority_when_requested(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)

    result = run_forward_paper_runtime(
        Path("tests/fixtures/paper_candles_breakout_long.jsonl"),
        settings=settings,
        runtime_id="limited-live-authority-enabled",
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[_ts(2026, 4, 13, 12, 0)],
        market_source="replay",
        limited_live_authority_enabled=True,
    )

    authority = LiveAuthorityStateArtifact.model_validate(
        json.loads(result.live_authority_state_path.read_text(encoding="utf-8"))
    )

    assert authority.authority_enabled is True
    assert authority.execution_authority == "limited_live"
    assert authority.scope == "tiny_limited_live"
    assert authority.reason_codes == []


def test_forward_runtime_marks_positive_path_transmission_eligibility_without_transmitting(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "limited-live-eligibility-positive"
    tick_time = _ts(2026, 4, 13, 12, 0)
    _write_active_live_approval(tmp_path=tmp_path, runtime_id=runtime_id, generated_at=tick_time)

    readiness = default_live_readiness_status(
        runtime_id=runtime_id,
        updated_at=tick_time,
    ).model_copy(update={"limited_live_gate_status": "ready_for_review"})
    controls = default_live_control_config(
        runtime_id=runtime_id,
        settings=settings,
        updated_at=tick_time,
    )

    result = run_forward_paper_runtime(
        Path("tests/fixtures/paper_candles_breakout_long.jsonl"),
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        max_sessions=1,
        tick_times=[tick_time],
        market_source="replay",
        limited_live_authority_enabled=True,
        live_launch_window_starts_at=_ts(2026, 4, 13, 11, 55),
        live_launch_window_ends_at=_ts(2026, 4, 13, 12, 5),
        readiness_status=readiness,
        live_control_config=controls,
    )

    decision = LiveTransmissionDecisionArtifact.model_validate(
        json.loads(result.live_transmission_decision_path.read_text(encoding="utf-8"))
    )
    transmission_result = LiveTransmissionRuntimeResultArtifact.model_validate(
        json.loads(result.live_transmission_result_path.read_text(encoding="utf-8"))
    )

    assert decision.transmission_authorized is True
    assert decision.decision == "authorized"
    assert transmission_result.transmission_eligible is True
    assert transmission_result.eligibility_state == "eligible"
    assert transmission_result.transmission_attempted is False
    assert transmission_result.adapter_submission_attempted is False
    assert transmission_result.final_state == "not_attempted"
    assert transmission_result.reason_codes == []
