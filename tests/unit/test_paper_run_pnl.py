from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings
from crypto_agent.enums import EventType, FillStatus, LiquidityRole, Mode, Side
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.evaluation.scorecard import build_replay_pnl
from crypto_agent.events.envelope import EventEnvelope

FIXTURES_DIR = Path("tests/fixtures")


def _paper_settings_for(
    tmp_path: Path,
    *,
    policy_overrides: dict[str, object] | None = None,
):
    settings = load_settings(Path("config/paper.yaml"))
    policy = settings.policy
    if policy_overrides is not None:
        policy = policy.model_copy(update=policy_overrides)
    return settings.model_copy(
        update={
            "paths": settings.paths.model_copy(
                update={
                    "runs_dir": tmp_path / "runs",
                    "journals_dir": tmp_path / "journals",
                }
            ),
            "policy": policy,
        }
    )


def _fill_event(
    *,
    intent_id: str,
    fill_id: str,
    symbol: str,
    side: Side,
    price: float,
    quantity: float,
    fee_usd: float,
    second: int,
) -> EventEnvelope:
    timestamp = datetime(2026, 1, 1, 0, 0, second, tzinfo=UTC)
    notional_usd = price * quantity
    return EventEnvelope(
        event_id=f"event-{fill_id}",
        event_type=EventType.ORDER_FILLED,
        timestamp=timestamp,
        source="execution_engine",
        run_id="inventory-validation",
        strategy_id="inventory-test",
        symbol=symbol,
        mode=Mode.PAPER,
        payload={
            "fill_id": fill_id,
            "intent_id": intent_id,
            "symbol": symbol,
            "side": side.value,
            "status": FillStatus.FILLED.value,
            "price": price,
            "quantity": quantity,
            "notional_usd": notional_usd,
            "fee_usd": fee_usd,
            "liquidity_role": LiquidityRole.TAKER.value,
            "timestamp": timestamp.isoformat(),
            "mode": Mode.PAPER.value,
        },
    )


def test_build_replay_pnl_partial_close_splits_realized_and_unrealized() -> None:
    pnl = build_replay_pnl(
        [
            _fill_event(
                intent_id="intent-1",
                fill_id="fill-1",
                symbol="BTCUSDT",
                side=Side.BUY,
                price=100.0,
                quantity=2.0,
                fee_usd=1.0,
                second=0,
            ),
            _fill_event(
                intent_id="intent-2",
                fill_id="fill-2",
                symbol="BTCUSDT",
                side=Side.SELL,
                price=110.0,
                quantity=1.0,
                fee_usd=0.5,
                second=1,
            ),
        ],
        final_close_by_symbol={"BTCUSDT": 120.0},
        starting_equity_usd=1_000.0,
    )

    assert pnl.gross_realized_pnl_usd == pytest.approx(10.0)
    assert pnl.total_fee_usd == pytest.approx(1.5)
    assert pnl.net_realized_pnl_usd == pytest.approx(8.5)
    assert pnl.ending_unrealized_pnl_usd == pytest.approx(20.0)
    assert pnl.ending_equity_usd == pytest.approx(1_028.5)
    assert pnl.return_fraction == pytest.approx(0.0285)


def test_build_replay_pnl_full_flatten_uses_weighted_average_inventory() -> None:
    pnl = build_replay_pnl(
        [
            _fill_event(
                intent_id="intent-1",
                fill_id="fill-1",
                symbol="BTCUSDT",
                side=Side.BUY,
                price=100.0,
                quantity=1.0,
                fee_usd=0.2,
                second=0,
            ),
            _fill_event(
                intent_id="intent-2",
                fill_id="fill-2",
                symbol="BTCUSDT",
                side=Side.BUY,
                price=120.0,
                quantity=1.0,
                fee_usd=0.2,
                second=1,
            ),
            _fill_event(
                intent_id="intent-3",
                fill_id="fill-3",
                symbol="BTCUSDT",
                side=Side.SELL,
                price=130.0,
                quantity=2.0,
                fee_usd=0.4,
                second=2,
            ),
        ],
        final_close_by_symbol={"BTCUSDT": 125.0},
        starting_equity_usd=1_000.0,
    )

    assert pnl.gross_realized_pnl_usd == pytest.approx(40.0)
    assert pnl.total_fee_usd == pytest.approx(0.8)
    assert pnl.net_realized_pnl_usd == pytest.approx(39.2)
    assert pnl.ending_unrealized_pnl_usd == pytest.approx(0.0)
    assert pnl.ending_equity_usd == pytest.approx(1_039.2)
    assert pnl.return_fraction == pytest.approx(0.0392)


def test_build_replay_pnl_position_flip_resets_inventory_after_crossing_zero() -> None:
    pnl = build_replay_pnl(
        [
            _fill_event(
                intent_id="intent-1",
                fill_id="fill-1",
                symbol="BTCUSDT",
                side=Side.BUY,
                price=100.0,
                quantity=1.0,
                fee_usd=0.1,
                second=0,
            ),
            _fill_event(
                intent_id="intent-2",
                fill_id="fill-2",
                symbol="BTCUSDT",
                side=Side.SELL,
                price=110.0,
                quantity=2.0,
                fee_usd=0.2,
                second=1,
            ),
        ],
        final_close_by_symbol={"BTCUSDT": 105.0},
        starting_equity_usd=1_000.0,
    )

    assert pnl.gross_realized_pnl_usd == pytest.approx(10.0)
    assert pnl.total_fee_usd == pytest.approx(0.3)
    assert pnl.net_realized_pnl_usd == pytest.approx(9.7)
    assert pnl.ending_unrealized_pnl_usd == pytest.approx(5.0)
    assert pnl.ending_equity_usd == pytest.approx(1_014.7)
    assert pnl.return_fraction == pytest.approx(0.0147)


def test_build_replay_pnl_multiple_fills_same_symbol_respects_weighted_average() -> None:
    pnl = build_replay_pnl(
        [
            _fill_event(
                intent_id="intent-1",
                fill_id="fill-1",
                symbol="ETHUSDT",
                side=Side.BUY,
                price=100.0,
                quantity=1.0,
                fee_usd=0.1,
                second=0,
            ),
            _fill_event(
                intent_id="intent-2",
                fill_id="fill-2",
                symbol="ETHUSDT",
                side=Side.BUY,
                price=130.0,
                quantity=2.0,
                fee_usd=0.2,
                second=1,
            ),
            _fill_event(
                intent_id="intent-3",
                fill_id="fill-3",
                symbol="ETHUSDT",
                side=Side.SELL,
                price=90.0,
                quantity=1.0,
                fee_usd=0.1,
                second=2,
            ),
        ],
        final_close_by_symbol={"ETHUSDT": 150.0},
        starting_equity_usd=1_000.0,
    )

    assert pnl.gross_realized_pnl_usd == pytest.approx(-30.0)
    assert pnl.total_fee_usd == pytest.approx(0.4)
    assert pnl.net_realized_pnl_usd == pytest.approx(-30.4)
    assert pnl.ending_unrealized_pnl_usd == pytest.approx(60.0)
    assert pnl.ending_equity_usd == pytest.approx(1_029.6)
    assert pnl.return_fraction == pytest.approx(0.0296)


def test_build_replay_pnl_ignores_non_fill_events_and_keeps_zero_pnl() -> None:
    event = EventEnvelope(
        event_id="reject-event",
        event_type=EventType.ORDER_REJECTED,
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        source="execution_engine",
        run_id="inventory-validation",
        strategy_id="inventory-test",
        symbol="BTCUSDT",
        mode=Mode.PAPER,
        payload={
            "intent": {
                "intent_id": "intent-1",
                "proposal_id": "proposal-1",
            },
            "reject_reason": "min_notional_not_met",
            "estimated_slippage_bps": 0.0,
        },
    )

    pnl = build_replay_pnl(
        [event],
        final_close_by_symbol={"BTCUSDT": 120.0},
        starting_equity_usd=500.0,
    )

    assert pnl.gross_realized_pnl_usd == 0.0
    assert pnl.total_fee_usd == 0.0
    assert pnl.net_realized_pnl_usd == 0.0
    assert pnl.ending_unrealized_pnl_usd == 0.0
    assert pnl.ending_equity_usd == 500.0
    assert pnl.return_fraction == 0.0


def test_replay_journal_empty_path_keeps_zero_pnl_behavior(tmp_path: Path) -> None:
    journal_path = tmp_path / "empty.jsonl"
    journal_path.write_text("", encoding="utf-8")

    replay_result = replay_journal(
        journal_path,
        replay_path=FIXTURES_DIR / "paper_candles_high_volatility.jsonl",
        starting_equity_usd=1_000.0,
    )

    assert replay_result.scorecard.run_id == "empty"
    assert replay_result.scorecard.event_count == 0
    assert replay_result.pnl is not None
    assert replay_result.pnl.gross_realized_pnl_usd == 0.0
    assert replay_result.pnl.total_fee_usd == 0.0
    assert replay_result.pnl.net_realized_pnl_usd == 0.0
    assert replay_result.pnl.ending_unrealized_pnl_usd == 0.0
    assert replay_result.pnl.ending_equity_usd == 1_000.0
    assert replay_result.pnl.return_fraction == 0.0


@pytest.mark.parametrize(
    (
        "fixture_name",
        "run_id",
        "equity_usd",
        "policy_overrides",
        "expected_fill_event_count",
        "expected_partial_fill_count",
        "expected_order_reject_count",
        "expected_halt_count",
        "expect_unrealized_non_zero",
    ),
    [
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-paper-run",
            100_000.0,
            None,
            2,
            1,
            0,
            0,
            True,
        ),
        (
            "paper_candles_mean_reversion_short.jsonl",
            "mean-reversion-paper-run",
            100_000.0,
            None,
            2,
            1,
            0,
            0,
            True,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-reject-low-equity-paper-run",
            1.0,
            None,
            0,
            0,
            1,
            0,
            False,
        ),
        (
            "paper_candles_breakout_long.jsonl",
            "breakout-halt-drawdown-zero-paper-run",
            100_000.0,
            {"max_drawdown_fraction": 0.0},
            0,
            0,
            0,
            1,
            False,
        ),
        (
            "paper_candles_high_volatility.jsonl",
            "high-vol-no-signal-paper-run",
            100_000.0,
            None,
            0,
            0,
            0,
            0,
            False,
        ),
    ],
)
def test_paper_run_pnl_surface_is_deterministic_and_reconciles(
    tmp_path: Path,
    fixture_name: str,
    run_id: str,
    equity_usd: float,
    policy_overrides: dict[str, object] | None,
    expected_fill_event_count: int,
    expected_partial_fill_count: int,
    expected_order_reject_count: int,
    expected_halt_count: int,
    expect_unrealized_non_zero: bool,
) -> None:
    result = run_paper_replay(
        FIXTURES_DIR / fixture_name,
        settings=_paper_settings_for(tmp_path, policy_overrides=policy_overrides),
        run_id=run_id,
        equity_usd=equity_usd,
    )

    pnl = result.pnl
    assert pnl.starting_equity_usd == equity_usd
    assert result.scorecard.fill_event_count == expected_fill_event_count
    assert result.scorecard.partial_fill_intent_count == expected_partial_fill_count
    assert result.scorecard.order_reject_count == expected_order_reject_count
    assert result.scorecard.halt_count == expected_halt_count
    assert pnl.total_fee_usd == result.scorecard.total_fee_usd
    assert pnl.net_realized_pnl_usd == pytest.approx(pnl.gross_realized_pnl_usd - pnl.total_fee_usd)
    assert pnl.ending_equity_usd == pytest.approx(
        pnl.starting_equity_usd + pnl.net_realized_pnl_usd + pnl.ending_unrealized_pnl_usd
    )
    assert pnl.return_fraction == pytest.approx(
        (pnl.ending_equity_usd - pnl.starting_equity_usd) / pnl.starting_equity_usd
    )

    if expect_unrealized_non_zero:
        assert pnl.ending_unrealized_pnl_usd != 0.0
    else:
        assert pnl.gross_realized_pnl_usd == 0.0
        assert pnl.total_fee_usd == 0.0
        assert pnl.net_realized_pnl_usd == 0.0
        assert pnl.ending_unrealized_pnl_usd == 0.0
        assert pnl.ending_equity_usd == pnl.starting_equity_usd
        assert pnl.return_fraction == 0.0
