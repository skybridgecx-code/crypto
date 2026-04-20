from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from crypto_agent.cli.main import PaperRunResult, run_paper_replay
from crypto_agent.config import Settings
from crypto_agent.enums import Mode
from crypto_agent.execution.live_adapter import LiveExecutionAdapter, SandboxExecutionAdapter
from crypto_agent.execution.models import (
    ExecutionRequestArtifact,
    ExecutionResultArtifact,
    ExecutionStatusArtifact,
    LiveTransmissionAck,
    LiveTransmissionOrderState,
    LiveTransmissionRequest,
    LiveTransmissionRequestArtifact,
    LiveTransmissionResultArtifact,
    LiveTransmissionStateArtifact,
)
from crypto_agent.execution.sandbox import execute_sandbox_requests
from crypto_agent.execution.shadow import (
    build_execution_request_artifact,
    build_shadow_execution_artifacts,
)
from crypto_agent.market_data.live_adapter import (
    BinanceSpotLiveMarketDataAdapter,
    LiveMarketDataUnavailableError,
)
from crypto_agent.market_data.live_models import LiveFeedHealth, LiveMarketState
from crypto_agent.market_data.models import BookLevel, OrderBookSnapshot
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.market_data.venue_constraints import (
    VenueConstraintRegistry,
    VenueSymbolConstraints,
)
from crypto_agent.policy.live_controls import (
    LiveControlConfig,
    LiveControlDecision,
    LiveControlStatusArtifact,
    ManualControlState,
    build_limited_live_transmission_decision_artifact,
    build_live_control_status_artifact,
    default_live_control_config,
    default_manual_control_state,
    evaluate_post_run_controls,
    evaluate_preflight_controls,
)
from crypto_agent.policy.live_gate import (
    build_live_gate_decision,
    build_live_gate_report,
    build_live_gate_threshold_summary,
    default_live_gate_config,
)
from crypto_agent.policy.readiness import LiveReadinessStatus, default_live_readiness_status
from crypto_agent.runtime.canary import build_forward_paper_shadow_canary_evaluation
from crypto_agent.runtime.history import append_forward_paper_history
from crypto_agent.runtime.launch_verdict import build_live_launch_verdict
from crypto_agent.runtime.models import (
    ForwardPaperHistoryEvent,
    ForwardPaperRuntimeAccountState,
    ForwardPaperRuntimePaths,
    ForwardPaperRuntimeResult,
    ForwardPaperRuntimeStatus,
    ForwardPaperSessionSkipEvidence,
    ForwardPaperSessionSummary,
    LiveApprovalStateArtifact,
    LiveAuthorityStateArtifact,
    LiveLaunchWindowArtifact,
    LiveMarketPreflightArtifact,
    LiveMarketPreflightResult,
    LiveTransmissionDecisionArtifact,
    LiveTransmissionRuntimeResultArtifact,
)
from crypto_agent.runtime.reconciliation import (
    RuntimeAccountMismatchError,
    load_reconciliation_report,
    reconcile_forward_paper_runtime,
)
from crypto_agent.runtime.session_registry import upsert_forward_paper_registry_entry
from crypto_agent.runtime.shadow_evaluation import build_forward_paper_shadow_evaluation
from crypto_agent.runtime.soak import (
    build_forward_paper_soak_evaluation,
    load_runtime_session_summaries,
)


class RuntimeAlreadyActiveError(RuntimeError):
    pass


@dataclass(frozen=True)
class _LivePollResult:
    market_state: LiveMarketState
    attempt_count_used: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("scheduled tick timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _write_runtime_status(status: ForwardPaperRuntimeStatus) -> None:
    status.status_path.parent.mkdir(parents=True, exist_ok=True)
    status.status_path.write_text(
        json.dumps(status.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_runtime_status(path: Path) -> ForwardPaperRuntimeStatus:
    return ForwardPaperRuntimeStatus.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _session_summary_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.json"


def _session_market_input_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.live_input.jsonl"


def _session_market_state_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.live_market_state.json"


def _session_execution_request_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.execution_requests.json"


def _session_execution_result_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.execution_results.json"


def _session_execution_status_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.execution_status.json"


def _session_live_transmission_request_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.live_transmission_request.json"


def _session_live_transmission_result_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.live_transmission_result.json"


def _session_live_transmission_state_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.live_transmission_state.json"


def _session_control_decision_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.control_decision.json"


def _session_skip_evidence_path(sessions_dir: Path, session_id: str) -> Path:
    return sessions_dir / f"{session_id}.skip_evidence.json"


def _write_session_summary(summary: ForwardPaperSessionSummary, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(summary.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_session_summary(path: Path) -> ForwardPaperSessionSummary:
    return ForwardPaperSessionSummary.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _write_json_artifact(path: Path, model: BaseModel) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _build_live_authority_state_artifact(
    *,
    runtime_id: str,
    generated_at: datetime,
    authority_enabled: bool,
) -> LiveAuthorityStateArtifact:
    if not authority_enabled:
        return LiveAuthorityStateArtifact(
            runtime_id=runtime_id,
            generated_at=generated_at,
            authority_enabled=False,
            execution_authority="none",
            scope="disabled",
            summary="Limited-live authority is disabled by default.",
            reason_codes=["live_authority_disabled_by_default"],
        )

    return LiveAuthorityStateArtifact(
        runtime_id=runtime_id,
        generated_at=generated_at,
        authority_enabled=True,
        execution_authority="limited_live",
        scope="tiny_limited_live",
        summary="Limited-live authority is explicitly enabled for this runtime.",
        reason_codes=[],
    )


def _build_live_launch_window_artifact(
    *,
    runtime_id: str,
    generated_at: datetime,
    starts_at: datetime | None,
    ends_at: datetime | None,
) -> LiveLaunchWindowArtifact:
    if starts_at is None or ends_at is None:
        return LiveLaunchWindowArtifact(
            runtime_id=runtime_id,
            generated_at=generated_at,
            configured=False,
            state="not_configured",
            starts_at=starts_at,
            ends_at=ends_at,
            summary="No limited-live launch window is configured.",
            reason_codes=["launch_window_not_configured"],
        )

    if generated_at < starts_at:
        return LiveLaunchWindowArtifact(
            runtime_id=runtime_id,
            generated_at=generated_at,
            configured=True,
            state="scheduled",
            starts_at=starts_at,
            ends_at=ends_at,
            summary="Limited-live launch window is scheduled but not active yet.",
            reason_codes=["launch_window_not_active_yet"],
        )

    if generated_at > ends_at:
        return LiveLaunchWindowArtifact(
            runtime_id=runtime_id,
            generated_at=generated_at,
            configured=True,
            state="expired",
            starts_at=starts_at,
            ends_at=ends_at,
            summary="Limited-live launch window has expired.",
            reason_codes=["launch_window_expired"],
        )

    return LiveLaunchWindowArtifact(
        runtime_id=runtime_id,
        generated_at=generated_at,
        configured=True,
        state="active",
        starts_at=starts_at,
        ends_at=ends_at,
        summary="Limited-live launch window is active.",
        reason_codes=[],
    )


def _ensure_limited_live_foundation_artifacts(
    *,
    runtime_id: str,
    paths: ForwardPaperRuntimePaths,
    generated_at: datetime,
    limited_live_authority_enabled: bool,
    live_launch_window_starts_at: datetime | None,
    live_launch_window_ends_at: datetime | None,
) -> None:
    authority_artifact = _build_live_authority_state_artifact(
        runtime_id=runtime_id,
        generated_at=generated_at,
        authority_enabled=limited_live_authority_enabled,
    )
    rewrite_authority = not paths.live_authority_state_path.exists()
    if not rewrite_authority:
        existing_payload = json.loads(paths.live_authority_state_path.read_text(encoding="utf-8"))
        desired_payload = authority_artifact.model_dump(mode="json")
        rewrite_authority = (
            existing_payload.get("authority_enabled") != desired_payload.get("authority_enabled")
            or existing_payload.get("execution_authority")
            != desired_payload.get("execution_authority")
            or existing_payload.get("scope") != desired_payload.get("scope")
        )
    if rewrite_authority:
        _write_json_artifact(paths.live_authority_state_path, authority_artifact)
    launch_window_artifact = _build_live_launch_window_artifact(
        runtime_id=runtime_id,
        generated_at=generated_at,
        starts_at=live_launch_window_starts_at,
        ends_at=live_launch_window_ends_at,
    )
    rewrite_launch_window = not paths.live_launch_window_path.exists()
    if not rewrite_launch_window:
        existing_payload = json.loads(paths.live_launch_window_path.read_text(encoding="utf-8"))
        desired_payload = launch_window_artifact.model_dump(mode="json")
        rewrite_launch_window = (
            existing_payload.get("configured") != desired_payload.get("configured")
            or existing_payload.get("state") != desired_payload.get("state")
            or existing_payload.get("starts_at") != desired_payload.get("starts_at")
            or existing_payload.get("ends_at") != desired_payload.get("ends_at")
        )
    if rewrite_launch_window:
        _write_json_artifact(paths.live_launch_window_path, launch_window_artifact)
    if not paths.live_approval_state_path.exists():
        _write_json_artifact(
            paths.live_approval_state_path,
            LiveApprovalStateArtifact(
                runtime_id=runtime_id,
                generated_at=generated_at,
                summary="No live approvals are active. Limited-live transmission remains denied.",
                reason_codes=["no_active_live_approval"],
            ),
        )
    rewrite_transmission_decision = not paths.live_transmission_decision_path.exists()
    if not rewrite_transmission_decision:
        decision_payload = json.loads(
            paths.live_transmission_decision_path.read_text(encoding="utf-8")
        )
        rewrite_transmission_decision = "approval_state_path" not in decision_payload
    if rewrite_transmission_decision:
        _write_json_artifact(
            paths.live_transmission_decision_path,
            LiveTransmissionDecisionArtifact(
                runtime_id=runtime_id,
                generated_at=generated_at,
                reason_codes=[
                    "live_authority_disabled_by_default",
                    "launch_window_not_configured",
                    "no_active_live_approval",
                ],
                authority_state_path=paths.live_authority_state_path,
                launch_window_path=paths.live_launch_window_path,
                approval_state_path=paths.live_approval_state_path,
            ),
        )
    decision = LiveTransmissionDecisionArtifact.model_validate(
        json.loads(paths.live_transmission_decision_path.read_text(encoding="utf-8"))
    )
    _write_json_artifact(
        paths.live_transmission_result_path,
        _build_live_transmission_result_artifact(
            runtime_id=runtime_id,
            generated_at=generated_at,
            decision=decision,
            decision_path=paths.live_transmission_decision_path,
        ),
    )


def _build_live_transmission_result_artifact(
    *,
    runtime_id: str,
    generated_at: datetime,
    decision: LiveTransmissionDecisionArtifact,
    decision_path: Path,
) -> LiveTransmissionRuntimeResultArtifact:
    return LiveTransmissionRuntimeResultArtifact(
        runtime_id=runtime_id,
        generated_at=generated_at,
        transmission_attempted=False,
        adapter_submission_attempted=False,
        final_state="not_attempted",
        summary=(
            "No live transmission attempt executed. "
            "Runtime remains artifact-only and deny-by-default."
        ),
        reason_codes=list(decision.reason_codes),
        transmission_decision_path=decision_path,
    )


def _load_live_control_config(path: Path) -> LiveControlConfig:
    return LiveControlConfig.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_readiness_status(path: Path) -> LiveReadinessStatus:
    return LiveReadinessStatus.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_manual_control_state(path: Path) -> ManualControlState:
    return ManualControlState.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_control_decision(path: Path) -> LiveControlDecision:
    return LiveControlDecision.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_live_control_status(path: Path) -> LiveControlStatusArtifact:
    return LiveControlStatusArtifact.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _load_live_transmission_decision(path: Path) -> LiveTransmissionDecisionArtifact:
    return LiveTransmissionDecisionArtifact.model_validate(
        json.loads(path.read_text(encoding="utf-8"))
    )


def _load_live_market_preflight_artifact(path: Path) -> LiveMarketPreflightArtifact | None:
    if not path.exists():
        return None
    return LiveMarketPreflightArtifact.model_validate(json.loads(path.read_text(encoding="utf-8")))


def _requested_symbols_from_replay(path: Path) -> list[str]:
    return sorted({candle.symbol for candle in load_candle_replay(path)})


def _last_completed_session(
    status: ForwardPaperRuntimeStatus,
) -> ForwardPaperSessionSummary | None:
    if status.last_session_id is None:
        return None
    session_path = _session_summary_path(status.sessions_dir, status.last_session_id)
    if not session_path.exists():
        return None
    summary = _load_session_summary(session_path)
    if summary.status != "completed":
        return None
    return summary


def build_forward_paper_runtime_paths(
    runs_dir: Path,
    runtime_id: str,
) -> ForwardPaperRuntimePaths:
    runtime_dir = runs_dir / runtime_id
    return ForwardPaperRuntimePaths(
        runtime_dir=runtime_dir,
        status_path=runtime_dir / "forward_paper_status.json",
        history_path=runtime_dir / "forward_paper_history.jsonl",
        sessions_dir=runtime_dir / "sessions",
        registry_path=runs_dir / "forward_paper_registry.json",
        live_market_status_path=runtime_dir / "live_market_status.json",
        venue_constraints_path=runtime_dir / "venue_constraints.json",
        account_state_path=runtime_dir / "account_state.json",
        reconciliation_report_path=runtime_dir / "reconciliation_report.json",
        recovery_status_path=runtime_dir / "recovery_status.json",
        execution_state_dir=runtime_dir / "execution",
        live_control_config_path=runtime_dir / "live_control_config.json",
        live_control_status_path=runtime_dir / "live_control_status.json",
        readiness_status_path=runtime_dir / "live_readiness_status.json",
        manual_control_state_path=runtime_dir / "manual_control_state.json",
        shadow_canary_evaluation_path=runtime_dir / "shadow_canary_evaluation.json",
        soak_evaluation_path=runtime_dir / "soak_evaluation.json",
        shadow_evaluation_path=runtime_dir / "shadow_evaluation.json",
        live_market_preflight_path=runtime_dir / "live_market_preflight.json",
        live_gate_decision_path=runtime_dir / "live_gate_decision.json",
        live_gate_threshold_summary_path=runtime_dir / "live_gate_threshold_summary.json",
        live_gate_report_path=runtime_dir / "live_gate_report.md",
        live_launch_verdict_path=runtime_dir / "live_launch_verdict.json",
        live_authority_state_path=runtime_dir / "live_authority_state.json",
        live_launch_window_path=runtime_dir / "live_launch_window.json",
        live_transmission_decision_path=runtime_dir / "live_transmission_decision.json",
        live_transmission_result_path=runtime_dir / "live_transmission_result.json",
        live_approval_state_path=runtime_dir / "live_approval_state.json",
    )


def _persist_runtime_status(status: ForwardPaperRuntimeStatus) -> None:
    _write_runtime_status(status)
    upsert_forward_paper_registry_entry(status.registry_path, status)


def _build_replay_fixture_market_state(
    replay_path: Path,
    *,
    stale_after_seconds: int,
) -> LiveMarketState:
    candles = load_candle_replay(replay_path)
    if not candles:
        raise ValueError("Replay fixture rehearsal requires at least one candle")

    last_candle = candles[-1]
    close_price = last_candle.close
    tick_size = 0.1
    step_size = 0.001
    bid_price = max(tick_size, close_price - tick_size)
    ask_price = close_price + tick_size
    symbol = last_candle.symbol
    quote_asset = symbol[-4:] if len(symbol) > 4 else "USDT"
    base_asset = symbol[:-4] if len(symbol) > 4 else symbol
    constraints = VenueSymbolConstraints(
        venue="binance_spot",
        symbol=symbol,
        status="TRADING",
        base_asset=base_asset,
        quote_asset=quote_asset,
        tick_size=tick_size,
        step_size=step_size,
        min_quantity=step_size,
        min_notional=10.0,
    )
    observed_at = last_candle.close_time
    return LiveMarketState(
        venue="binance_spot",
        symbol=symbol,
        interval=last_candle.interval,
        polled_at=observed_at,
        candles=candles,
        order_book=OrderBookSnapshot(
            venue="binance_spot",
            symbol=symbol,
            timestamp=observed_at,
            bids=[BookLevel(price=bid_price, quantity=1.0)],
            asks=[BookLevel(price=ask_price, quantity=1.0)],
        ),
        constraints=constraints,
        constraint_registry=VenueConstraintRegistry(
            venue="binance_spot_testnet",
            updated_at=observed_at,
            symbol_constraints=[constraints],
        ),
        feed_health=LiveFeedHealth(
            status="healthy",
            observed_at=observed_at,
            last_success_at=observed_at,
            last_candle_close_time=last_candle.close_time,
            stale_after_seconds=stale_after_seconds,
        ),
    )


def _write_live_market_state(paths: ForwardPaperRuntimePaths, state: LiveMarketState) -> None:
    paths.live_market_status_path.write_text(
        json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    paths.venue_constraints_path.write_text(
        json.dumps(state.constraint_registry.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_live_market_input(path: Path, state: LiveMarketState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for candle in state.candles:
            handle.write(json.dumps(candle.model_dump(mode="json"), sort_keys=True) + "\n")


def _write_execution_artifact(
    path: Path,
    artifact: ExecutionRequestArtifact | ExecutionResultArtifact | ExecutionStatusArtifact,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(artifact.model_dump(mode="json"), indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _build_live_transmission_request_artifact(
    *,
    runtime_id: str,
    session_id: str,
    run_id: str,
    generated_at: datetime,
    request_artifact: ExecutionRequestArtifact | None,
) -> LiveTransmissionRequestArtifact:
    requests: list[LiveTransmissionRequest] = []
    rejected_request_count = 0
    if request_artifact is not None:
        for request in request_artifact.requests:
            requests.append(
                LiveTransmissionRequest(
                    request_id=request.request_id,
                    client_order_id=request.client_order_id,
                    venue=request.venue,
                    proposal_id=request.proposal_id,
                    intent_id=request.intent_id,
                    symbol=request.symbol,
                    side=request.side,
                    order_type=request.order_type,
                    time_in_force=request.time_in_force,
                    quantity=request.quantity,
                    price=request.price,
                    reference_price=request.reference_price,
                    estimated_notional_usd=request.estimated_notional_usd,
                    min_notional_usd=request.min_notional_usd,
                    normalization_status=request.normalization_status,
                    normalization_reject_reason=request.normalization_reject_reason,
                )
            )
            if request.normalization_status == "rejected":
                rejected_request_count += 1
    return LiveTransmissionRequestArtifact(
        runtime_id=runtime_id,
        session_id=session_id,
        run_id=run_id,
        generated_at=generated_at,
        request_count=len(requests),
        rejected_request_count=rejected_request_count,
        requests=requests,
    )


def _clear_live_market_state_artifacts(paths: ForwardPaperRuntimePaths) -> None:
    for path in (paths.live_market_status_path, paths.venue_constraints_path):
        if path.exists():
            path.unlink()


def _initial_runtime_status(
    *,
    runtime_id: str,
    execution_mode: Literal["paper", "shadow", "sandbox"],
    market_source: Literal["replay", "binance_spot"],
    replay_path: Path | None,
    live_symbol: str | None,
    live_interval: str | None,
    live_lookback_candles: int | None,
    feed_stale_after_seconds: int | None,
    binance_base_url: str | None,
    starting_equity_usd: float,
    session_interval_seconds: int,
    now: datetime,
    paths: ForwardPaperRuntimePaths,
) -> ForwardPaperRuntimeStatus:
    return ForwardPaperRuntimeStatus(
        runtime_id=runtime_id,
        mode=Mode.PAPER,
        execution_mode=execution_mode,
        market_source=market_source,
        replay_path=replay_path,
        live_symbol=live_symbol,
        live_interval=live_interval,
        live_lookback_candles=live_lookback_candles,
        feed_stale_after_seconds=feed_stale_after_seconds,
        binance_base_url=binance_base_url,
        starting_equity_usd=starting_equity_usd,
        session_interval_seconds=session_interval_seconds,
        status="idle",
        next_session_number=1,
        updated_at=now,
        status_path=paths.status_path,
        history_path=paths.history_path,
        sessions_dir=paths.sessions_dir,
        registry_path=paths.registry_path,
        live_market_status_path=paths.live_market_status_path,
        venue_constraints_path=paths.venue_constraints_path,
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
        live_authority_state_path=paths.live_authority_state_path,
        live_launch_window_path=paths.live_launch_window_path,
        live_transmission_decision_path=paths.live_transmission_decision_path,
        live_transmission_result_path=paths.live_transmission_result_path,
        live_approval_state_path=paths.live_approval_state_path,
    )


def _ensure_runtime_status(
    *,
    settings: Settings,
    execution_mode: Literal["paper", "shadow", "sandbox"],
    market_source: Literal["replay", "binance_spot"],
    sandbox_fixture_rehearsal: bool = False,
    replay_path: Path | None,
    live_symbol: str | None,
    live_interval: str | None,
    live_lookback_candles: int | None,
    feed_stale_after_seconds: int | None,
    binance_base_url: str | None,
    runtime_id: str,
    starting_equity_usd: float,
    session_interval_seconds: int,
    now: datetime,
    recover_interrupted: bool,
) -> tuple[
    ForwardPaperRuntimeStatus,
    ForwardPaperRuntimeAccountState,
    str | None,
    str | None,
]:
    if settings.mode is not Mode.PAPER:
        raise ValueError("Forward paper runtime requires settings.mode to be paper.")

    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    runtime_dir = paths.runtime_dir
    summary_conflict = runtime_dir / "summary.json"
    manifest_conflict = runtime_dir / "manifest.json"
    if runtime_dir.exists() and (summary_conflict.exists() or manifest_conflict.exists()):
        raise ValueError(f"Runtime id conflicts with existing run artifacts: {runtime_id}")

    runtime_dir.mkdir(parents=True, exist_ok=True)
    paths.sessions_dir.mkdir(parents=True, exist_ok=True)
    paths.execution_state_dir.mkdir(parents=True, exist_ok=True)

    if market_source == "replay" and replay_path is None:
        raise ValueError("Replay market source requires replay_path")
    if market_source == "binance_spot" and (
        live_symbol is None
        or live_interval is None
        or live_lookback_candles is None
        or feed_stale_after_seconds is None
    ):
        raise ValueError(
            "Live market source requires symbol, interval, lookback, and stale feed threshold"
        )
    if execution_mode in {"shadow", "sandbox"} and market_source != "binance_spot":
        if not (
            sandbox_fixture_rehearsal and execution_mode == "sandbox" and market_source == "replay"
        ):
            raise ValueError(
                "Shadow and sandbox execution modes require binance_spot market source."
            )

    if not paths.status_path.exists():
        status = _initial_runtime_status(
            runtime_id=runtime_id,
            execution_mode=execution_mode,
            market_source=market_source,
            replay_path=replay_path,
            live_symbol=live_symbol,
            live_interval=live_interval,
            live_lookback_candles=live_lookback_candles,
            feed_stale_after_seconds=feed_stale_after_seconds,
            binance_base_url=binance_base_url,
            starting_equity_usd=starting_equity_usd,
            session_interval_seconds=session_interval_seconds,
            now=now,
            paths=paths,
        )
        _persist_runtime_status(status)
        reconciled_status, reconciled_account_state, _, _ = reconcile_forward_paper_runtime(
            status=status,
            paths=paths,
            reconciled_at=now,
        )
        _persist_runtime_status(reconciled_status)
        return reconciled_status, reconciled_account_state, None, None

    status = _load_runtime_status(paths.status_path)
    status = status.model_copy(
        update={
            "live_authority_state_path": paths.live_authority_state_path,
            "live_launch_window_path": paths.live_launch_window_path,
            "live_transmission_decision_path": paths.live_transmission_decision_path,
            "live_transmission_result_path": paths.live_transmission_result_path,
            "live_approval_state_path": paths.live_approval_state_path,
        }
    )
    if status.execution_mode != execution_mode:
        raise ValueError("Existing runtime execution_mode does not match requested value")
    if status.market_source != market_source:
        raise ValueError("Existing runtime market_source does not match requested market_source")
    if status.replay_path != replay_path:
        raise ValueError("Existing runtime replay_path does not match requested replay_path")
    if status.live_symbol != live_symbol:
        raise ValueError("Existing runtime live_symbol does not match requested value")
    if status.live_interval != live_interval:
        raise ValueError("Existing runtime live_interval does not match requested value")
    if status.live_lookback_candles != live_lookback_candles:
        raise ValueError("Existing runtime lookback does not match requested value")
    if status.feed_stale_after_seconds != feed_stale_after_seconds:
        raise ValueError("Existing runtime stale-feed threshold does not match requested value")
    if status.starting_equity_usd != starting_equity_usd:
        raise ValueError("Existing runtime starting_equity_usd does not match requested value")
    if status.session_interval_seconds != session_interval_seconds:
        raise ValueError("Existing runtime interval does not match requested value")
    recovered_session_id = None
    recovery_note = None
    if status.status == "running" and status.active_session_id is not None:
        if not recover_interrupted:
            raise RuntimeAlreadyActiveError(
                f"Forward paper runtime is already active: {runtime_id}"
            )
        status, recovered_session_id, recovery_note = _recover_interrupted_session(
            status=status,
            recovered_at=now,
        )

    reconciled_status, account_state, _, _ = reconcile_forward_paper_runtime(
        status=status,
        paths=paths,
        reconciled_at=now,
        recovered_session_id=recovered_session_id,
        recovery_note=recovery_note,
    )
    _persist_runtime_status(reconciled_status)
    if reconciled_status.mismatch_detected:
        raise RuntimeAccountMismatchError(
            f"Forward paper runtime account state mismatch detected: {runtime_id}"
        )
    return reconciled_status, account_state, recovered_session_id, recovery_note


def _resolve_control_surfaces(
    *,
    runtime_id: str,
    settings: Settings,
    paths: ForwardPaperRuntimePaths,
    updated_at: datetime,
    live_control_config: LiveControlConfig | None,
    readiness_status: LiveReadinessStatus | None,
    manual_control_state: ManualControlState | None,
) -> tuple[LiveControlConfig, LiveReadinessStatus, ManualControlState]:
    if live_control_config is not None:
        resolved_controls = live_control_config
    elif paths.live_control_config_path.exists():
        resolved_controls = _load_live_control_config(paths.live_control_config_path)
    else:
        resolved_controls = default_live_control_config(
            runtime_id=runtime_id,
            settings=settings,
            updated_at=updated_at,
        )

    if readiness_status is not None:
        resolved_readiness = readiness_status
    elif paths.readiness_status_path.exists():
        resolved_readiness = _load_readiness_status(paths.readiness_status_path)
    else:
        resolved_readiness = default_live_readiness_status(
            runtime_id=runtime_id,
            updated_at=updated_at,
        )

    if manual_control_state is not None:
        resolved_manual_controls = manual_control_state
    elif paths.manual_control_state_path.exists():
        resolved_manual_controls = _load_manual_control_state(paths.manual_control_state_path)
    else:
        resolved_manual_controls = default_manual_control_state(
            runtime_id=runtime_id,
            updated_at=updated_at,
        )

    if resolved_controls.runtime_id != runtime_id:
        raise ValueError("live control config runtime_id does not match runtime")
    if resolved_readiness.runtime_id != runtime_id:
        raise ValueError("readiness status runtime_id does not match runtime")
    if resolved_manual_controls.runtime_id != runtime_id:
        raise ValueError("manual control state runtime_id does not match runtime")

    resolved_controls = resolved_controls.model_copy(update={"updated_at": updated_at})
    resolved_readiness = resolved_readiness.model_copy(update={"updated_at": updated_at})
    resolved_manual_controls = resolved_manual_controls.model_copy(
        update={"updated_at": updated_at}
    )

    _write_json_artifact(paths.live_control_config_path, resolved_controls)
    _write_json_artifact(paths.readiness_status_path, resolved_readiness)
    _write_json_artifact(paths.manual_control_state_path, resolved_manual_controls)
    return resolved_controls, resolved_readiness, resolved_manual_controls


def _recover_interrupted_session(
    *,
    status: ForwardPaperRuntimeStatus,
    recovered_at: datetime,
) -> tuple[ForwardPaperRuntimeStatus, str | None, str | None]:
    if status.active_session_id is None:
        return (
            status.model_copy(update={"status": "idle", "updated_at": recovered_at}),
            None,
            None,
        )

    session_path = _session_summary_path(status.sessions_dir, status.active_session_id)
    if session_path.exists():
        session_summary = _load_session_summary(session_path).model_copy(
            update={
                "status": "interrupted",
                "completed_at": recovered_at,
                "recovery_note": "recovered_after_restart",
                "all_artifact_paths_exist": False,
            }
        )
    else:
        session_number = status.next_session_number - 1 if status.next_session_number > 1 else 1
        session_summary = ForwardPaperSessionSummary(
            runtime_id=status.runtime_id,
            session_id=status.active_session_id,
            session_number=session_number,
            mode=Mode.PAPER,
            execution_mode=status.execution_mode,
            market_source=status.market_source,
            live_symbol=status.live_symbol,
            live_interval=status.live_interval,
            status="interrupted",
            replay_path=status.replay_path,
            venue_constraints_path=(
                status.venue_constraints_path if status.market_source == "binance_spot" else None
            ),
            scheduled_at=status.active_session_started_at or recovered_at,
            started_at=status.active_session_started_at or recovered_at,
            completed_at=recovered_at,
            recovery_note="recovered_after_restart_without_session_file",
            all_artifact_paths_exist=False,
        )

    _write_session_summary(session_summary, session_path)
    append_forward_paper_history(
        status.history_path,
        ForwardPaperHistoryEvent(
            event_type="session.interrupted",
            runtime_id=status.runtime_id,
            session_id=session_summary.session_id,
            session_number=session_summary.session_number,
            occurred_at=recovered_at,
            status="interrupted",
            message=session_summary.recovery_note,
        ),
    )

    recovered_status = status.model_copy(
        update={
            "status": "idle",
            "active_session_id": None,
            "active_session_started_at": None,
            "last_session_id": session_summary.session_id,
            "interrupted_session_count": status.interrupted_session_count + 1,
            "updated_at": recovered_at,
        }
    )
    _persist_runtime_status(recovered_status)
    return recovered_status, session_summary.session_id, session_summary.recovery_note


def _start_session(
    *,
    status: ForwardPaperRuntimeStatus,
    scheduled_at: datetime,
) -> tuple[ForwardPaperRuntimeStatus, ForwardPaperSessionSummary, Path]:
    session_number = status.next_session_number
    session_id = f"session-{session_number:04d}"
    session_summary = ForwardPaperSessionSummary(
        runtime_id=status.runtime_id,
        session_id=session_id,
        session_number=session_number,
        mode=Mode.PAPER,
        execution_mode=status.execution_mode,
        market_source=status.market_source,
        live_symbol=status.live_symbol,
        live_interval=status.live_interval,
        status="running",
        replay_path=status.replay_path,
        venue_constraints_path=(
            status.venue_constraints_path if status.market_source == "binance_spot" else None
        ),
        scheduled_at=scheduled_at,
        started_at=scheduled_at,
        all_artifact_paths_exist=False,
    )
    session_path = _session_summary_path(status.sessions_dir, session_id)
    _write_session_summary(session_summary, session_path)
    append_forward_paper_history(
        status.history_path,
        ForwardPaperHistoryEvent(
            event_type="session.started",
            runtime_id=status.runtime_id,
            session_id=session_id,
            session_number=session_number,
            occurred_at=scheduled_at,
            status="running",
        ),
    )

    running_status = status.model_copy(
        update={
            "status": "running",
            "next_session_number": session_number + 1,
            "active_session_id": session_id,
            "active_session_started_at": scheduled_at,
            "updated_at": scheduled_at,
        }
    )
    _persist_runtime_status(running_status)
    return running_status, session_summary, session_path


def _completed_session_summary(
    *,
    session_summary: ForwardPaperSessionSummary,
    result: PaperRunResult,
    completed_at: datetime,
) -> ForwardPaperSessionSummary:
    path_exists = {
        "journal_path": result.journal_path.exists(),
        "summary_path": result.summary_path.exists(),
        "report_path": result.report_path.exists(),
        "trade_ledger_path": result.trade_ledger_path.exists(),
    }
    if session_summary.market_input_path is not None:
        path_exists["market_input_path"] = session_summary.market_input_path.exists()
    if session_summary.market_state_path is not None:
        path_exists["market_state_path"] = session_summary.market_state_path.exists()
    if session_summary.venue_constraints_path is not None:
        path_exists["venue_constraints_path"] = session_summary.venue_constraints_path.exists()
    return session_summary.model_copy(
        update={
            "status": "completed",
            "session_outcome": "executed",
            "completed_at": completed_at,
            "run_id": result.run_id,
            "journal_path": result.journal_path,
            "summary_path": result.summary_path,
            "report_path": result.report_path,
            "trade_ledger_path": result.trade_ledger_path,
            "quality_issue_count": result.quality_issue_count,
            "scorecard": result.scorecard,
            "pnl": result.pnl,
            "review_packet": result.review_packet,
            "operator_summary": result.operator_summary,
            "artifact_paths_exist": path_exists,
            "all_artifact_paths_exist": all(path_exists.values()),
        }
    )


def _skipped_session_summary(
    *,
    session_summary: ForwardPaperSessionSummary,
    completed_at: datetime,
    outcome: str,
    feed_health: LiveFeedHealth,
) -> ForwardPaperSessionSummary:
    path_exists = {}
    if session_summary.market_input_path is not None:
        path_exists["market_input_path"] = session_summary.market_input_path.exists()
    if session_summary.market_state_path is not None:
        path_exists["market_state_path"] = session_summary.market_state_path.exists()
    if session_summary.venue_constraints_path is not None:
        path_exists["venue_constraints_path"] = session_summary.venue_constraints_path.exists()
    return session_summary.model_copy(
        update={
            "status": "completed",
            "session_outcome": outcome,
            "completed_at": completed_at,
            "feed_health": feed_health,
            "artifact_paths_exist": path_exists,
            "all_artifact_paths_exist": all(path_exists.values()) if path_exists else True,
        }
    )


def _blocked_session_summary(
    *,
    session_summary: ForwardPaperSessionSummary,
    completed_at: datetime,
    control_decision: LiveControlDecision,
) -> ForwardPaperSessionSummary:
    path_exists = dict(session_summary.artifact_paths_exist)
    if session_summary.market_input_path is not None:
        path_exists["market_input_path"] = session_summary.market_input_path.exists()
    if session_summary.market_state_path is not None:
        path_exists["market_state_path"] = session_summary.market_state_path.exists()
    if session_summary.venue_constraints_path is not None:
        path_exists["venue_constraints_path"] = session_summary.venue_constraints_path.exists()
    return session_summary.model_copy(
        update={
            "status": "completed",
            "session_outcome": "blocked_controls",
            "completed_at": completed_at,
            "control_action": control_decision.action,
            "control_reason_codes": control_decision.reason_codes,
            "artifact_paths_exist": path_exists,
            "all_artifact_paths_exist": all(path_exists.values()) if path_exists else True,
        }
    )


def _failed_session_summary(
    *,
    session_summary: ForwardPaperSessionSummary,
    failed_at: datetime,
    error: Exception,
) -> ForwardPaperSessionSummary:
    return session_summary.model_copy(
        update={
            "status": "failed",
            "completed_at": failed_at,
            "error_message": str(error),
            "all_artifact_paths_exist": False,
        }
    )


def _complete_status(
    *,
    status: ForwardPaperRuntimeStatus,
    session_summary: ForwardPaperSessionSummary,
    completed_at: datetime,
) -> ForwardPaperRuntimeStatus:
    next_scheduled_at = session_summary.scheduled_at + timedelta(
        seconds=status.session_interval_seconds
    )
    completed_session_count = status.completed_session_count
    failed_session_count = status.failed_session_count
    last_error_message = status.last_error_message
    if session_summary.status == "completed":
        completed_session_count += 1
        last_error_message = None
    elif session_summary.status == "failed":
        failed_session_count += 1
        last_error_message = session_summary.error_message

    completed_status = status.model_copy(
        update={
            "status": "idle",
            "active_session_id": None,
            "active_session_started_at": None,
            "last_session_id": session_summary.session_id,
            "completed_session_count": completed_session_count,
            "failed_session_count": failed_session_count,
            "next_scheduled_at": next_scheduled_at,
            "last_error_message": last_error_message,
            "updated_at": completed_at,
        }
    )
    _persist_runtime_status(completed_status)
    return completed_status


def _iter_scheduled_times(
    *,
    tick_times: Iterable[datetime] | None,
    max_sessions: int | None,
    initial_next_scheduled_at: datetime | None,
    now_fn: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
    interval_seconds: int,
) -> list[datetime]:
    if tick_times is not None:
        normalized = [_normalize_datetime(tick) for tick in tick_times]
        if max_sessions is not None:
            return normalized[:max_sessions]
        return normalized

    if max_sessions is None:
        raise ValueError("Real-clock forward paper runtime requires max_sessions to be explicit.")

    scheduled_times: list[datetime] = []
    next_scheduled_at = initial_next_scheduled_at
    for _ in range(max_sessions):
        due_at = (
            _normalize_datetime(next_scheduled_at)
            if next_scheduled_at is not None
            else _normalize_datetime(now_fn())
        )
        current_time = _normalize_datetime(now_fn())
        delay_seconds = (due_at - current_time).total_seconds()
        if delay_seconds > 0:
            sleep_fn(delay_seconds)
        scheduled_times.append(due_at)
        next_scheduled_at = due_at + timedelta(seconds=interval_seconds)
    return scheduled_times


def _refresh_live_state(
    *,
    status: ForwardPaperRuntimeStatus,
    adapter: BinanceSpotLiveMarketDataAdapter,
    now: datetime,
) -> LiveMarketState:
    if (
        status.live_symbol is None
        or status.live_interval is None
        or status.live_lookback_candles is None
        or status.feed_stale_after_seconds is None
    ):
        raise ValueError("Live runtime status is missing required live market fields")
    return adapter.poll_market_state(
        symbol=status.live_symbol,
        interval=status.live_interval,
        lookback_candles=status.live_lookback_candles,
        stale_after_seconds=status.feed_stale_after_seconds,
        now=now,
    )


def _poll_with_retry_result(
    *,
    status: ForwardPaperRuntimeStatus,
    adapter: BinanceSpotLiveMarketDataAdapter,
    now: datetime,
    retry_count: int,
    retry_delay_seconds: float,
    sleep_fn: Callable[[float], None],
) -> _LivePollResult:
    """Call _refresh_live_state with bounded retry/backoff on LiveMarketDataUnavailableError.

    On success after one or more retries, enriches feed_health.message to record which
    attempt succeeded.  On exhaustion, re-raises with a retries_exhausted note so the
    catch block in the session loop can surface it in the skip evidence artifact.
    """
    total_attempts = 1 + retry_count
    last_exc: LiveMarketDataUnavailableError | None = None
    for attempt in range(total_attempts):
        if attempt > 0:
            sleep_fn(retry_delay_seconds)
        try:
            state = _refresh_live_state(status=status, adapter=adapter, now=now)
            if attempt > 0:
                enriched_message = (
                    f"{state.feed_health.message or 'ok'}"
                    f" | retry_recovery: succeeded on attempt {attempt + 1} of {total_attempts}"
                )
                state = state.model_copy(
                    update={
                        "feed_health": state.feed_health.model_copy(
                            update={"message": enriched_message}
                        )
                    }
                )
            return _LivePollResult(market_state=state, attempt_count_used=attempt + 1)
        except LiveMarketDataUnavailableError as caught:
            last_exc = caught
    if last_exc is None:
        raise LiveMarketDataUnavailableError("poll_with_retry: unexpected empty attempt loop")
    if retry_count > 0:
        raise LiveMarketDataUnavailableError(
            f"{last_exc} | retries_exhausted: failed after {total_attempts} attempts"
        ) from last_exc
    raise last_exc


def _poll_with_retry(
    *,
    status: ForwardPaperRuntimeStatus,
    adapter: BinanceSpotLiveMarketDataAdapter,
    now: datetime,
    retry_count: int,
    retry_delay_seconds: float,
    sleep_fn: Callable[[float], None],
) -> LiveMarketState:
    return _poll_with_retry_result(
        status=status,
        adapter=adapter,
        now=now,
        retry_count=retry_count,
        retry_delay_seconds=retry_delay_seconds,
        sleep_fn=sleep_fn,
    ).market_state


def _build_failed_preflight_artifact(
    *,
    runtime_id: str,
    market_source: Literal["binance_spot"],
    live_symbol: str,
    live_interval: str,
    configured_base_url: str,
    retry_count: int,
    retry_delay_seconds: float,
    attempt_count_used: int,
    observed_at: datetime,
    status: Literal["stale", "unavailable", "retries_exhausted"],
    feed_health_status: Literal["healthy", "stale", "degraded"] | None,
    feed_health_message: str | None,
    required_closed_candle_count: int,
    candle_count: int,
    order_book_present: bool,
    constraints_present: bool,
    batch_readiness_reason: str,
    single_probe_success: bool,
) -> LiveMarketPreflightArtifact:
    return LiveMarketPreflightArtifact(
        runtime_id=runtime_id,
        market_source=market_source,
        symbol=live_symbol,
        interval=live_interval,
        configured_base_url=configured_base_url,
        retry_count=retry_count,
        retry_delay_seconds=retry_delay_seconds,
        attempt_count_used=attempt_count_used,
        observed_at=observed_at,
        status=status,
        success=False,
        single_probe_success=single_probe_success,
        batch_readiness=False,
        batch_readiness_reason=batch_readiness_reason,
        feed_health_status=feed_health_status,
        feed_health_message=feed_health_message,
        required_closed_candle_count=required_closed_candle_count,
        candle_count=candle_count,
        stability_window_probe_count=0 if not single_probe_success else 2,
        stability_window_success_count=1 if single_probe_success else 0,
        stability_window_result="not_run" if not single_probe_success else "failed",
        stability_failure_status=None if not single_probe_success else "unavailable",
        stability_probe_attempt_count_used=None,
        stability_feed_health_status=None,
        stability_feed_health_message=None,
        order_book_present=order_book_present,
        constraints_present=constraints_present,
    )


def _build_default_live_adapter(
    *,
    binance_base_url: str | None,
) -> BinanceSpotLiveMarketDataAdapter:
    if binance_base_url is not None:
        return BinanceSpotLiveMarketDataAdapter(base_url=binance_base_url)
    return BinanceSpotLiveMarketDataAdapter()


def run_live_market_preflight_probe(
    *,
    settings: Settings,
    runtime_id: str,
    market_source: Literal["binance_spot"],
    live_symbol: str,
    live_interval: str,
    live_lookback_candles: int,
    feed_stale_after_seconds: int,
    binance_base_url: str | None = None,
    live_market_poll_retry_count: int = 2,
    live_market_poll_retry_delay_seconds: float = 2.0,
    live_adapter: BinanceSpotLiveMarketDataAdapter | None = None,
    live_adapter_factory: Callable[[], BinanceSpotLiveMarketDataAdapter] | None = None,
    now_fn: Callable[[], datetime] = _utc_now,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> LiveMarketPreflightResult:
    if settings.mode is not Mode.PAPER:
        raise ValueError("Live market preflight requires settings.mode to be paper.")
    if market_source != "binance_spot":
        raise ValueError("Live market preflight only supports market_source=binance_spot.")

    observed_at = _normalize_datetime(now_fn())
    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    paths.runtime_dir.mkdir(parents=True, exist_ok=True)
    transient_status = _initial_runtime_status(
        runtime_id=runtime_id,
        execution_mode="paper",
        market_source=market_source,
        replay_path=None,
        live_symbol=live_symbol,
        live_interval=live_interval,
        live_lookback_candles=live_lookback_candles,
        feed_stale_after_seconds=feed_stale_after_seconds,
        binance_base_url=binance_base_url,
        starting_equity_usd=1.0,
        session_interval_seconds=1,
        now=observed_at,
        paths=paths,
    )

    def _make_probe_adapter() -> BinanceSpotLiveMarketDataAdapter:
        if live_adapter_factory is not None:
            return live_adapter_factory()
        if live_adapter is not None:
            return live_adapter
        return _build_default_live_adapter(binance_base_url=binance_base_url)

    initial_adapter = _make_probe_adapter()
    configured_base_url = binance_base_url or initial_adapter.base_url

    try:
        initial_poll_result = _poll_with_retry_result(
            status=transient_status,
            adapter=initial_adapter,
            now=observed_at,
            retry_count=live_market_poll_retry_count,
            retry_delay_seconds=live_market_poll_retry_delay_seconds,
            sleep_fn=sleep_fn,
        )
        initial_market_state = initial_poll_result.market_state
        if initial_market_state.feed_health.status != "healthy":
            _clear_live_market_state_artifacts(paths)
            artifact = _build_failed_preflight_artifact(
                runtime_id=runtime_id,
                market_source=market_source,
                live_symbol=live_symbol,
                live_interval=live_interval,
                configured_base_url=configured_base_url,
                retry_count=live_market_poll_retry_count,
                retry_delay_seconds=live_market_poll_retry_delay_seconds,
                attempt_count_used=initial_poll_result.attempt_count_used,
                observed_at=observed_at,
                status="stale",
                feed_health_status=initial_market_state.feed_health.status,
                feed_health_message=initial_market_state.feed_health.message,
                required_closed_candle_count=live_lookback_candles,
                candle_count=len(initial_market_state.candles),
                order_book_present=initial_market_state.order_book is not None,
                constraints_present=initial_market_state.constraints is not None,
                batch_readiness_reason="single_probe_not_healthy",
                single_probe_success=False,
            )
        else:
            stability_observed_at = observed_at + timedelta(seconds=1)
            try:
                stability_adapter = _make_probe_adapter()
                stability_poll_result = _poll_with_retry_result(
                    status=transient_status,
                    adapter=stability_adapter,
                    now=stability_observed_at,
                    retry_count=live_market_poll_retry_count,
                    retry_delay_seconds=live_market_poll_retry_delay_seconds,
                    sleep_fn=sleep_fn,
                )
                stability_market_state = stability_poll_result.market_state
                if stability_market_state.feed_health.status == "healthy":
                    _write_live_market_state(paths, stability_market_state)
                    if (
                        initial_poll_result.attempt_count_used > 1
                        or stability_poll_result.attempt_count_used > 1
                        or initial_market_state.feed_health.recovered
                        or stability_market_state.feed_health.recovered
                    ):
                        classification: Literal[
                            "batch_ready",
                            "recovered_after_retry",
                            "single_probe_ready",
                            "stale",
                            "unavailable",
                            "retries_exhausted",
                        ] = "recovered_after_retry"
                        batch_readiness_reason = "batch_ready_after_retry_recovery"
                    else:
                        classification = "batch_ready"
                        batch_readiness_reason = "batch_ready"
                    artifact = LiveMarketPreflightArtifact(
                        runtime_id=runtime_id,
                        market_source=market_source,
                        symbol=live_symbol,
                        interval=live_interval,
                        configured_base_url=configured_base_url,
                        retry_count=live_market_poll_retry_count,
                        retry_delay_seconds=live_market_poll_retry_delay_seconds,
                        attempt_count_used=initial_poll_result.attempt_count_used,
                        observed_at=observed_at,
                        status=classification,
                        success=True,
                        single_probe_success=True,
                        batch_readiness=True,
                        batch_readiness_reason=batch_readiness_reason,
                        feed_health_status=initial_market_state.feed_health.status,
                        feed_health_message=initial_market_state.feed_health.message,
                        required_closed_candle_count=live_lookback_candles,
                        candle_count=min(
                            len(initial_market_state.candles),
                            len(stability_market_state.candles),
                        ),
                        stability_window_probe_count=2,
                        stability_window_success_count=2,
                        stability_window_result="passed",
                        stability_failure_status=None,
                        stability_probe_attempt_count_used=stability_poll_result.attempt_count_used,
                        stability_feed_health_status=stability_market_state.feed_health.status,
                        stability_feed_health_message=stability_market_state.feed_health.message,
                        order_book_present=(
                            initial_market_state.order_book is not None
                            and stability_market_state.order_book is not None
                        ),
                        constraints_present=(
                            initial_market_state.constraints is not None
                            and stability_market_state.constraints is not None
                        ),
                    )
                else:
                    _clear_live_market_state_artifacts(paths)
                    stability_failure_status: Literal[
                        "stale",
                        "unavailable",
                        "retries_exhausted",
                    ] = (
                        "stale"
                        if stability_market_state.feed_health.status == "stale"
                        else "unavailable"
                    )
                    artifact = LiveMarketPreflightArtifact(
                        runtime_id=runtime_id,
                        market_source=market_source,
                        symbol=live_symbol,
                        interval=live_interval,
                        configured_base_url=configured_base_url,
                        retry_count=live_market_poll_retry_count,
                        retry_delay_seconds=live_market_poll_retry_delay_seconds,
                        attempt_count_used=initial_poll_result.attempt_count_used,
                        observed_at=observed_at,
                        status="single_probe_ready",
                        success=False,
                        single_probe_success=True,
                        batch_readiness=False,
                        batch_readiness_reason=(
                            f"stability_probe_{stability_market_state.feed_health.status}"
                        ),
                        feed_health_status=initial_market_state.feed_health.status,
                        feed_health_message=initial_market_state.feed_health.message,
                        required_closed_candle_count=live_lookback_candles,
                        candle_count=min(
                            len(initial_market_state.candles),
                            len(stability_market_state.candles),
                        ),
                        stability_window_probe_count=2,
                        stability_window_success_count=1,
                        stability_window_result="failed",
                        stability_failure_status=stability_failure_status,
                        stability_probe_attempt_count_used=stability_poll_result.attempt_count_used,
                        stability_feed_health_status=stability_market_state.feed_health.status,
                        stability_feed_health_message=stability_market_state.feed_health.message,
                        order_book_present=(
                            initial_market_state.order_book is not None
                            and stability_market_state.order_book is not None
                        ),
                        constraints_present=(
                            initial_market_state.constraints is not None
                            and stability_market_state.constraints is not None
                        ),
                    )
            except LiveMarketDataUnavailableError as exc:
                _clear_live_market_state_artifacts(paths)
                stability_exception_status: Literal["unavailable", "retries_exhausted"] = (
                    "retries_exhausted" if "retries_exhausted" in str(exc) else "unavailable"
                )
                artifact = LiveMarketPreflightArtifact(
                    runtime_id=runtime_id,
                    market_source=market_source,
                    symbol=live_symbol,
                    interval=live_interval,
                    configured_base_url=configured_base_url,
                    retry_count=live_market_poll_retry_count,
                    retry_delay_seconds=live_market_poll_retry_delay_seconds,
                    attempt_count_used=initial_poll_result.attempt_count_used,
                    observed_at=observed_at,
                    status="single_probe_ready",
                    success=False,
                    single_probe_success=True,
                    batch_readiness=False,
                    batch_readiness_reason="stability_probe_unavailable",
                    feed_health_status=initial_market_state.feed_health.status,
                    feed_health_message=initial_market_state.feed_health.message,
                    required_closed_candle_count=live_lookback_candles,
                    candle_count=len(initial_market_state.candles),
                    stability_window_probe_count=2,
                    stability_window_success_count=1,
                    stability_window_result="failed",
                    stability_failure_status=stability_exception_status,
                    stability_probe_attempt_count_used=(
                        live_market_poll_retry_count + 1
                        if stability_exception_status == "retries_exhausted"
                        else 1
                    ),
                    stability_feed_health_status="degraded",
                    stability_feed_health_message=str(exc),
                    order_book_present=initial_market_state.order_book is not None,
                    constraints_present=initial_market_state.constraints is not None,
                )
    except LiveMarketDataUnavailableError as exc:
        _clear_live_market_state_artifacts(paths)
        message = str(exc)
        classification = "retries_exhausted" if "retries_exhausted" in message else "unavailable"
        artifact = _build_failed_preflight_artifact(
            runtime_id=runtime_id,
            market_source=market_source,
            live_symbol=live_symbol,
            live_interval=live_interval,
            configured_base_url=configured_base_url,
            retry_count=live_market_poll_retry_count,
            retry_delay_seconds=live_market_poll_retry_delay_seconds,
            attempt_count_used=(
                live_market_poll_retry_count + 1 if classification == "retries_exhausted" else 1
            ),
            observed_at=observed_at,
            status=classification,
            feed_health_status="degraded",
            feed_health_message=message,
            required_closed_candle_count=live_lookback_candles,
            candle_count=0,
            order_book_present=False,
            constraints_present=False,
            batch_readiness_reason=classification,
            single_probe_success=False,
        )

    _write_json_artifact(paths.live_market_preflight_path, artifact)
    return LiveMarketPreflightResult(
        runtime_id=runtime_id,
        artifact_path=paths.live_market_preflight_path,
        artifact=artifact,
    )


def _session_summary_with_live_state(
    *,
    session_summary: ForwardPaperSessionSummary,
    session_market_input_path: Path,
    session_market_state_path: Path,
    state: LiveMarketState,
    paths: ForwardPaperRuntimePaths,
) -> ForwardPaperSessionSummary:
    return session_summary.model_copy(
        update={
            "market_input_path": session_market_input_path,
            "market_state_path": session_market_state_path,
            "venue_constraints_path": paths.venue_constraints_path,
            "feed_health": state.feed_health,
        }
    )


def _session_summary_with_execution_artifacts(
    *,
    session_summary: ForwardPaperSessionSummary,
    request_path: Path,
    result_path: Path,
    status_path: Path,
    request_artifact: ExecutionRequestArtifact,
    status_artifact: ExecutionStatusArtifact,
) -> ForwardPaperSessionSummary:
    artifact_paths_exist = dict(session_summary.artifact_paths_exist)
    artifact_paths_exist.update(
        {
            "execution_request_path": request_path.exists(),
            "execution_result_path": result_path.exists(),
            "execution_status_path": status_path.exists(),
        }
    )
    return session_summary.model_copy(
        update={
            "execution_request_path": request_path,
            "execution_result_path": result_path,
            "execution_status_path": status_path,
            "execution_request_count": request_artifact.request_count,
            "execution_terminal_count": status_artifact.terminal_status_count,
            "artifact_paths_exist": artifact_paths_exist,
            "all_artifact_paths_exist": all(artifact_paths_exist.values()),
        }
    )


def _session_summary_with_request_artifact(
    *,
    session_summary: ForwardPaperSessionSummary,
    request_path: Path,
    request_artifact: ExecutionRequestArtifact,
) -> ForwardPaperSessionSummary:
    artifact_paths_exist = dict(session_summary.artifact_paths_exist)
    artifact_paths_exist["execution_request_path"] = request_path.exists()
    return session_summary.model_copy(
        update={
            "execution_request_path": request_path,
            "execution_request_count": request_artifact.request_count,
            "artifact_paths_exist": artifact_paths_exist,
            "all_artifact_paths_exist": all(artifact_paths_exist.values()),
        }
    )


def _session_summary_with_live_transmission_artifacts(
    *,
    session_summary: ForwardPaperSessionSummary,
    request_path: Path,
    result_path: Path,
    state_path: Path,
) -> ForwardPaperSessionSummary:
    artifact_paths_exist = dict(session_summary.artifact_paths_exist)
    artifact_paths_exist.update(
        {
            "live_transmission_request_path": request_path.exists(),
            "live_transmission_result_path": result_path.exists(),
            "live_transmission_state_path": state_path.exists(),
        }
    )
    return session_summary.model_copy(
        update={
            "live_transmission_request_path": request_path,
            "live_transmission_result_path": result_path,
            "live_transmission_state_path": state_path,
            "artifact_paths_exist": artifact_paths_exist,
            "all_artifact_paths_exist": all(artifact_paths_exist.values()),
        }
    )


def _session_summary_with_control_decision(
    *,
    session_summary: ForwardPaperSessionSummary,
    control_decision_path: Path,
    control_decision: LiveControlDecision,
) -> ForwardPaperSessionSummary:
    artifact_paths_exist = dict(session_summary.artifact_paths_exist)
    artifact_paths_exist["control_decision_path"] = control_decision_path.exists()
    return session_summary.model_copy(
        update={
            "control_decision_path": control_decision_path,
            "control_action": control_decision.action,
            "control_reason_codes": control_decision.reason_codes,
            "artifact_paths_exist": artifact_paths_exist,
            "all_artifact_paths_exist": all(artifact_paths_exist.values()),
        }
    )


def _persist_control_status(
    *,
    status: ForwardPaperRuntimeStatus,
    controls: LiveControlConfig,
    readiness: LiveReadinessStatus,
    manual_controls: ManualControlState,
    account_state: ForwardPaperRuntimeAccountState,
    latest_decision_path: Path | None,
    latest_decision: LiveControlDecision,
    updated_at: datetime,
) -> ForwardPaperRuntimeStatus:
    last_session = _last_completed_session(status)
    control_status = build_live_control_status_artifact(
        runtime_id=status.runtime_id,
        execution_mode=status.execution_mode,
        market_source=status.market_source,
        controls=controls,
        manual_controls=manual_controls,
        readiness_status=readiness.status,
        limited_live_gate_status=readiness.limited_live_gate_status,
        account_state=account_state,
        last_completed_session=last_session,
        latest_decision_path=latest_decision_path,
        latest_decision=latest_decision,
        updated_at=updated_at,
    )
    _write_json_artifact(status.live_control_status_path, control_status)
    updated_status = status.model_copy(
        update={
            "live_control_status_path": status.live_control_status_path,
            "live_control_config_path": status.live_control_config_path,
            "readiness_status_path": status.readiness_status_path,
            "manual_control_state_path": status.manual_control_state_path,
            "control_status": latest_decision.action,
            "control_block_reasons": latest_decision.reason_codes,
            "updated_at": updated_at,
        }
    )
    _refresh_limited_live_transmission_boundary(
        status=updated_status,
        readiness=readiness,
        manual_controls=manual_controls,
        latest_decision=latest_decision,
        updated_at=updated_at,
    )
    _persist_runtime_status(updated_status)
    return updated_status


def _refresh_limited_live_transmission_boundary(
    *,
    status: ForwardPaperRuntimeStatus,
    readiness: LiveReadinessStatus,
    manual_controls: ManualControlState,
    latest_decision: LiveControlDecision,
    updated_at: datetime,
) -> None:
    if (
        status.live_authority_state_path is None
        or status.live_launch_window_path is None
        or status.live_approval_state_path is None
        or status.live_transmission_decision_path is None
        or status.live_transmission_result_path is None
    ):
        raise ValueError("Limited-live foundation artifacts must exist before boundary refresh.")

    decision = build_limited_live_transmission_decision_artifact(
        runtime_id=status.runtime_id,
        authority_state_path=status.live_authority_state_path,
        launch_window_path=status.live_launch_window_path,
        approval_state_path=status.live_approval_state_path,
        readiness_status=readiness.status,
        limited_live_gate_status=readiness.limited_live_gate_status,
        manual_controls=manual_controls,
        reconciliation_status=status.reconciliation_status,
        latest_decision=latest_decision,
        generated_at=updated_at,
    )
    _write_json_artifact(status.live_transmission_decision_path, decision)
    _write_json_artifact(
        status.live_transmission_result_path,
        _build_live_transmission_result_artifact(
            runtime_id=status.runtime_id,
            generated_at=updated_at,
            decision=decision,
            decision_path=status.live_transmission_decision_path,
        ),
    )


def _ensure_live_control_status_artifact(
    *,
    status: ForwardPaperRuntimeStatus,
    runtime_id: str,
    execution_mode: Literal["paper", "shadow", "sandbox"],
    controls: LiveControlConfig,
    readiness: LiveReadinessStatus,
    manual_controls: ManualControlState,
    account_state: ForwardPaperRuntimeAccountState,
    checked_at: datetime,
) -> ForwardPaperRuntimeStatus:
    if status.live_control_status_path.exists():
        return status

    initial_decision = evaluate_preflight_controls(
        runtime_id=runtime_id,
        session_id="runtime-init",
        execution_mode=execution_mode,
        requested_symbols=[],
        account_state=account_state,
        controls=controls,
        readiness_status=readiness.status,
        manual_controls=manual_controls,
        checked_at=checked_at,
        last_completed_session=_last_completed_session(status),
    )
    return _persist_control_status(
        status=status,
        controls=controls,
        readiness=readiness,
        manual_controls=manual_controls,
        account_state=account_state,
        latest_decision_path=None,
        latest_decision=initial_decision,
        updated_at=checked_at,
    )


def _materialize_live_gate_artifacts(
    *,
    status: ForwardPaperRuntimeStatus,
    paths: ForwardPaperRuntimePaths,
    generated_at: datetime,
) -> None:
    sessions = load_runtime_session_summaries(status.sessions_dir)
    soak_evaluation = build_forward_paper_soak_evaluation(
        runtime_id=status.runtime_id,
        sessions=sessions,
        generated_at=generated_at,
    )
    shadow_evaluation = build_forward_paper_shadow_evaluation(
        runtime_id=status.runtime_id,
        sessions=sessions,
        generated_at=generated_at,
    )
    shadow_canary = build_forward_paper_shadow_canary_evaluation(
        runtime_id=status.runtime_id,
        execution_mode=status.execution_mode,
        market_source=status.market_source,
        sessions=sessions,
        generated_at=generated_at,
    )
    preflight_artifact = _load_live_market_preflight_artifact(paths.live_market_preflight_path)
    control_status = _load_live_control_status(status.live_control_status_path)
    readiness = _load_readiness_status(status.readiness_status_path)
    manual_controls = _load_manual_control_state(status.manual_control_state_path)
    reconciliation_report = load_reconciliation_report(status.reconciliation_report_path)
    gate_config = default_live_gate_config(runtime_id=status.runtime_id, updated_at=generated_at)
    threshold_summary = build_live_gate_threshold_summary(
        runtime_id=status.runtime_id,
        generated_at=generated_at,
        config=gate_config,
        soak=soak_evaluation,
        shadow=shadow_evaluation,
        reconciliation=reconciliation_report,
        control_status=control_status,
        readiness=readiness,
        manual_controls=manual_controls,
    )
    decision = build_live_gate_decision(
        runtime_id=status.runtime_id,
        generated_at=generated_at,
        threshold_summary=threshold_summary,
        soak_evaluation_path=paths.soak_evaluation_path,
        shadow_evaluation_path=paths.shadow_evaluation_path,
        threshold_summary_path=paths.live_gate_threshold_summary_path,
    )
    report = build_live_gate_report(
        decision=decision,
        threshold_summary=threshold_summary,
        soak=soak_evaluation,
        shadow=shadow_evaluation,
    )
    launch_verdict = build_live_launch_verdict(
        runtime_id=status.runtime_id,
        generated_at=generated_at,
        preflight_artifact=preflight_artifact,
        preflight_path=paths.live_market_preflight_path,
        shadow_canary=shadow_canary,
        shadow_canary_path=paths.shadow_canary_evaluation_path,
        threshold_summary=threshold_summary,
        threshold_summary_path=paths.live_gate_threshold_summary_path,
        gate_decision=decision,
        gate_decision_path=paths.live_gate_decision_path,
        readiness_status=readiness,
        readiness_status_path=paths.readiness_status_path,
        control_status=control_status,
        control_status_path=paths.live_control_status_path,
    )
    _write_json_artifact(paths.shadow_canary_evaluation_path, shadow_canary)
    _write_json_artifact(paths.soak_evaluation_path, soak_evaluation)
    _write_json_artifact(paths.shadow_evaluation_path, shadow_evaluation)
    _write_json_artifact(paths.live_gate_threshold_summary_path, threshold_summary)
    _write_json_artifact(paths.live_gate_decision_path, decision)
    _write_json_artifact(paths.live_launch_verdict_path, launch_verdict)
    paths.live_gate_report_path.write_text(report, encoding="utf-8")


def _materialize_execution_mode_artifacts(
    *,
    execution_mode: Literal["paper", "shadow", "sandbox"],
    session_summary: ForwardPaperSessionSummary,
    sessions_dir: Path,
    sandbox_execution_adapter: SandboxExecutionAdapter | None,
    observed_at: datetime,
    request_artifact: ExecutionRequestArtifact | None = None,
) -> ForwardPaperSessionSummary:
    if execution_mode == "paper":
        return session_summary
    if (
        session_summary.journal_path is None
        or session_summary.run_id is None
        or session_summary.market_state_path is None
        or session_summary.venue_constraints_path is None
    ):
        raise ValueError(
            "Execution adapter artifacts require journal, run, market state, and constraints."
        )

    request_path = _session_execution_request_path(sessions_dir, session_summary.session_id)
    result_path = _session_execution_result_path(sessions_dir, session_summary.session_id)
    status_path = _session_execution_status_path(sessions_dir, session_summary.session_id)

    if execution_mode == "shadow":
        request_artifact, result_artifact, status_artifact = build_shadow_execution_artifacts(
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            journal_path=session_summary.journal_path,
            market_state_path=session_summary.market_state_path,
            venue_constraints_path=session_summary.venue_constraints_path,
            observed_at=observed_at,
            request_artifact=request_artifact,
        )
    else:
        if sandbox_execution_adapter is None:
            raise ValueError("Sandbox execution mode requires an explicit sandbox adapter.")
        request_artifact, result_artifact, status_artifact = execute_sandbox_requests(
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            journal_path=session_summary.journal_path,
            market_state_path=session_summary.market_state_path,
            venue_constraints_path=session_summary.venue_constraints_path,
            existing_status_path=status_path,
            adapter=sandbox_execution_adapter,
            observed_at=observed_at,
            request_artifact=request_artifact,
        )

    _write_execution_artifact(request_path, request_artifact)
    _write_execution_artifact(result_path, result_artifact)
    _write_execution_artifact(status_path, status_artifact)
    return _session_summary_with_execution_artifacts(
        session_summary=session_summary,
        request_path=request_path,
        result_path=result_path,
        status_path=status_path,
        request_artifact=request_artifact,
        status_artifact=status_artifact,
    )


def _materialize_limited_live_transmission_artifacts(
    *,
    runtime_id: str,
    session_summary: ForwardPaperSessionSummary,
    sessions_dir: Path,
    observed_at: datetime,
    decision: LiveTransmissionDecisionArtifact,
    request_artifact: ExecutionRequestArtifact | None,
    expected_symbol: str | None,
    live_execution_adapter: LiveExecutionAdapter | None,
) -> ForwardPaperSessionSummary:
    if session_summary.run_id is None:
        raise ValueError("Limited-live transmission artifacts require session run_id.")
    request_path = _session_live_transmission_request_path(sessions_dir, session_summary.session_id)
    result_path = _session_live_transmission_result_path(sessions_dir, session_summary.session_id)
    state_path = _session_live_transmission_state_path(sessions_dir, session_summary.session_id)

    request_model = _build_live_transmission_request_artifact(
        runtime_id=runtime_id,
        session_id=session_summary.session_id,
        run_id=session_summary.run_id,
        generated_at=observed_at,
        request_artifact=request_artifact,
    )
    # Write in fixed order for deterministic operator/audit flow.
    _write_json_artifact(request_path, request_model)
    reason_codes = set(decision.reason_codes)
    result_model: LiveTransmissionResultArtifact
    state_model: LiveTransmissionStateArtifact

    if request_model.request_count != 1:
        reason_codes.add("bounded_live_requires_single_request")
        result_model = LiveTransmissionResultArtifact(
            runtime_id=runtime_id,
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            generated_at=observed_at,
            submission_status="not_submitted",
            summary=(
                "Live transmission blocked because bounded live mode requires exactly one "
                "normalized request."
            ),
            reason_codes=sorted(reason_codes),
        )
        state_model = LiveTransmissionStateArtifact(
            runtime_id=runtime_id,
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            generated_at=observed_at,
            state="not_submitted_terminal_blocked",
            terminal=True,
            submission_present=False,
            summary="No live submission attempted because request cardinality was not one.",
            reason_codes=sorted(reason_codes),
        )
        _write_json_artifact(result_path, result_model)
        _write_json_artifact(state_path, state_model)
        return _session_summary_with_live_transmission_artifacts(
            session_summary=session_summary,
            request_path=request_path,
            result_path=result_path,
            state_path=state_path,
        )

    live_request = request_model.requests[0]
    if expected_symbol is None:
        reason_codes.add("bounded_live_symbol_not_configured")
    elif live_request.symbol != expected_symbol:
        reason_codes.add("bounded_live_symbol_mismatch")
    if live_execution_adapter is None:
        reason_codes.add("live_execution_adapter_missing")

    if reason_codes:
        result_model = LiveTransmissionResultArtifact(
            runtime_id=runtime_id,
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            generated_at=observed_at,
            submission_status="not_submitted",
            summary=(
                "Live transmission blocked because bounded prerequisites were ambiguous or "
                "incomplete."
            ),
            reason_codes=sorted(reason_codes),
        )
        state_model = LiveTransmissionStateArtifact(
            runtime_id=runtime_id,
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            generated_at=observed_at,
            state="not_submitted_terminal_blocked",
            terminal=True,
            submission_present=False,
            summary="No live submission attempted because bounded prerequisites were not met.",
            reason_codes=sorted(reason_codes),
        )
        _write_json_artifact(result_path, result_model)
        _write_json_artifact(state_path, state_model)
        return _session_summary_with_live_transmission_artifacts(
            session_summary=session_summary,
            request_path=request_path,
            result_path=result_path,
            state_path=state_path,
        )

    adapter = live_execution_adapter
    if adapter is None:
        raise ValueError("Live execution adapter must be configured for bounded transmission.")

    try:
        ack: LiveTransmissionAck = adapter.submit_order(live_request)
        if ack.status == "accepted":
            submission_status: Literal["submitted", "rejected"] = "submitted"
            summary = "Live adapter accepted the bounded live request."
        else:
            submission_status = "rejected"
            reason_codes.add("live_submission_not_accepted")
            summary = "Live adapter did not accept the bounded live request."
        result_model = LiveTransmissionResultArtifact(
            runtime_id=runtime_id,
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            generated_at=observed_at,
            adapter_call_attempted=True,
            submission_status=submission_status,
            ack=ack,
            summary=summary,
            reason_codes=sorted(reason_codes),
        )

        if ack.status != "accepted":
            state_model = LiveTransmissionStateArtifact(
                runtime_id=runtime_id,
                session_id=session_summary.session_id,
                run_id=session_summary.run_id,
                generated_at=observed_at,
                state="rejected",
                terminal=True,
                submission_present=False,
                summary="Live request was not accepted; no live order state fetch attempted.",
                reason_codes=sorted(reason_codes),
            )
        else:
            order_state: LiveTransmissionOrderState = adapter.fetch_order_state(
                client_order_id=live_request.client_order_id,
                request=live_request,
            )
            if not order_state.terminal:
                reason_codes.add("live_order_non_terminal_canceled")
                order_state = adapter.cancel_order(
                    client_order_id=live_request.client_order_id,
                    request=live_request,
                )
            state_model = LiveTransmissionStateArtifact(
                runtime_id=runtime_id,
                session_id=session_summary.session_id,
                run_id=session_summary.run_id,
                generated_at=observed_at,
                state=order_state.state,
                terminal=order_state.terminal,
                submission_present=True,
                order_state=order_state,
                summary="Live order state captured from bounded adapter lifecycle.",
                reason_codes=sorted(reason_codes),
            )
    except Exception as exc:
        reason_codes.update({"live_adapter_error", "live_transmission_failed_closed"})
        result_model = LiveTransmissionResultArtifact(
            runtime_id=runtime_id,
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            generated_at=observed_at,
            adapter_call_attempted=True,
            submission_status="error",
            summary=f"Live adapter call failed closed: {exc}",
            reason_codes=sorted(reason_codes),
        )
        state_model = LiveTransmissionStateArtifact(
            runtime_id=runtime_id,
            session_id=session_summary.session_id,
            run_id=session_summary.run_id,
            generated_at=observed_at,
            state="error_terminal_blocked",
            terminal=True,
            submission_present=False,
            summary="Live transmission failed closed after adapter error.",
            reason_codes=sorted(reason_codes),
        )

    _write_json_artifact(result_path, result_model)
    _write_json_artifact(state_path, state_model)
    return _session_summary_with_live_transmission_artifacts(
        session_summary=session_summary,
        request_path=request_path,
        result_path=result_path,
        state_path=state_path,
    )


def run_forward_paper_runtime(
    replay_path: str | Path | None,
    *,
    settings: Settings,
    runtime_id: str,
    session_interval_seconds: int,
    equity_usd: float = 100_000.0,
    execution_mode: Literal["paper", "shadow", "sandbox"] = "paper",
    max_sessions: int | None = None,
    tick_times: Iterable[datetime] | None = None,
    recover_interrupted: bool = True,
    now_fn: Callable[[], datetime] = _utc_now,
    sleep_fn: Callable[[float], None] = time.sleep,
    market_source: Literal["replay", "binance_spot"] = "replay",
    live_symbol: str | None = None,
    live_interval: str | None = None,
    live_lookback_candles: int | None = None,
    feed_stale_after_seconds: int | None = None,
    live_adapter: BinanceSpotLiveMarketDataAdapter | None = None,
    binance_base_url: str | None = None,
    live_market_poll_retry_count: int = 2,
    live_market_poll_retry_delay_seconds: float = 2.0,
    sandbox_fixture_rehearsal: bool = False,
    sandbox_execution_adapter: SandboxExecutionAdapter | None = None,
    live_execution_adapter: LiveExecutionAdapter | None = None,
    live_launch_window_starts_at: datetime | None = None,
    live_launch_window_ends_at: datetime | None = None,
    limited_live_authority_enabled: bool = False,
    live_control_config: LiveControlConfig | None = None,
    readiness_status: LiveReadinessStatus | None = None,
    manual_control_state: ManualControlState | None = None,
) -> ForwardPaperRuntimeResult:
    replay_fixture_path = Path(replay_path) if replay_path is not None else None
    scheduled_ticks = (
        [_normalize_datetime(tick) for tick in tick_times] if tick_times is not None else None
    )
    initial_now = scheduled_ticks[0] if scheduled_ticks else _normalize_datetime(now_fn())
    live_launch_window_starts_at = (
        _normalize_datetime(live_launch_window_starts_at)
        if live_launch_window_starts_at is not None
        else None
    )
    live_launch_window_ends_at = (
        _normalize_datetime(live_launch_window_ends_at)
        if live_launch_window_ends_at is not None
        else None
    )
    status, account_state, recovered_session_id, recovery_note = _ensure_runtime_status(
        settings=settings,
        execution_mode=execution_mode,
        market_source=market_source,
        sandbox_fixture_rehearsal=sandbox_fixture_rehearsal,
        replay_path=replay_fixture_path,
        live_symbol=live_symbol,
        live_interval=live_interval,
        live_lookback_candles=live_lookback_candles,
        feed_stale_after_seconds=feed_stale_after_seconds,
        binance_base_url=binance_base_url,
        runtime_id=runtime_id,
        starting_equity_usd=equity_usd,
        session_interval_seconds=session_interval_seconds,
        now=initial_now,
        recover_interrupted=recover_interrupted,
    )
    paths = build_forward_paper_runtime_paths(settings.paths.runs_dir, runtime_id)
    _ensure_limited_live_foundation_artifacts(
        runtime_id=runtime_id,
        paths=paths,
        generated_at=initial_now,
        limited_live_authority_enabled=limited_live_authority_enabled,
        live_launch_window_starts_at=live_launch_window_starts_at,
        live_launch_window_ends_at=live_launch_window_ends_at,
    )
    controls, readiness, manual_controls = _resolve_control_surfaces(
        runtime_id=runtime_id,
        settings=settings,
        paths=paths,
        updated_at=initial_now,
        live_control_config=live_control_config,
        readiness_status=readiness_status,
        manual_control_state=manual_control_state,
    )
    status = _ensure_live_control_status_artifact(
        status=status,
        runtime_id=runtime_id,
        execution_mode=execution_mode,
        controls=controls,
        readiness=readiness,
        manual_controls=manual_controls,
        account_state=account_state,
        checked_at=initial_now,
    )
    scheduled_times = _iter_scheduled_times(
        tick_times=scheduled_ticks,
        max_sessions=max_sessions,
        initial_next_scheduled_at=status.next_scheduled_at,
        now_fn=now_fn,
        sleep_fn=sleep_fn,
        interval_seconds=session_interval_seconds,
    )

    completed_sessions: list[ForwardPaperSessionSummary] = []
    if live_adapter is not None and market_source == "binance_spot":
        resolved_live_adapter: BinanceSpotLiveMarketDataAdapter | None = live_adapter
    elif market_source == "binance_spot":
        resolved_live_adapter = (
            BinanceSpotLiveMarketDataAdapter(base_url=binance_base_url)
            if binance_base_url is not None
            else BinanceSpotLiveMarketDataAdapter()
        )
    else:
        resolved_live_adapter = None

    for scheduled_at in scheduled_times:
        status, running_session, session_path = _start_session(
            status=status,
            scheduled_at=scheduled_at,
        )
        run_id = f"{runtime_id}-{running_session.session_id}"
        control_decision_path = _session_control_decision_path(
            status.sessions_dir,
            running_session.session_id,
        )
        try:
            if market_source == "replay":
                if replay_fixture_path is None:
                    raise ValueError("Replay runtime requires replay fixture path")
                preflight_decision = evaluate_preflight_controls(
                    runtime_id=runtime_id,
                    session_id=running_session.session_id,
                    execution_mode=execution_mode,
                    requested_symbols=_requested_symbols_from_replay(replay_fixture_path),
                    account_state=account_state,
                    controls=controls,
                    readiness_status=readiness.status,
                    manual_controls=manual_controls,
                    checked_at=scheduled_at,
                    last_completed_session=_last_completed_session(status),
                )
                _write_json_artifact(control_decision_path, preflight_decision)
                running_session = _session_summary_with_control_decision(
                    session_summary=running_session,
                    control_decision_path=control_decision_path,
                    control_decision=preflight_decision,
                )
                status = _persist_control_status(
                    status=status,
                    controls=controls,
                    readiness=readiness,
                    manual_controls=manual_controls,
                    account_state=account_state,
                    latest_decision_path=control_decision_path,
                    latest_decision=preflight_decision,
                    updated_at=scheduled_at,
                )
                if preflight_decision.action != "go":
                    completed_at = _normalize_datetime(now_fn())
                    blocked_session = _blocked_session_summary(
                        session_summary=running_session,
                        completed_at=completed_at,
                        control_decision=preflight_decision,
                    )
                    _write_session_summary(blocked_session, session_path)
                    append_forward_paper_history(
                        status.history_path,
                        ForwardPaperHistoryEvent(
                            event_type="session.completed",
                            runtime_id=runtime_id,
                            session_id=blocked_session.session_id,
                            session_number=blocked_session.session_number,
                            occurred_at=completed_at,
                            status="completed",
                            message=blocked_session.session_outcome,
                        ),
                    )
                    status = _complete_status(
                        status=status,
                        session_summary=blocked_session,
                        completed_at=completed_at,
                    )
                    status, account_state, _, _ = reconcile_forward_paper_runtime(
                        status=status,
                        paths=paths,
                        reconciled_at=completed_at,
                        require_local_match=False,
                        recovered_session_id=recovered_session_id,
                        recovery_note=recovery_note,
                    )
                    recovered_session_id = None
                    recovery_note = None
                    _persist_runtime_status(status)
                    completed_sessions.append(blocked_session)
                    continue
                result = run_paper_replay(
                    replay_fixture_path,
                    settings=settings,
                    run_id=run_id,
                    equity_usd=account_state.ending_equity_usd,
                    starting_portfolio=account_state.to_portfolio_state(),
                )
                replay_session = running_session
                if sandbox_fixture_rehearsal and execution_mode == "sandbox":
                    fixture_market_state = _build_replay_fixture_market_state(
                        replay_fixture_path,
                        stale_after_seconds=feed_stale_after_seconds or 120,
                    )
                    _write_live_market_state(paths, fixture_market_state)
                    session_market_input_path = _session_market_input_path(
                        status.sessions_dir,
                        running_session.session_id,
                    )
                    session_market_state_path = _session_market_state_path(
                        status.sessions_dir,
                        running_session.session_id,
                    )
                    _write_live_market_input(session_market_input_path, fixture_market_state)
                    session_market_state_path.write_text(
                        json.dumps(
                            fixture_market_state.model_dump(mode="json"),
                            indent=2,
                            sort_keys=True,
                        ),
                        encoding="utf-8",
                    )
                    replay_session = _session_summary_with_live_state(
                        session_summary=running_session,
                        session_market_input_path=session_market_input_path,
                        session_market_state_path=session_market_state_path,
                        state=fixture_market_state,
                        paths=paths,
                    )
                    status = status.model_copy(
                        update={
                            "feed_health": fixture_market_state.feed_health,
                            "venue_constraints_ready": True,
                            "live_market_status_path": paths.live_market_status_path,
                            "venue_constraints_path": paths.venue_constraints_path,
                            "updated_at": scheduled_at,
                        }
                    )
                    _persist_runtime_status(status)
                completed_at = _normalize_datetime(now_fn())
                completed_session = _completed_session_summary(
                    session_summary=replay_session,
                    result=result,
                    completed_at=completed_at,
                )
            else:
                if resolved_live_adapter is None:
                    raise ValueError("Live market runtime requires a live market adapter")
                market_state = _poll_with_retry(
                    status=status,
                    adapter=resolved_live_adapter,
                    now=scheduled_at,
                    retry_count=live_market_poll_retry_count,
                    retry_delay_seconds=live_market_poll_retry_delay_seconds,
                    sleep_fn=sleep_fn,
                )
                _write_live_market_state(paths, market_state)
                session_market_input_path = _session_market_input_path(
                    status.sessions_dir,
                    running_session.session_id,
                )
                session_market_state_path = _session_market_state_path(
                    status.sessions_dir,
                    running_session.session_id,
                )
                _write_live_market_input(session_market_input_path, market_state)
                session_market_state_path.write_text(
                    json.dumps(market_state.model_dump(mode="json"), indent=2, sort_keys=True),
                    encoding="utf-8",
                )
                live_session = _session_summary_with_live_state(
                    session_summary=running_session,
                    session_market_input_path=session_market_input_path,
                    session_market_state_path=session_market_state_path,
                    state=market_state,
                    paths=paths,
                )
                status = status.model_copy(
                    update={
                        "feed_health": market_state.feed_health,
                        "venue_constraints_ready": True,
                        "live_market_status_path": paths.live_market_status_path,
                        "venue_constraints_path": paths.venue_constraints_path,
                        "updated_at": scheduled_at,
                    }
                )
                _persist_runtime_status(status)

                preflight_decision = evaluate_preflight_controls(
                    runtime_id=runtime_id,
                    session_id=live_session.session_id,
                    execution_mode=execution_mode,
                    requested_symbols=[market_state.symbol],
                    account_state=account_state,
                    controls=controls,
                    readiness_status=readiness.status,
                    manual_controls=manual_controls,
                    checked_at=scheduled_at,
                    last_completed_session=_last_completed_session(status),
                )
                _write_json_artifact(control_decision_path, preflight_decision)
                live_session = _session_summary_with_control_decision(
                    session_summary=live_session,
                    control_decision_path=control_decision_path,
                    control_decision=preflight_decision,
                )
                status = _persist_control_status(
                    status=status,
                    controls=controls,
                    readiness=readiness,
                    manual_controls=manual_controls,
                    account_state=account_state,
                    latest_decision_path=control_decision_path,
                    latest_decision=preflight_decision,
                    updated_at=scheduled_at,
                )

                if preflight_decision.action != "go":
                    completed_at = _normalize_datetime(now_fn())
                    completed_session = _blocked_session_summary(
                        session_summary=live_session,
                        completed_at=completed_at,
                        control_decision=preflight_decision,
                    )
                    _write_session_summary(completed_session, session_path)
                    append_forward_paper_history(
                        status.history_path,
                        ForwardPaperHistoryEvent(
                            event_type="session.completed",
                            runtime_id=runtime_id,
                            session_id=completed_session.session_id,
                            session_number=completed_session.session_number,
                            occurred_at=completed_at,
                            status="completed",
                            message=completed_session.session_outcome,
                        ),
                    )
                    status = _complete_status(
                        status=status,
                        session_summary=completed_session,
                        completed_at=completed_at,
                    )
                    status, account_state, _, _ = reconcile_forward_paper_runtime(
                        status=status,
                        paths=paths,
                        reconciled_at=completed_at,
                        require_local_match=False,
                        recovered_session_id=recovered_session_id,
                        recovery_note=recovery_note,
                    )
                    recovered_session_id = None
                    recovery_note = None
                    _persist_runtime_status(status)
                    completed_sessions.append(completed_session)
                    continue

                if market_state.feed_health.status == "healthy":
                    result = run_paper_replay(
                        session_market_input_path,
                        settings=settings,
                        run_id=run_id,
                        equity_usd=account_state.ending_equity_usd,
                        starting_portfolio=account_state.to_portfolio_state(),
                    )
                    completed_at = _normalize_datetime(now_fn())
                    completed_session = _completed_session_summary(
                        session_summary=live_session,
                        result=result,
                        completed_at=completed_at,
                    )
                else:
                    completed_at = _normalize_datetime(now_fn())
                    outcome = (
                        "skipped_stale_feed"
                        if market_state.feed_health.status == "stale"
                        else "skipped_degraded_feed"
                    )
                    completed_session = _skipped_session_summary(
                        session_summary=live_session,
                        completed_at=completed_at,
                        outcome=outcome,
                        feed_health=market_state.feed_health,
                    )

            if completed_session.session_outcome == "executed":
                request_artifact = None
                if execution_mode != "paper":
                    if (
                        completed_session.journal_path is None
                        or completed_session.market_state_path is None
                        or completed_session.venue_constraints_path is None
                    ):
                        raise ValueError(
                            "Non-paper execution controls require journal, market state, "
                            "and constraints."
                        )
                    request_artifact = build_execution_request_artifact(
                        session_id=completed_session.session_id,
                        run_id=completed_session.run_id or run_id,
                        journal_path=completed_session.journal_path,
                        market_state_path=completed_session.market_state_path,
                        venue_constraints_path=completed_session.venue_constraints_path,
                        execution_mode="shadow" if execution_mode == "shadow" else "sandbox",
                    )
                    request_path = _session_execution_request_path(
                        status.sessions_dir,
                        completed_session.session_id,
                    )
                    _write_execution_artifact(request_path, request_artifact)
                    completed_session = _session_summary_with_request_artifact(
                        session_summary=completed_session,
                        request_path=request_path,
                        request_artifact=request_artifact,
                    )

                post_run_decision = evaluate_post_run_controls(
                    runtime_id=runtime_id,
                    session_id=completed_session.session_id,
                    execution_mode=execution_mode,
                    request_artifact=request_artifact,
                    session_pnl=completed_session.pnl,
                    account_state=account_state,
                    controls=controls,
                    manual_controls=manual_controls,
                    checked_at=completed_session.completed_at or scheduled_at,
                )
                _write_json_artifact(control_decision_path, post_run_decision)
                completed_session = _session_summary_with_control_decision(
                    session_summary=completed_session,
                    control_decision_path=control_decision_path,
                    control_decision=post_run_decision,
                )
                status = _persist_control_status(
                    status=status,
                    controls=controls,
                    readiness=readiness,
                    manual_controls=manual_controls,
                    account_state=account_state,
                    latest_decision_path=control_decision_path,
                    latest_decision=post_run_decision,
                    updated_at=completed_session.completed_at or scheduled_at,
                )
                if status.live_transmission_decision_path is None:
                    raise ValueError(
                        "Limited-live transmission decision path must exist before artifact "
                        "materialization."
                    )
                transmission_decision = _load_live_transmission_decision(
                    status.live_transmission_decision_path
                )
                if (
                    status.market_source == "binance_spot"
                    and transmission_decision.transmission_authorized
                ):
                    completed_session = _materialize_limited_live_transmission_artifacts(
                        runtime_id=runtime_id,
                        session_summary=completed_session,
                        sessions_dir=status.sessions_dir,
                        observed_at=completed_session.completed_at or scheduled_at,
                        decision=transmission_decision,
                        request_artifact=request_artifact,
                        expected_symbol=status.live_symbol,
                        live_execution_adapter=live_execution_adapter,
                    )

                if execution_mode != "paper" and post_run_decision.action == "go":
                    completed_session = _materialize_execution_mode_artifacts(
                        execution_mode=execution_mode,
                        session_summary=completed_session,
                        sessions_dir=status.sessions_dir,
                        sandbox_execution_adapter=sandbox_execution_adapter,
                        observed_at=completed_session.completed_at or scheduled_at,
                        request_artifact=request_artifact,
                    )

            _write_session_summary(completed_session, session_path)
            append_forward_paper_history(
                status.history_path,
                ForwardPaperHistoryEvent(
                    event_type="session.completed",
                    runtime_id=runtime_id,
                    session_id=completed_session.session_id,
                    session_number=completed_session.session_number,
                    occurred_at=completed_session.completed_at or scheduled_at,
                    status="completed",
                    run_id=completed_session.run_id,
                    message=completed_session.session_outcome,
                ),
            )
            status = _complete_status(
                status=status,
                session_summary=completed_session,
                completed_at=completed_session.completed_at or scheduled_at,
            )
            status, account_state, _, _ = reconcile_forward_paper_runtime(
                status=status,
                paths=paths,
                reconciled_at=completed_session.completed_at or scheduled_at,
                require_local_match=False,
                recovered_session_id=recovered_session_id,
                recovery_note=recovery_note,
            )
            recovered_session_id = None
            recovery_note = None
            _persist_runtime_status(status)
            if status.mismatch_detected:
                raise RuntimeAccountMismatchError(
                    f"Forward paper runtime account state mismatch detected: {runtime_id}"
                )
            completed_sessions.append(completed_session)
        except LiveMarketDataUnavailableError as exc:
            completed_at = _normalize_datetime(now_fn())
            exc_msg = str(exc)
            configured_base_url = status.binance_base_url or "https://api.binance.com"
            if "451" in exc_msg:
                feed_message = (
                    f"{exc_msg} | venue_access: feed unavailable — HTTP 451 indicates a "
                    f"legal/geo/IP restriction at the configured endpoint "
                    f"({configured_base_url}); verify network path or set --binance-base-url"
                )
            else:
                feed_message = (
                    f"{exc_msg} | venue_access: feed unavailable on first call to "
                    f"{configured_base_url}; check network access or use --binance-base-url "
                    f"to override the endpoint"
                )
            unavailable_health = LiveFeedHealth(
                status="degraded",
                observed_at=completed_at,
                last_success_at=status.feed_health.last_success_at if status.feed_health else None,
                last_candle_close_time=(
                    status.feed_health.last_candle_close_time if status.feed_health else None
                ),
                consecutive_failure_count=(
                    (status.feed_health.consecutive_failure_count if status.feed_health else 0) + 1
                ),
                stale_after_seconds=status.feed_stale_after_seconds or 60,
                message=feed_message,
            )
            skip_evidence_path: Path | None = None
            if execution_mode == "shadow":
                skip_evidence_path = _session_skip_evidence_path(
                    status.sessions_dir, running_session.session_id
                )
                skip_evidence = ForwardPaperSessionSkipEvidence(
                    runtime_id=runtime_id,
                    session_id=running_session.session_id,
                    session_outcome="skipped_unavailable_feed",
                    feed_health_status=unavailable_health.status,
                    feed_health_message=unavailable_health.message,
                    configured_base_url=configured_base_url,
                    observed_at=completed_at,
                )
                _write_json_artifact(skip_evidence_path, skip_evidence)
            skipped_session = _skipped_session_summary(
                session_summary=running_session.model_copy(
                    update={
                        "market_source": market_source,
                        "live_symbol": status.live_symbol,
                        "live_interval": status.live_interval,
                        "venue_constraints_path": status.venue_constraints_path,
                        "skip_evidence_path": skip_evidence_path,
                    }
                ),
                completed_at=completed_at,
                outcome="skipped_unavailable_feed",
                feed_health=unavailable_health,
            )
            _write_session_summary(skipped_session, session_path)
            append_forward_paper_history(
                status.history_path,
                ForwardPaperHistoryEvent(
                    event_type="session.completed",
                    runtime_id=runtime_id,
                    session_id=skipped_session.session_id,
                    session_number=skipped_session.session_number,
                    occurred_at=completed_at,
                    status="completed",
                    message=skipped_session.session_outcome,
                ),
            )
            status = status.model_copy(
                update={
                    "feed_health": unavailable_health,
                    "venue_constraints_ready": status.venue_constraints_ready,
                    "updated_at": completed_at,
                }
            )
            _persist_runtime_status(status)
            status = _complete_status(
                status=status,
                session_summary=skipped_session,
                completed_at=completed_at,
            )
            status, account_state, _, _ = reconcile_forward_paper_runtime(
                status=status,
                paths=paths,
                reconciled_at=completed_at,
                require_local_match=False,
                recovered_session_id=recovered_session_id,
                recovery_note=recovery_note,
            )
            recovered_session_id = None
            recovery_note = None
            _persist_runtime_status(status)
            completed_sessions.append(skipped_session)
        except (KeyboardInterrupt, SystemExit):
            interrupted_at = _normalize_datetime(now_fn())
            status, _, _ = _recover_interrupted_session(
                status=status,
                recovered_at=interrupted_at,
            )
            raise
        except Exception as exc:
            failed_at = _normalize_datetime(now_fn())
            failed_session = _failed_session_summary(
                session_summary=running_session,
                failed_at=failed_at,
                error=exc,
            )
            _write_session_summary(failed_session, session_path)
            append_forward_paper_history(
                status.history_path,
                ForwardPaperHistoryEvent(
                    event_type="session.failed",
                    runtime_id=runtime_id,
                    session_id=failed_session.session_id,
                    session_number=failed_session.session_number,
                    occurred_at=failed_at,
                    status="failed",
                    run_id=failed_session.run_id,
                    message=failed_session.error_message,
                ),
            )
            status = _complete_status(
                status=status,
                session_summary=failed_session,
                completed_at=failed_at,
            )
            raise

    _materialize_live_gate_artifacts(
        status=status,
        paths=paths,
        generated_at=_normalize_datetime(now_fn()),
    )

    return ForwardPaperRuntimeResult(
        runtime_id=status.runtime_id,
        registry_path=status.registry_path,
        status_path=status.status_path,
        history_path=status.history_path,
        sessions_dir=status.sessions_dir,
        live_market_status_path=status.live_market_status_path,
        venue_constraints_path=status.venue_constraints_path,
        account_state_path=status.account_state_path,
        reconciliation_report_path=status.reconciliation_report_path,
        recovery_status_path=status.recovery_status_path,
        execution_mode=status.execution_mode,
        execution_state_dir=status.execution_state_dir,
        live_control_config_path=status.live_control_config_path,
        live_control_status_path=status.live_control_status_path,
        readiness_status_path=status.readiness_status_path,
        manual_control_state_path=status.manual_control_state_path,
        shadow_canary_evaluation_path=status.shadow_canary_evaluation_path,
        live_market_preflight_path=paths.live_market_preflight_path,
        soak_evaluation_path=status.soak_evaluation_path,
        shadow_evaluation_path=status.shadow_evaluation_path,
        live_gate_decision_path=status.live_gate_decision_path,
        live_gate_threshold_summary_path=status.live_gate_threshold_summary_path,
        live_gate_report_path=status.live_gate_report_path,
        live_launch_verdict_path=status.live_launch_verdict_path,
        live_authority_state_path=status.live_authority_state_path,
        live_launch_window_path=status.live_launch_window_path,
        live_transmission_decision_path=status.live_transmission_decision_path,
        live_transmission_result_path=status.live_transmission_result_path,
        live_approval_state_path=status.live_approval_state_path,
        session_count=len(completed_sessions),
        session_summaries=completed_sessions,
    )
