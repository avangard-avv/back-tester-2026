"""Domain types for the Python Strategy API.

All user-facing events and commands are represented as frozen dataclasses.
Price values use scaled-integer encoding (see ``PRICE_SCALE``).
"""

from __future__ import annotations

import enum
from dataclasses import dataclass

PRICE_SCALE: int = 10_000
"""Fixed scale factor: 1 price unit = 1 / PRICE_SCALE."""


class Side(enum.Enum):
    """Order / trade direction."""

    BUY = 1
    SELL = 2


class OrderStatus(enum.Enum):
    """Lifecycle state of an order."""

    PENDING = "PENDING"
    ACKED = "ACKED"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


# ---------------------------------------------------------------------------
# Market-data events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class BookUpdate:
    """Top-of-book snapshot pushed by the market-data feed.

    Parameters
    ----------
    instrument_id : int
        Eurex product identifier.
    timestamp_ns : int
        Nanoseconds since Unix epoch.
    seq_no : int
        Monotonic per-instrument sequence number.
    bid_price : int
        Best bid in scaled-integer encoding.
    ask_price : int
        Best ask in scaled-integer encoding.
    bid_size : int
        Size at best bid.
    ask_size : int
        Size at best ask.
    """

    instrument_id: int
    timestamp_ns: int
    seq_no: int
    bid_price: int
    ask_price: int
    bid_size: int
    ask_size: int


@dataclass(frozen=True, slots=True)
class Trade:
    """Exchange trade event.

    Parameters
    ----------
    instrument_id : int
        Eurex product identifier.
    timestamp_ns : int
        Nanoseconds since Unix epoch.
    seq_no : int
        Monotonic per-instrument sequence number.
    price : int
        Trade price in scaled-integer encoding.
    size : int
        Trade size.
    aggressor_side : Side
        Side of the aggressor.
    """

    instrument_id: int
    timestamp_ns: int
    seq_no: int
    price: int
    size: int
    aggressor_side: Side


# ---------------------------------------------------------------------------
# Order-management events
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Fill:
    """Execution report for a filled (or partially filled) order.

    Parameters
    ----------
    order_id : int
        Exchange-assigned order identifier.
    client_order_id : int
        Strategy-assigned identifier.
    instrument_id : int
        Eurex product identifier.
    timestamp_ns : int
        Nanoseconds since Unix epoch.
    side : Side
        Order direction.
    fill_price : int
        Execution price in scaled-integer encoding.
    fill_size : int
        Executed quantity.
    """

    order_id: int
    client_order_id: int
    instrument_id: int
    timestamp_ns: int
    side: Side
    fill_price: int
    fill_size: int


@dataclass(frozen=True, slots=True)
class Reject:
    """Order rejection report.

    Parameters
    ----------
    order_id : int
        Exchange-assigned order identifier (may be 0 if never acked).
    client_order_id : int
        Strategy-assigned identifier.
    instrument_id : int
        Eurex product identifier.
    timestamp_ns : int
        Nanoseconds since Unix epoch.
    reason : str
        Human-readable rejection reason.
    """

    order_id: int
    client_order_id: int
    instrument_id: int
    timestamp_ns: int
    reason: str


# ---------------------------------------------------------------------------
# Order command
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Order:
    """Outbound order command sent by the strategy.

    Parameters
    ----------
    instrument_id : int
        Eurex product identifier.
    side : Side
        BUY or SELL.
    price : int
        Limit price in scaled-integer encoding.
    size : int
        Order quantity.
    client_order_id : int
        Assigned by :class:`BacktestRunner` at send time.
    """

    instrument_id: int
    side: Side
    price: int
    size: int
    client_order_id: int = 0
