from datetime import UTC, datetime

import pytest
from crypto_agent.events.envelope import EventEnvelope


def test_event_envelope_normalizes_timezone_aware_timestamp() -> None:
    event = EventEnvelope(
        event_type="trade.proposal.created",
        timestamp=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
        source="signal_engine",
        run_id="run-123",
        strategy_id="breakout_v1",
        symbol="BTCUSDT",
        mode="paper",
        payload={"confidence": 0.7},
    )

    assert event.timestamp == datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    assert event.payload["confidence"] == 0.7
    assert event.event_id


def test_event_envelope_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EventEnvelope(
            event_type="trade.proposal.created",
            timestamp=datetime(2026, 4, 3, 12, 0),
            source="signal_engine",
            run_id="run-123",
            mode="paper",
            payload={},
        )
