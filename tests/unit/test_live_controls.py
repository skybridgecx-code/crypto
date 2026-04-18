from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from crypto_agent.evaluation.models import ReplayPnLSummary
from crypto_agent.execution.models import ExecutionRequestArtifact, VenueOrderRequest
from crypto_agent.policy.live_controls import (
    LiveControlConfig,
    LiveControlDecision,
    ManualControlState,
    build_limited_live_transmission_decision_artifact,
    evaluate_post_run_controls,
    evaluate_preflight_controls,
)
from crypto_agent.runtime.models import (
    ForwardPaperRuntimeAccountState,
    ForwardPaperSessionSummary,
    LiveApprovalStateArtifact,
    LiveAuthorityStateArtifact,
    LiveLaunchWindowArtifact,
)


def _ts(year: int, month: int, day: int, hour: int, minute: int) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


def _account_state(
    *,
    starting_equity_usd: float = 100_000.0,
    net_realized_pnl_usd: float = 0.0,
    open_position_count: int = 0,
) -> ForwardPaperRuntimeAccountState:
    return ForwardPaperRuntimeAccountState(
        runtime_id="runtime-demo",
        updated_at=_ts(2026, 4, 6, 9, 0),
        starting_equity_usd=starting_equity_usd,
        cash_balance_usd=starting_equity_usd + net_realized_pnl_usd,
        net_realized_pnl_usd=net_realized_pnl_usd,
        ending_equity_usd=starting_equity_usd + net_realized_pnl_usd,
        positions=[
            {
                "symbol": f"BTCUSDT-{index}",
                "quantity": 0.1,
                "entry_price": 100.0,
                "mark_price": 100.0,
                "market_value_usd": 10.0,
                "unrealized_pnl_usd": 0.0,
            }
            for index in range(open_position_count)
        ],
    )


def _request_artifact(
    *,
    venue: str = "binance_spot_testnet",
    estimated_notional_usd: float = 250.0,
):
    request = VenueOrderRequest(
        request_id="request-1",
        client_order_id="client-order-1",
        venue=venue,
        execution_mode="sandbox",
        sandbox=True,
        proposal_id="proposal-1",
        intent_id="intent-1",
        symbol="BTCUSDT",
        side="buy",
        order_type="market",
        time_in_force="ioc",
        quantity=1.0,
        reference_price=estimated_notional_usd,
        estimated_notional_usd=estimated_notional_usd,
        min_notional_usd=10.0,
        normalization_status="ready",
    )
    return ExecutionRequestArtifact(
        run_id="run-1",
        session_id="session-0001",
        execution_mode="sandbox",
        request_count=1,
        rejected_request_count=0,
        requests=[request],
    )


def test_preflight_controls_block_disallowed_mode_and_symbol_allowlist() -> None:
    controls = LiveControlConfig(
        runtime_id="runtime-demo",
        updated_at=_ts(2026, 4, 6, 9, 0),
        allowed_execution_modes=["paper"],
        symbol_allowlist=["ETHUSDT"],
        max_open_positions=3,
    )
    decision = evaluate_preflight_controls(
        runtime_id="runtime-demo",
        session_id="session-0001",
        execution_mode="shadow",
        requested_symbols=["BTCUSDT"],
        account_state=_account_state(),
        controls=controls,
        readiness_status="ready",
        manual_controls=ManualControlState(
            runtime_id="runtime-demo",
            updated_at=_ts(2026, 4, 6, 9, 0),
        ),
        checked_at=_ts(2026, 4, 6, 9, 1),
        last_completed_session=None,
    )

    assert decision.action == "no_go"
    assert "execution_mode_not_allowed" in decision.reason_codes
    assert "symbol_not_allowed:BTCUSDT" in decision.reason_codes


def test_preflight_controls_block_daily_loss_open_positions_and_prior_session_loss() -> None:
    controls = LiveControlConfig(
        runtime_id="runtime-demo",
        updated_at=_ts(2026, 4, 6, 9, 0),
        symbol_allowlist=["BTCUSDT"],
        max_session_loss_fraction=0.01,
        max_daily_loss_fraction=0.02,
        max_open_positions=1,
    )
    prior_session = ForwardPaperSessionSummary(
        runtime_id="runtime-demo",
        session_id="session-0001",
        session_number=1,
        status="completed",
        session_outcome="executed",
        scheduled_at=_ts(2026, 4, 6, 8, 0),
        started_at=_ts(2026, 4, 6, 8, 0),
        completed_at=_ts(2026, 4, 6, 8, 1),
        pnl=ReplayPnLSummary(
            starting_equity_usd=100_000.0,
            ending_equity_usd=98_500.0,
        ),
    )
    decision = evaluate_preflight_controls(
        runtime_id="runtime-demo",
        session_id="session-0002",
        execution_mode="paper",
        requested_symbols=["BTCUSDT"],
        account_state=_account_state(
            net_realized_pnl_usd=-2_500.0,
            open_position_count=2,
        ),
        controls=controls,
        readiness_status="ready",
        manual_controls=ManualControlState(
            runtime_id="runtime-demo",
            updated_at=_ts(2026, 4, 6, 9, 0),
        ),
        checked_at=_ts(2026, 4, 6, 9, 1),
        last_completed_session=prior_session,
    )

    assert decision.action == "no_go"
    assert "max_open_positions_exceeded" in decision.reason_codes
    assert "max_daily_loss_exceeded" in decision.reason_codes
    assert "max_session_loss_exceeded" in decision.reason_codes


def test_post_run_controls_require_manual_approval_and_symbol_cap() -> None:
    controls = LiveControlConfig(
        runtime_id="runtime-demo",
        updated_at=_ts(2026, 4, 6, 9, 0),
        symbol_allowlist=["BTCUSDT"],
        per_symbol_max_notional_usd={"BTCUSDT": 100.0},
        manual_approval_above_notional_usd=200.0,
    )
    decision = evaluate_post_run_controls(
        runtime_id="runtime-demo",
        session_id="session-0001",
        execution_mode="sandbox",
        request_artifact=_request_artifact(estimated_notional_usd=250.0),
        session_pnl=ReplayPnLSummary(starting_equity_usd=100_000.0, ending_equity_usd=99_900.0),
        account_state=_account_state(),
        controls=controls,
        manual_controls=ManualControlState(
            runtime_id="runtime-demo",
            updated_at=_ts(2026, 4, 6, 9, 0),
            approval_granted=False,
        ),
        checked_at=_ts(2026, 4, 6, 9, 2),
    )

    assert decision.action == "manual_approval_required"
    assert "manual_approval_required" in decision.reason_codes
    assert "per_symbol_max_notional_exceeded:BTCUSDT" in decision.reason_codes


def test_post_run_controls_enforce_sandbox_testnet_suffix() -> None:
    controls = LiveControlConfig(
        runtime_id="runtime-demo",
        updated_at=_ts(2026, 4, 6, 9, 0),
        symbol_allowlist=["BTCUSDT"],
    )
    decision = evaluate_post_run_controls(
        runtime_id="runtime-demo",
        session_id="session-0001",
        execution_mode="sandbox",
        request_artifact=_request_artifact(venue="binance_spot"),
        session_pnl=ReplayPnLSummary(starting_equity_usd=100_000.0, ending_equity_usd=100_100.0),
        account_state=_account_state(),
        controls=controls,
        manual_controls=ManualControlState(
            runtime_id="runtime-demo",
            updated_at=_ts(2026, 4, 6, 9, 0),
            approval_granted=True,
        ),
        checked_at=_ts(2026, 4, 6, 9, 2),
    )

    assert decision.action == "no_go"
    assert decision.reason_codes == ["sandbox_venue_not_testnet"]


def test_limited_live_gate_decision_stays_denied_by_default(tmp_path: Path) -> None:
    authority_path = tmp_path / "live_authority_state.json"
    launch_window_path = tmp_path / "live_launch_window.json"
    approval_state_path = tmp_path / "live_approval_state.json"

    authority_path.write_text(
        json.dumps(
            LiveAuthorityStateArtifact(
                runtime_id="runtime-demo",
                generated_at=_ts(2026, 4, 11, 9, 0),
                summary="Limited-live authority is disabled by default.",
                reason_codes=["live_authority_disabled_by_default"],
            ).model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    launch_window_path.write_text(
        json.dumps(
            LiveLaunchWindowArtifact(
                runtime_id="runtime-demo",
                generated_at=_ts(2026, 4, 11, 9, 0),
                summary="No limited-live launch window is configured.",
                reason_codes=["launch_window_not_configured"],
            ).model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    approval_state_path.write_text(
        json.dumps(
            LiveApprovalStateArtifact(
                runtime_id="runtime-demo",
                generated_at=_ts(2026, 4, 11, 9, 0),
                summary="No live approvals are active. Limited-live transmission remains denied.",
                reason_codes=["no_active_live_approval"],
            ).model_dump(mode="json"),
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    decision = build_limited_live_transmission_decision_artifact(
        runtime_id="runtime-demo",
        authority_state_path=authority_path,
        launch_window_path=launch_window_path,
        approval_state_path=approval_state_path,
        readiness_status="ready",
        limited_live_gate_status="ready_for_review",
        manual_controls=ManualControlState(
            runtime_id="runtime-demo",
            updated_at=_ts(2026, 4, 11, 9, 0),
            halt_active=False,
        ),
        reconciliation_status="clean",
        latest_decision=LiveControlDecision(
            runtime_id="runtime-demo",
            session_id="session-0001",
            checked_at=_ts(2026, 4, 11, 9, 1),
            stage="preflight",
            execution_mode="paper",
            action="go",
            summary="Controls passed.",
        ),
        generated_at=_ts(2026, 4, 11, 9, 1),
    )

    assert decision.transmission_authorized is False
    assert "live_authority_disabled_by_default" in decision.reason_codes
    assert "launch_window_not_configured" in decision.reason_codes
    assert "no_active_live_approval" in decision.reason_codes
    assert "limited_live_transmission_not_implemented" in decision.reason_codes
    assert decision.approval_state_path == approval_state_path
