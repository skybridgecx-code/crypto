from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from crypto_agent.config import load_settings
from crypto_agent.execution.live_adapter import (
    ScriptedLiveExecutionAdapter,
    ScriptedSandboxExecutionAdapter,
)
from crypto_agent.execution.models import (
    ExecutionRequestArtifact,
    ExecutionResultArtifact,
    ExecutionStatusArtifact,
    LiveTransmissionAck,
    LiveTransmissionOrderState,
    LiveTransmissionRequestArtifact,
    LiveTransmissionResultArtifact,
    LiveTransmissionStateArtifact,
    VenueExecutionAck,
    VenueOrderState,
)
from crypto_agent.market_data.live_adapter import BinanceSpotLiveMarketDataAdapter
from crypto_agent.policy.live_controls import LiveControlConfig
from crypto_agent.policy.readiness import default_live_readiness_status
from crypto_agent.runtime.loop import run_forward_paper_runtime
from crypto_agent.runtime.models import (
    ForwardPaperRuntimeStatus,
    LiveApprovalStateArtifact,
    LiveRehearsalGateScope,
    LiveTransmissionDecisionArtifact,
    LiveTransmissionPerRequestDecisionArtifact,
    LiveTransmissionPerRequestResultArtifact,
    LiveTransmissionRuntimeResultArtifact,
)

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


def _ts(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _exchange_info() -> dict[str, object]:
    return {
        "symbols": [
            {
                "symbol": "BTCUSDT",
                "status": "TRADING",
                "baseAsset": "BTC",
                "quoteAsset": "USDT",
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                    {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10.00"},
                ],
            }
        ]
    }


class ScriptedFetcher:
    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)

    def __call__(self, endpoint: str, params: dict[str, str]) -> object:
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _live_adapter() -> BinanceSpotLiveMarketDataAdapter:
    fixture_klines = [
        [
            int(datetime.fromisoformat(row["open_time"].replace("Z", "+00:00")).timestamp() * 1000),
            str(row["open"]),
            str(row["high"]),
            str(row["low"]),
            str(row["close"]),
            str(row["volume"]),
            int(
                datetime.fromisoformat(row["close_time"].replace("Z", "+00:00")).timestamp() * 1000
            ),
            "0",
            0,
            "0",
            "0",
            "0",
        ]
        for row in (
            json.loads(line)
            for line in (FIXTURES_DIR / "paper_candles_breakout_long.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        )
    ]
    fetcher = ScriptedFetcher(
        [
            _exchange_info(),
            fixture_klines,
            {
                "symbol": "BTCUSDT",
                "bidPrice": "103.70",
                "bidQty": "1.5",
                "askPrice": "103.80",
                "askQty": "1.4",
            },
        ]
    )
    return BinanceSpotLiveMarketDataAdapter(fetch_json=fetcher)


def _write_active_live_approval(
    *,
    tmp_path: Path,
    runtime_id: str,
    generated_at: datetime,
) -> Path:
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
                summary="One live approval is active for boundary testing.",
                reason_codes=[],
            ).model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return approval_path


def _permissive_live_controls(runtime_id: str, updated_at: datetime) -> LiveControlConfig:
    return LiveControlConfig(
        runtime_id=runtime_id,
        updated_at=updated_at,
        symbol_allowlist=["BTCUSDT"],
        per_symbol_max_notional_usd={"BTCUSDT": 1_000_000.0},
        max_session_loss_fraction=1.0,
        max_daily_loss_fraction=1.0,
        max_open_positions=10,
        manual_approval_above_notional_usd=1_000_000.0,
    )


def test_forward_runtime_live_shadow_mode_writes_execution_artifacts(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-live-shadow",
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
    )

    session = result.session_summaries[0]
    assert session.execution_mode == "shadow"
    assert session.execution_request_path is not None
    assert session.execution_result_path is not None
    assert session.execution_status_path is not None

    requests = ExecutionRequestArtifact.model_validate(
        json.loads(Path(session.execution_request_path).read_text(encoding="utf-8"))
    )
    results = ExecutionResultArtifact.model_validate(
        json.loads(Path(session.execution_result_path).read_text(encoding="utf-8"))
    )
    statuses = ExecutionStatusArtifact.model_validate(
        json.loads(Path(session.execution_status_path).read_text(encoding="utf-8"))
    )
    status = ForwardPaperRuntimeStatus.model_validate(
        json.loads(result.status_path.read_text(encoding="utf-8"))
    )

    assert requests.execution_mode == "shadow"
    assert results.result_count == requests.request_count
    assert statuses.terminal_status_count == statuses.status_count
    assert status.execution_mode == "shadow"


def test_forward_runtime_live_sandbox_mode_writes_adapter_evidence(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    adapter = ScriptedSandboxExecutionAdapter(
        submit_fn=lambda request: VenueExecutionAck(
            request_id=request.request_id,
            client_order_id=request.client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            status="accepted",
            venue_order_id="sandbox-order-1",
            observed_at=_ts(2026, 4, 3, 16, 4),
        ),
        fetch_state_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="filled",
            terminal=True,
            filled_quantity=request.quantity,
            average_fill_price=request.reference_price,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
        cancel_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="canceled",
            terminal=True,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
    )

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id="forward-live-sandbox",
        session_interval_seconds=60,
        execution_mode="sandbox",
        max_sessions=1,
        tick_times=[_ts(2026, 4, 3, 16, 4)],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        sandbox_execution_adapter=adapter,
    )

    session = result.session_summaries[0]
    requests = ExecutionRequestArtifact.model_validate(
        json.loads(Path(session.execution_request_path).read_text(encoding="utf-8"))
    )
    results = ExecutionResultArtifact.model_validate(
        json.loads(Path(session.execution_result_path).read_text(encoding="utf-8"))
    )
    statuses = ExecutionStatusArtifact.model_validate(
        json.loads(Path(session.execution_status_path).read_text(encoding="utf-8"))
    )

    assert session.execution_mode == "sandbox"
    assert requests.request_count >= 1
    assert results.results[0].status == "accepted"
    assert statuses.statuses[0].state == "filled"


def test_limited_live_boundary_authorizes_without_affecting_shadow_path(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-live-shadow-boundary"
    tick_time = _ts(2026, 4, 3, 16, 4)
    _write_active_live_approval(tmp_path=tmp_path, runtime_id=runtime_id, generated_at=tick_time)
    readiness = default_live_readiness_status(
        runtime_id=runtime_id,
        updated_at=tick_time,
    ).model_copy(update={"limited_live_gate_status": "ready_for_review"})
    controls = _permissive_live_controls(runtime_id=runtime_id, updated_at=tick_time)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[tick_time],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        limited_live_authority_enabled=True,
        live_launch_window_starts_at=_ts(2026, 4, 3, 16, 0),
        live_launch_window_ends_at=_ts(2026, 4, 3, 16, 10),
        live_control_config=controls,
        readiness_status=readiness,
    )

    decision = LiveTransmissionDecisionArtifact.model_validate(
        json.loads(result.live_transmission_decision_path.read_text(encoding="utf-8"))
    )
    runtime_transmission_result = LiveTransmissionRuntimeResultArtifact.model_validate(
        json.loads(result.live_transmission_result_path.read_text(encoding="utf-8"))
    )
    session = result.session_summaries[0]
    results = ExecutionResultArtifact.model_validate(
        json.loads(Path(session.execution_result_path).read_text(encoding="utf-8"))
    )
    live_request = LiveTransmissionRequestArtifact.model_validate(
        json.loads(Path(session.live_transmission_request_path).read_text(encoding="utf-8"))
    )
    live_result = LiveTransmissionResultArtifact.model_validate(
        json.loads(Path(session.live_transmission_result_path).read_text(encoding="utf-8"))
    )
    live_state = LiveTransmissionStateArtifact.model_validate(
        json.loads(Path(session.live_transmission_state_path).read_text(encoding="utf-8"))
    )
    per_request_decision = LiveTransmissionPerRequestDecisionArtifact.model_validate(
        json.loads(
            Path(session.live_transmission_request_decision_path).read_text(encoding="utf-8")
        )
    )
    per_request_result = LiveTransmissionPerRequestResultArtifact.model_validate(
        json.loads(Path(session.live_transmission_request_result_path).read_text(encoding="utf-8"))
    )

    assert decision.decision == "authorized"
    assert decision.transmission_authorized is True
    assert runtime_transmission_result.transmission_eligible is True
    assert runtime_transmission_result.transmission_attempted is False
    assert runtime_transmission_result.adapter_submission_attempted is False
    assert runtime_transmission_result.rehearsal_gate_state == "inactive"
    assert runtime_transmission_result.rehearsal_gate_scope_state == "absent"
    assert runtime_transmission_result.rehearsal_gate_match is False
    assert runtime_transmission_result.rehearsal_gate_reason_codes == [
        "operator_rehearsal_gate_inactive",
        "operator_rehearsal_gate_scope_absent",
    ]
    assert runtime_transmission_result.rehearsal_gate_passed is False
    assert runtime_transmission_result.final_state == "not_submitted_terminal_blocked"
    assert session.execution_mode == "shadow"
    assert all(result.status == "would_send" for result in results.results)
    assert live_request.request_count == results.result_count
    assert live_result.adapter_call_attempted is False
    assert live_result.submission_status == "not_submitted"
    assert "operator_rehearsal_gate_inactive" in live_result.reason_codes
    assert per_request_decision.request_id == live_request.requests[0].request_id
    assert per_request_decision.bounded_decision == "denied"
    assert per_request_decision.bounded_seam_allowed is False
    assert "operator_rehearsal_gate_scope_absent" in per_request_decision.reason_codes
    assert per_request_decision.adapter_call_attempted is False
    assert per_request_decision.submission_status == "not_submitted"
    assert per_request_decision.live_transmission_result_path == Path(
        session.live_transmission_result_path
    )
    assert per_request_result.request_id == per_request_decision.request_id
    assert per_request_result.bounded_result_state == "not_submitted_terminal_blocked"
    assert per_request_result.submission_status == "not_submitted"
    assert per_request_result.adapter_call_attempted is False
    assert per_request_result.per_request_decision_path == Path(
        session.live_transmission_request_decision_path
    )
    assert per_request_result.live_transmission_result_path == Path(
        session.live_transmission_result_path
    )
    assert (
        per_request_result.runtime_live_transmission_result_path
        == result.live_transmission_result_path
    )
    assert live_state.state == "not_submitted_terminal_blocked"
    assert live_state.terminal is True
    assert live_result.generated_at <= live_state.generated_at


def test_limited_live_boundary_authorizes_without_affecting_sandbox_path(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-live-sandbox-boundary"
    tick_time = _ts(2026, 4, 3, 16, 4)
    _write_active_live_approval(tmp_path=tmp_path, runtime_id=runtime_id, generated_at=tick_time)
    readiness = default_live_readiness_status(
        runtime_id=runtime_id,
        updated_at=tick_time,
    ).model_copy(update={"limited_live_gate_status": "ready_for_review"})
    controls = _permissive_live_controls(runtime_id=runtime_id, updated_at=tick_time)
    adapter = ScriptedSandboxExecutionAdapter(
        submit_fn=lambda request: VenueExecutionAck(
            request_id=request.request_id,
            client_order_id=request.client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            status="accepted",
            venue_order_id="sandbox-order-1",
            observed_at=tick_time,
        ),
        fetch_state_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="filled",
            terminal=True,
            filled_quantity=request.quantity,
            average_fill_price=request.reference_price,
            updated_at=tick_time,
        ),
        cancel_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="canceled",
            terminal=True,
            updated_at=tick_time,
        ),
    )

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="sandbox",
        max_sessions=1,
        tick_times=[tick_time],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        sandbox_execution_adapter=adapter,
        limited_live_authority_enabled=True,
        live_launch_window_starts_at=_ts(2026, 4, 3, 16, 0),
        live_launch_window_ends_at=_ts(2026, 4, 3, 16, 10),
        live_control_config=controls,
        readiness_status=readiness,
    )

    decision = LiveTransmissionDecisionArtifact.model_validate(
        json.loads(result.live_transmission_decision_path.read_text(encoding="utf-8"))
    )
    runtime_transmission_result = LiveTransmissionRuntimeResultArtifact.model_validate(
        json.loads(result.live_transmission_result_path.read_text(encoding="utf-8"))
    )
    session = result.session_summaries[0]
    statuses = ExecutionStatusArtifact.model_validate(
        json.loads(Path(session.execution_status_path).read_text(encoding="utf-8"))
    )
    live_request = LiveTransmissionRequestArtifact.model_validate(
        json.loads(Path(session.live_transmission_request_path).read_text(encoding="utf-8"))
    )
    live_result = LiveTransmissionResultArtifact.model_validate(
        json.loads(Path(session.live_transmission_result_path).read_text(encoding="utf-8"))
    )
    live_state = LiveTransmissionStateArtifact.model_validate(
        json.loads(Path(session.live_transmission_state_path).read_text(encoding="utf-8"))
    )
    per_request_decision = LiveTransmissionPerRequestDecisionArtifact.model_validate(
        json.loads(
            Path(session.live_transmission_request_decision_path).read_text(encoding="utf-8")
        )
    )
    assert decision.decision == "authorized"
    assert decision.transmission_authorized is True
    assert runtime_transmission_result.transmission_eligible is True
    assert runtime_transmission_result.transmission_attempted is False
    assert runtime_transmission_result.adapter_submission_attempted is False
    assert runtime_transmission_result.rehearsal_gate_state == "inactive"
    assert runtime_transmission_result.rehearsal_gate_scope_state == "absent"
    assert runtime_transmission_result.rehearsal_gate_match is False
    assert runtime_transmission_result.rehearsal_gate_reason_codes == [
        "operator_rehearsal_gate_inactive",
        "operator_rehearsal_gate_scope_absent",
    ]
    assert runtime_transmission_result.rehearsal_gate_passed is False
    assert runtime_transmission_result.final_state == "not_submitted_terminal_blocked"
    assert session.execution_mode == "sandbox"
    assert statuses.statuses[0].state == "filled"
    assert live_request.request_count >= 1
    assert live_result.adapter_call_attempted is False
    assert live_result.submission_status == "not_submitted"
    assert "operator_rehearsal_gate_inactive" in live_result.reason_codes
    assert per_request_decision.bounded_decision == "denied"
    assert per_request_decision.bounded_seam_allowed is False
    assert "operator_rehearsal_gate_scope_absent" in per_request_decision.reason_codes
    assert per_request_decision.adapter_call_attempted is False
    assert per_request_decision.submission_status == "not_submitted"
    assert live_state.submission_present is False


def test_limited_live_boundary_authorized_writes_live_artifacts_in_order(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-live-shadow-live-artifacts-order"
    tick_time = _ts(2026, 4, 3, 16, 4)
    _write_active_live_approval(tmp_path=tmp_path, runtime_id=runtime_id, generated_at=tick_time)
    readiness = default_live_readiness_status(
        runtime_id=runtime_id,
        updated_at=tick_time,
    ).model_copy(update={"limited_live_gate_status": "ready_for_review"})
    controls = _permissive_live_controls(runtime_id=runtime_id, updated_at=tick_time)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[tick_time],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        limited_live_authority_enabled=True,
        live_launch_window_starts_at=_ts(2026, 4, 3, 16, 0),
        live_launch_window_ends_at=_ts(2026, 4, 3, 16, 10),
        live_control_config=controls,
        readiness_status=readiness,
    )

    session = result.session_summaries[0]
    assert session.live_transmission_request_path is not None
    assert session.live_transmission_result_path is not None
    assert session.live_transmission_state_path is not None

    live_request_path = Path(session.live_transmission_request_path)
    live_result_path = Path(session.live_transmission_result_path)
    live_state_path = Path(session.live_transmission_state_path)
    live_request = LiveTransmissionRequestArtifact.model_validate(
        json.loads(live_request_path.read_text(encoding="utf-8"))
    )
    live_result = LiveTransmissionResultArtifact.model_validate(
        json.loads(live_result_path.read_text(encoding="utf-8"))
    )
    live_state = LiveTransmissionStateArtifact.model_validate(
        json.loads(live_state_path.read_text(encoding="utf-8"))
    )

    assert live_request.request_count >= 1
    assert live_result.adapter_call_attempted is False
    assert live_result.submission_status == "not_submitted"
    assert live_state.state == "not_submitted_terminal_blocked"
    assert live_state.submission_present is False
    assert (
        live_request_path.stat().st_mtime_ns
        <= live_result_path.stat().st_mtime_ns
        <= live_state_path.stat().st_mtime_ns
    )


def test_limited_live_boundary_authorized_invokes_live_adapter_once(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-live-shadow-live-adapter-call"
    tick_time = _ts(2026, 4, 3, 16, 4)
    _write_active_live_approval(tmp_path=tmp_path, runtime_id=runtime_id, generated_at=tick_time)
    readiness = default_live_readiness_status(
        runtime_id=runtime_id,
        updated_at=tick_time,
    ).model_copy(update={"limited_live_gate_status": "ready_for_review"})
    controls = _permissive_live_controls(runtime_id=runtime_id, updated_at=tick_time)
    call_counts = {"submit": 0, "fetch": 0, "cancel": 0}
    live_adapter = ScriptedLiveExecutionAdapter(
        submit_fn=lambda request: (
            call_counts.__setitem__("submit", call_counts["submit"] + 1)
            or LiveTransmissionAck(
                request_id=request.request_id,
                client_order_id=request.client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                status="accepted",
                venue_order_id="live-order-1",
                observed_at=tick_time,
            )
        ),
        fetch_state_fn=lambda client_order_id, request: (
            call_counts.__setitem__("fetch", call_counts["fetch"] + 1)
            or LiveTransmissionOrderState(
                request_id=request.request_id,
                client_order_id=client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                venue_order_id="live-order-1",
                state="filled",
                terminal=True,
                filled_quantity=request.quantity,
                average_fill_price=request.reference_price,
                updated_at=tick_time,
            )
        ),
        cancel_fn=lambda client_order_id, request: (
            call_counts.__setitem__("cancel", call_counts["cancel"] + 1)
            or LiveTransmissionOrderState(
                request_id=request.request_id,
                client_order_id=client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                venue_order_id="live-order-1",
                state="canceled",
                terminal=True,
                updated_at=tick_time,
            )
        ),
    )

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[tick_time],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        limited_live_authority_enabled=True,
        live_launch_window_starts_at=_ts(2026, 4, 3, 16, 0),
        live_launch_window_ends_at=_ts(2026, 4, 3, 16, 10),
        live_control_config=controls,
        readiness_status=readiness,
        live_execution_adapter=live_adapter,
        live_rehearsal_gate_scope=LiveRehearsalGateScope(
            runtime_id=runtime_id,
            session_id="session-0001",
            request_id="single_request",
        ),
    )

    session = result.session_summaries[0]
    live_result = LiveTransmissionResultArtifact.model_validate(
        json.loads(Path(session.live_transmission_result_path).read_text(encoding="utf-8"))
    )
    live_state = LiveTransmissionStateArtifact.model_validate(
        json.loads(Path(session.live_transmission_state_path).read_text(encoding="utf-8"))
    )
    per_request_decision = LiveTransmissionPerRequestDecisionArtifact.model_validate(
        json.loads(
            Path(session.live_transmission_request_decision_path).read_text(encoding="utf-8")
        )
    )
    per_request_result = LiveTransmissionPerRequestResultArtifact.model_validate(
        json.loads(Path(session.live_transmission_request_result_path).read_text(encoding="utf-8"))
    )
    runtime_transmission_result = LiveTransmissionRuntimeResultArtifact.model_validate(
        json.loads(result.live_transmission_result_path.read_text(encoding="utf-8"))
    )

    assert call_counts == {"submit": 1, "fetch": 1, "cancel": 0}
    assert live_result.adapter_call_attempted is True
    assert live_result.submission_status == "submitted"
    assert live_result.ack is not None
    assert live_result.ack.status == "accepted"
    assert live_state.submission_present is True
    assert live_state.state == "filled"
    assert live_state.order_state is not None
    assert live_state.order_state.state == "filled"
    assert runtime_transmission_result.transmission_eligible is True
    assert runtime_transmission_result.transmission_attempted is True
    assert runtime_transmission_result.adapter_submission_attempted is True
    assert runtime_transmission_result.rehearsal_gate_state == "active"
    assert runtime_transmission_result.rehearsal_gate_scope_state == "matched"
    assert runtime_transmission_result.rehearsal_gate_match is True
    assert runtime_transmission_result.rehearsal_gate_reason_codes == []
    assert runtime_transmission_result.rehearsal_gate_passed is True
    assert runtime_transmission_result.final_state == "filled"
    assert per_request_decision.request_id == live_result.ack.request_id
    assert per_request_decision.bounded_decision == "allowed"
    assert per_request_decision.bounded_seam_allowed is True
    assert per_request_decision.reason_codes == []
    assert per_request_decision.rehearsal_gate_reason_codes == []
    assert per_request_decision.adapter_call_attempted is True
    assert per_request_decision.submission_status == "submitted"
    assert per_request_decision.live_transmission_state_path == Path(
        session.live_transmission_state_path
    )
    assert per_request_result.request_id == per_request_decision.request_id
    assert per_request_result.bounded_result_state == "filled"
    assert per_request_result.submission_status == "submitted"
    assert per_request_result.adapter_call_attempted is True
    assert per_request_result.ack_status == "accepted"
    assert per_request_result.order_state == "filled"
    assert per_request_result.per_request_decision_path == Path(
        session.live_transmission_request_decision_path
    )
    assert per_request_result.live_transmission_state_path == Path(
        session.live_transmission_state_path
    )
    assert (
        per_request_result.runtime_live_transmission_result_path
        == result.live_transmission_result_path
    )


def test_limited_live_rehearsal_gate_scope_mismatch_blocks_adapter_call(tmp_path: Path) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-live-shadow-gate-mismatch"
    tick_time = _ts(2026, 4, 3, 16, 4)
    _write_active_live_approval(tmp_path=tmp_path, runtime_id=runtime_id, generated_at=tick_time)
    readiness = default_live_readiness_status(
        runtime_id=runtime_id,
        updated_at=tick_time,
    ).model_copy(update={"limited_live_gate_status": "ready_for_review"})
    controls = _permissive_live_controls(runtime_id=runtime_id, updated_at=tick_time)
    call_counts = {"submit": 0, "fetch": 0, "cancel": 0}

    live_adapter = ScriptedLiveExecutionAdapter(
        submit_fn=lambda request: (
            call_counts.__setitem__("submit", call_counts["submit"] + 1)
            or LiveTransmissionAck(
                request_id=request.request_id,
                client_order_id=request.client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                status="accepted",
                venue_order_id="live-order-1",
                observed_at=tick_time,
            )
        ),
        fetch_state_fn=lambda client_order_id, request: (
            call_counts.__setitem__("fetch", call_counts["fetch"] + 1)
            or LiveTransmissionOrderState(
                request_id=request.request_id,
                client_order_id=client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                venue_order_id="live-order-1",
                state="filled",
                terminal=True,
                filled_quantity=request.quantity,
                average_fill_price=request.reference_price,
                updated_at=tick_time,
            )
        ),
        cancel_fn=lambda client_order_id, request: (
            call_counts.__setitem__("cancel", call_counts["cancel"] + 1)
            or LiveTransmissionOrderState(
                request_id=request.request_id,
                client_order_id=client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                venue_order_id="live-order-1",
                state="canceled",
                terminal=True,
                updated_at=tick_time,
            )
        ),
    )

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[tick_time],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        limited_live_authority_enabled=True,
        live_launch_window_starts_at=_ts(2026, 4, 3, 16, 0),
        live_launch_window_ends_at=_ts(2026, 4, 3, 16, 10),
        live_control_config=controls,
        readiness_status=readiness,
        live_execution_adapter=live_adapter,
        live_rehearsal_gate_scope=LiveRehearsalGateScope(
            runtime_id=runtime_id,
            session_id="session-0001",
            request_id="wrong-request-id",
        ),
    )

    session = result.session_summaries[0]
    live_result = LiveTransmissionResultArtifact.model_validate(
        json.loads(Path(session.live_transmission_result_path).read_text(encoding="utf-8"))
    )
    per_request_decision = LiveTransmissionPerRequestDecisionArtifact.model_validate(
        json.loads(
            Path(session.live_transmission_request_decision_path).read_text(encoding="utf-8")
        )
    )
    per_request_result = LiveTransmissionPerRequestResultArtifact.model_validate(
        json.loads(Path(session.live_transmission_request_result_path).read_text(encoding="utf-8"))
    )
    runtime_transmission_result = LiveTransmissionRuntimeResultArtifact.model_validate(
        json.loads(result.live_transmission_result_path.read_text(encoding="utf-8"))
    )

    assert call_counts == {"submit": 0, "fetch": 0, "cancel": 0}
    assert live_result.adapter_call_attempted is False
    assert live_result.submission_status == "not_submitted"
    assert "operator_rehearsal_gate_scope_mismatch" in live_result.reason_codes
    assert runtime_transmission_result.transmission_attempted is False
    assert runtime_transmission_result.adapter_submission_attempted is False
    assert runtime_transmission_result.rehearsal_gate_state == "inactive"
    assert runtime_transmission_result.rehearsal_gate_scope_state == "mismatched"
    assert runtime_transmission_result.rehearsal_gate_match is False
    assert (
        "operator_rehearsal_gate_inactive"
        in runtime_transmission_result.rehearsal_gate_reason_codes
    )
    assert (
        "operator_rehearsal_gate_scope_mismatch"
        in runtime_transmission_result.rehearsal_gate_reason_codes
    )
    assert (
        "operator_rehearsal_gate_request_mismatch"
        in runtime_transmission_result.rehearsal_gate_reason_codes
    )
    assert runtime_transmission_result.rehearsal_gate_passed is False
    assert per_request_decision.bounded_decision == "denied"
    assert per_request_decision.bounded_seam_allowed is False
    assert "operator_rehearsal_gate_scope_mismatch" in per_request_decision.reason_codes
    assert (
        "operator_rehearsal_gate_request_mismatch"
        in per_request_decision.rehearsal_gate_reason_codes
    )
    assert per_request_result.request_id == per_request_decision.request_id
    assert per_request_result.bounded_result_state == "not_submitted_terminal_blocked"
    assert per_request_result.submission_status == "not_submitted"
    assert per_request_result.adapter_call_attempted is False


def test_limited_live_rehearsal_gate_multi_field_mismatch_reasons_are_recorded(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    runtime_id = "forward-live-shadow-gate-mismatch-all-fields"
    tick_time = _ts(2026, 4, 3, 16, 4)
    _write_active_live_approval(tmp_path=tmp_path, runtime_id=runtime_id, generated_at=tick_time)
    readiness = default_live_readiness_status(
        runtime_id=runtime_id,
        updated_at=tick_time,
    ).model_copy(update={"limited_live_gate_status": "ready_for_review"})
    controls = _permissive_live_controls(runtime_id=runtime_id, updated_at=tick_time)

    result = run_forward_paper_runtime(
        None,
        settings=settings,
        runtime_id=runtime_id,
        session_interval_seconds=60,
        execution_mode="shadow",
        max_sessions=1,
        tick_times=[tick_time],
        market_source="binance_spot",
        live_symbol="BTCUSDT",
        live_interval="1m",
        live_lookback_candles=4,
        feed_stale_after_seconds=120,
        live_adapter=_live_adapter(),
        limited_live_authority_enabled=True,
        live_launch_window_starts_at=_ts(2026, 4, 3, 16, 0),
        live_launch_window_ends_at=_ts(2026, 4, 3, 16, 10),
        live_control_config=controls,
        readiness_status=readiness,
        live_execution_adapter=ScriptedLiveExecutionAdapter(
            submit_fn=lambda request: LiveTransmissionAck(
                request_id=request.request_id,
                client_order_id=request.client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                status="accepted",
                venue_order_id="live-order-1",
                observed_at=tick_time,
            ),
            fetch_state_fn=lambda client_order_id, request: LiveTransmissionOrderState(
                request_id=request.request_id,
                client_order_id=client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                venue_order_id="live-order-1",
                state="filled",
                terminal=True,
                filled_quantity=request.quantity,
                average_fill_price=request.reference_price,
                updated_at=tick_time,
            ),
            cancel_fn=lambda client_order_id, request: LiveTransmissionOrderState(
                request_id=request.request_id,
                client_order_id=client_order_id,
                venue=request.venue,
                intent_id=request.intent_id,
                venue_order_id="live-order-1",
                state="canceled",
                terminal=True,
                updated_at=tick_time,
            ),
        ),
        live_rehearsal_gate_scope=LiveRehearsalGateScope(
            runtime_id="wrong-runtime",
            session_id="wrong-session",
            request_id="wrong-request",
        ),
    )

    session = result.session_summaries[0]
    live_result = LiveTransmissionResultArtifact.model_validate(
        json.loads(Path(session.live_transmission_result_path).read_text(encoding="utf-8"))
    )
    runtime_transmission_result = LiveTransmissionRuntimeResultArtifact.model_validate(
        json.loads(result.live_transmission_result_path.read_text(encoding="utf-8"))
    )

    assert live_result.adapter_call_attempted is False
    assert live_result.submission_status == "not_submitted"
    assert "operator_rehearsal_gate_runtime_mismatch" in live_result.reason_codes
    assert "operator_rehearsal_gate_session_mismatch" in live_result.reason_codes
    assert "operator_rehearsal_gate_request_mismatch" in live_result.reason_codes
    assert (
        "operator_rehearsal_gate_runtime_mismatch"
        in runtime_transmission_result.rehearsal_gate_reason_codes
    )
    assert (
        "operator_rehearsal_gate_session_mismatch"
        in runtime_transmission_result.rehearsal_gate_reason_codes
    )
    assert (
        "operator_rehearsal_gate_request_mismatch"
        in runtime_transmission_result.rehearsal_gate_reason_codes
    )


def test_forward_runtime_replay_sandbox_requires_fixture_rehearsal_flag(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    adapter = ScriptedSandboxExecutionAdapter(
        submit_fn=lambda request: VenueExecutionAck(
            request_id=request.request_id,
            client_order_id=request.client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            status="accepted",
            venue_order_id="sandbox-order-1",
            observed_at=_ts(2026, 4, 3, 16, 4),
        ),
        fetch_state_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="filled",
            terminal=True,
            filled_quantity=request.quantity,
            average_fill_price=request.reference_price,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
        cancel_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="canceled",
            terminal=True,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
    )

    with pytest.raises(
        ValueError,
        match="Shadow and sandbox execution modes require binance_spot market source.",
    ):
        run_forward_paper_runtime(
            Path("tests/fixtures/paper_candles_breakout_long.jsonl"),
            settings=settings,
            runtime_id="forward-replay-sandbox-blocked",
            session_interval_seconds=60,
            execution_mode="sandbox",
            max_sessions=1,
            market_source="replay",
            sandbox_execution_adapter=adapter,
        )


def test_forward_runtime_replay_shadow_remains_blocked_even_with_fixture_rehearsal(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)

    with pytest.raises(
        ValueError,
        match="Shadow and sandbox execution modes require binance_spot market source.",
    ):
        run_forward_paper_runtime(
            Path("tests/fixtures/paper_candles_breakout_long.jsonl"),
            settings=settings,
            runtime_id="forward-replay-shadow-blocked",
            session_interval_seconds=60,
            execution_mode="shadow",
            max_sessions=1,
            market_source="replay",
            sandbox_fixture_rehearsal=True,
        )


def test_forward_runtime_replay_sandbox_fixture_rehearsal_writes_nonzero_adapter_evidence(
    tmp_path: Path,
) -> None:
    settings = _paper_settings_for(tmp_path)
    adapter = ScriptedSandboxExecutionAdapter(
        submit_fn=lambda request: VenueExecutionAck(
            request_id=request.request_id,
            client_order_id=request.client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            status="accepted",
            venue_order_id="sandbox-order-1",
            observed_at=_ts(2026, 4, 3, 16, 4),
        ),
        fetch_state_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="filled",
            terminal=True,
            filled_quantity=request.quantity,
            average_fill_price=request.reference_price,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
        cancel_fn=lambda client_order_id, request: VenueOrderState(
            request_id=request.request_id,
            client_order_id=client_order_id,
            venue=request.venue,
            execution_mode="sandbox",
            sandbox=True,
            intent_id=request.intent_id,
            venue_order_id="sandbox-order-1",
            state="canceled",
            terminal=True,
            updated_at=_ts(2026, 4, 3, 16, 4),
        ),
    )

    result = run_forward_paper_runtime(
        Path("tests/fixtures/paper_candles_breakout_long.jsonl"),
        settings=settings,
        runtime_id="forward-replay-sandbox-fixture",
        session_interval_seconds=60,
        execution_mode="sandbox",
        max_sessions=1,
        market_source="replay",
        sandbox_fixture_rehearsal=True,
        sandbox_execution_adapter=adapter,
    )

    session = result.session_summaries[0]
    requests = ExecutionRequestArtifact.model_validate(
        json.loads(Path(session.execution_request_path).read_text(encoding="utf-8"))
    )
    results = ExecutionResultArtifact.model_validate(
        json.loads(Path(session.execution_result_path).read_text(encoding="utf-8"))
    )
    statuses = ExecutionStatusArtifact.model_validate(
        json.loads(Path(session.execution_status_path).read_text(encoding="utf-8"))
    )

    assert session.execution_mode == "sandbox"
    assert requests.request_count > 0
    assert results.result_count > 0
    assert statuses.status_count > 0
    assert all(request.sandbox is True for request in requests.requests)
    assert all(result.sandbox is True for result in results.results)
    assert all(status.sandbox is True for status in statuses.statuses)
