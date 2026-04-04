from __future__ import annotations

from enum import Enum


class Mode(str, Enum):
    RESEARCH_ONLY = "research_only"
    PAPER = "paper"
    LIMITED_LIVE = "limited_live"
    HALTED = "halted"


class EventType(str, Enum):
    MARKET_TICK_RECEIVED = "market.tick.received"
    MARKET_CANDLE_CLOSED = "market.candle.closed"
    FEATURES_COMPUTED = "features.computed"
    REGIME_UPDATED = "regime.updated"
    TRADE_PROPOSAL_CREATED = "trade.proposal.created"
    RISK_CHECK_COMPLETED = "risk.check.completed"
    POLICY_DECISION_MADE = "policy.decision.made"
    ORDER_INTENT_CREATED = "order.intent.created"
    ORDER_SUBMITTED = "order.submitted"
    ORDER_FILLED = "order.filled"
    ORDER_REJECTED = "order.rejected"
    POSITION_UPDATED = "position.updated"
    ALERT_RAISED = "alert.raised"
    KILL_SWITCH_ACTIVATED = "kill_switch.activated"
    REVIEW_PACKET_CREATED = "review.packet.created"


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"
    LIMIT = "limit"


class TimeInForce(str, Enum):
    GTC = "gtc"
    IOC = "ioc"
    FOK = "fok"


class PolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    HALT = "halt"


class LiquidityRole(str, Enum):
    MAKER = "maker"
    TAKER = "taker"


class FillStatus(str, Enum):
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
