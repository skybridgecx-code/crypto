from __future__ import annotations

from pathlib import Path

import pytest

from crypto_agent.cli.main import run_paper_replay
from crypto_agent.config import load_settings

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
