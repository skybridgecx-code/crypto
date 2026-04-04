from datetime import UTC, datetime

import pytest
from crypto_agent.enums import EventType, Mode
from crypto_agent.events.envelope import EventEnvelope


def test_event_envelope_normalizes_timezone_aware_timestamp() -> None:
    event = EventEnvelope(
        event_type=EventType.TRADE_PROPOSAL_CREATED,
        timestamp=datetime(2026, 4, 3, 12, 0, tzinfo=UTC),
        source="signal_engine",
        run_id="run-123",
        strategy_id="breakout_v1",
        symbol="BTCUSDT",
        mode=Mode.PAPER,
        payload={"confidence": 0.7},
    )

    assert event.timestamp == datetime(2026, 4, 3, 12, 0, tzinfo=UTC)
    assert event.payload["confidence"] == 0.7
    assert event.event_id
    assert event.event_type is EventType.TRADE_PROPOSAL_CREATED
    assert event.mode is Mode.PAPER


def test_event_envelope_rejects_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        EventEnvelope(
            event_type=EventType.TRADE_PROPOSAL_CREATED,
            timestamp=datetime(2026, 4, 3, 12, 0),
            source="signal_engine",
            run_id="run-123",
            mode=Mode.PAPER,
            payload={},
        )
