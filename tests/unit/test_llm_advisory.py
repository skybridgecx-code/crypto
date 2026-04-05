import json
from pathlib import Path

import pytest
from crypto_agent.config import load_settings
from crypto_agent.evaluation.replay import replay_journal
from crypto_agent.events.journal import AppendOnlyJournal, build_execution_events
from crypto_agent.execution.models import PaperExecutionConfig
from crypto_agent.execution.simulator import PaperExecutionSimulator
from crypto_agent.features.pipeline import build_feature_snapshot
from crypto_agent.llm.analyst import LLMOutputError, build_analyst_context, parse_analyst_output
from crypto_agent.llm.prompts import build_analyst_prompt_payload, build_review_prompt_payload
from crypto_agent.llm.summarizer import parse_review_output
from crypto_agent.market_data.replay import load_candle_replay
from crypto_agent.portfolio.positions import PortfolioState
from crypto_agent.regime.rules import classify_regime
from crypto_agent.risk.checks import evaluate_trade_proposal
from crypto_agent.signals.breakout import generate_breakout_proposal

FIXTURES_DIR = Path("tests/fixtures")


def _replay_result(tmp_path: Path):
    settings = load_settings(Path("config/paper.yaml"))
    candles = load_candle_replay(FIXTURES_DIR / "paper_candles_breakout_long.jsonl")
    features = build_feature_snapshot(candles, lookback_periods=4)
    regime = classify_regime(features)
    proposal = generate_breakout_proposal(candles, features, regime)
    assert proposal is not None
    portfolio = PortfolioState(
        equity_usd=100_000.0,
        available_cash_usd=100_000.0,
        daily_realized_pnl_usd=0.0,
    )
    risk_result = evaluate_trade_proposal(proposal, portfolio, settings)
    simulator = PaperExecutionSimulator(
        PaperExecutionConfig(partial_fill_notional_threshold=1_000.0)
    )
    report = simulator.submit(risk_result)
    journal = AppendOnlyJournal(tmp_path / "llm_replay.jsonl")
    journal.append_many(build_execution_events("run-llm", proposal, risk_result, report))
    return replay_journal(tmp_path / "llm_replay.jsonl")


def test_parse_analyst_output_accepts_valid_json(tmp_path: Path) -> None:
    replay_result = _replay_result(tmp_path)
    context = build_analyst_context(replay_result)
    raw = json.dumps(
        {
            "authority": "advisory_only",
            "run_id": replay_result.scorecard.run_id,
            "overall_summary": "One proposal was approved and completed via partial fill.",
            "assumptions": ["Replay context is complete for this run."],
            "candidates": [
                {
                    "proposal_id": context["proposals"][0]["proposal_id"],
                    "rank": 1,
                    "summary": "Breakout proposal remained the highest-quality candidate.",
                    "confidence": 0.74,
                    "invalidation_reason": "Breakout failed to sustain follow-through.",
                    "evidence_event_types": ["trade.proposal.created", "order.filled"],
                }
            ],
            "warnings": [],
        }
    )

    advisory = parse_analyst_output(raw)

    assert advisory.authority == "advisory_only"
    assert advisory.candidates[0].proposal_id == context["proposals"][0]["proposal_id"]


def test_parse_analyst_output_fails_on_malformed_json() -> None:
    with pytest.raises(LLMOutputError, match="valid JSON"):
        parse_analyst_output("{not-json}")


def test_parse_analyst_output_fails_on_missing_required_fields() -> None:
    raw = json.dumps({"authority": "advisory_only", "run_id": "run-x"})

    with pytest.raises(LLMOutputError, match="schema validation"):
        parse_analyst_output(raw)


def test_parse_review_output_fails_if_authority_is_not_advisory() -> None:
    raw = json.dumps(
        {
            "authority": "execute",
            "run_id": "run-x",
            "summary": "Unsafe output",
            "findings": [],
            "policy_violations": [],
            "next_checks": [],
        }
    )

    with pytest.raises(LLMOutputError, match="schema validation|exceed advisory-only authority"):
        parse_review_output(raw)


def test_prompt_payloads_include_strict_response_schemas(tmp_path: Path) -> None:
    replay_result = _replay_result(tmp_path)

    analyst_payload = build_analyst_prompt_payload(replay_result)
    review_payload = build_review_prompt_payload(replay_result)

    assert "response_schema" in analyst_payload
    assert "response_schema" in review_payload
    assert analyst_payload["context"]["run_id"] == replay_result.scorecard.run_id
    assert review_payload["context"]["scorecard"]["run_id"] == replay_result.scorecard.run_id
