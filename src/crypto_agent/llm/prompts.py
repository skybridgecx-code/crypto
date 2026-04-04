from __future__ import annotations

from typing import Any

from crypto_agent.evaluation.models import ReplayResult
from crypto_agent.llm.analyst import (
    AnalystAdvisory,
    build_analyst_context,
)
from crypto_agent.llm.summarizer import ReviewSummary

ANALYST_SYSTEM_PROMPT = """You are the market analyst for a controlled crypto trading system.
Your job is to turn structured replay and evaluation inputs into a concise research memo
and ranked candidate review.
You do not place trades.
You do not change risk or policy decisions.
You do not invent missing facts.

Rules:
- Use only the provided structured inputs.
- Stay advisory_only.
- Return valid JSON only.
- Match the provided schema exactly.
- If the context is incomplete, say so in warnings.
"""

REVIEW_SYSTEM_PROMPT = """You are the post-trade reviewer for a controlled crypto trading system.
Your job is to summarize whether the system followed its own process.
You do not override risk or execution.
You do not invent missing facts.

Rules:
- Use only the provided structured inputs.
- Stay advisory_only.
- Return valid JSON only.
- Match the provided schema exactly.
- Focus on process quality, not hype or speculation.
"""


def build_analyst_prompt_payload(replay_result: ReplayResult) -> dict[str, Any]:
    return {
        "system_prompt": ANALYST_SYSTEM_PROMPT,
        "response_schema": AnalystAdvisory.model_json_schema(),
        "context": build_analyst_context(replay_result),
    }


def build_review_prompt_payload(replay_result: ReplayResult) -> dict[str, Any]:
    return {
        "system_prompt": REVIEW_SYSTEM_PROMPT,
        "response_schema": ReviewSummary.model_json_schema(),
        "context": {
            "run_id": replay_result.scorecard.run_id,
            "scorecard": replay_result.scorecard.model_dump(mode="json"),
            "event_types": [event.event_type.value for event in replay_result.events],
        },
    }
