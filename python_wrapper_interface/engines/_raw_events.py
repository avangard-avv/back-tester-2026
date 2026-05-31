"""C++-style "dirty" event shapes (private module).

These dataclasses imitate the messy structs that pybind11 will eventually
surface from the C++ engine.  They intentionally use **different** field
names, **microseconds** instead of nanoseconds, **single-character** side
codes and **string** instrument symbols so that the adapter layer has real
work to do.

The strategy code must never see these types — they live behind
``IEventAdapter`` / ``IOrderAdapter`` / ``IDataAdapter`` and are converted
into clean :mod:`python_wrapper_interface.types` dataclasses before they
cross the engine ↔ strategy boundary.

Notes
-----
Differences from the clean Python dataclasses
    * ``ts_micros`` instead of ``timestamp_ns`` — multiply by 1000.
    * ``header.sequence`` instead of flat ``seq_no``.
    * ``bid_px_mantissa`` / ``bid_px_exp`` instead of ``bid_price``.
    * ``side_char`` (``'B'``/``'S'``) instead of :class:`Side`.
    * ``instrument_symbol`` (string) instead of ``instrument_id`` (int).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from types import SimpleNamespace


def _new_header(sequence: int = 0) -> SimpleNamespace:
    """Build a nested header object (mimics pybind11 nested structs)."""
    return SimpleNamespace(sequence=sequence)


# ---------------------------------------------------------------------------
# Engine → strategy events (the "dirty" side of the adapter)
# ---------------------------------------------------------------------------


@dataclass
class RawBookUpdate:
    """C++-style top-of-book snapshot.

    Parameters
    ----------
    instrument_symbol : str
        String identifier, e.g. ``"EURUSD_F_202506"``.  Resolved to an
        integer ``instrument_id`` by the event adapter.
    ts_micros : int
        Microseconds since Unix epoch (adapter multiplies by 1000).
    header : SimpleNamespace
        Nested header carrying ``sequence`` (sequence number).
    bid_px_mantissa : int
        Mantissa component of the best bid price.
    bid_px_exp : int
        Exponent component of the best bid price.
    bid_size : int
        Size at best bid.
    ask_px_mantissa : int
    ask_px_exp : int
    ask_size : int
    side_char : str
        Unused for book updates (always ``'-'``); kept to mirror the C++
        union-style event struct.
    """

    instrument_symbol: str
    ts_micros: int
    header: SimpleNamespace
    bid_px_mantissa: int
    bid_px_exp: int
    bid_size: int
    ask_px_mantissa: int
    ask_px_exp: int
    ask_size: int
    side_char: str = "-"


@dataclass
class RawTrade:
    """C++-style trade print.

    Parameters
    ----------
    instrument_symbol : str
    ts_micros : int
    header : SimpleNamespace
    px_mantissa : int
    px_exp : int
    qty : int
        Trade size (renamed ``size`` → ``qty`` for ugliness).
    side_char : str
        Aggressor side ``'B'`` or ``'S'``.
    """

    instrument_symbol: str
    ts_micros: int
    header: SimpleNamespace
    px_mantissa: int
    px_exp: int
    qty: int
    side_char: str


@dataclass
class RawFill:
    """C++-style execution report.

    Parameters
    ----------
    exch_order_id : int
        Exchange-assigned order id (renamed ``order_id``).
    cl_ord_id : int
        Client order id (renamed ``client_order_id``).
    instrument_symbol : str
    ts_micros : int
    header : SimpleNamespace
    side_char : str
    px_mantissa : int
    px_exp : int
    qty : int
    """

    exch_order_id: int
    cl_ord_id: int
    instrument_symbol: str
    ts_micros: int
    header: SimpleNamespace
    side_char: str
    px_mantissa: int
    px_exp: int
    qty: int


@dataclass
class RawReject:
    """C++-style reject report.

    Parameters
    ----------
    exch_order_id : int
    cl_ord_id : int
    instrument_symbol : str
    ts_micros : int
    header : SimpleNamespace
    reject_text : str
        Renamed ``reason`` → ``reject_text``.
    """

    exch_order_id: int
    cl_ord_id: int
    instrument_symbol: str
    ts_micros: int
    header: SimpleNamespace
    reject_text: str


# ---------------------------------------------------------------------------
# Data-feed → engine events (raw L3 ticks emitted by IDataAdapter)
# ---------------------------------------------------------------------------


@dataclass
class RawAdd:
    """L3 ADD: a new resting order entered the book.

    Parameters
    ----------
    instrument_symbol : str
    ts_micros : int
    header : SimpleNamespace
    order_id : int
        Unique exchange-side identifier (separate from the strategy's
        ``client_order_id``).
    side_char : str
        ``'B'`` or ``'S'``.
    px_mantissa : int
    px_exp : int
    qty : int
    """

    instrument_symbol: str
    ts_micros: int
    header: SimpleNamespace
    order_id: int
    side_char: str
    px_mantissa: int
    px_exp: int
    qty: int


@dataclass
class RawCancel:
    """L3 CANCEL: an existing resting order was removed.

    Parameters
    ----------
    instrument_symbol : str
    ts_micros : int
    header : SimpleNamespace
    order_id : int
        Identifier of the order being cancelled.
    """

    instrument_symbol: str
    ts_micros: int
    header: SimpleNamespace
    order_id: int


@dataclass
class RawModify:
    """L3 MODIFY: an existing order's price or size changed.

    Parameters
    ----------
    instrument_symbol : str
    ts_micros : int
    header : SimpleNamespace
    order_id : int
    new_px_mantissa : int
    new_px_exp : int
    new_qty : int
    """

    instrument_symbol: str
    ts_micros: int
    header: SimpleNamespace
    order_id: int
    new_px_mantissa: int
    new_px_exp: int
    new_qty: int


@dataclass
class RawTradeTick:
    """L3 TRADE: a trade printed against the book.

    Distinguished from :class:`RawTrade` (which is what the *engine* emits
    to the strategy) because the L3 tick is what the *data feed* emits to
    the engine.  Same shape, but conceptually different stage.

    Parameters
    ----------
    instrument_symbol : str
    ts_micros : int
    header : SimpleNamespace
    px_mantissa : int
    px_exp : int
    qty : int
    side_char : str
        Aggressor side.
    maker_order_id : int
        Id of the resting order that got hit (0 if unknown).
    """

    instrument_symbol: str
    ts_micros: int
    header: SimpleNamespace
    px_mantissa: int
    px_exp: int
    qty: int
    side_char: str
    maker_order_id: int = 0


__all__ = [
    "RawAdd",
    "RawBookUpdate",
    "RawCancel",
    "RawFill",
    "RawModify",
    "RawReject",
    "RawTrade",
    "RawTradeTick",
    "_new_header",
]
