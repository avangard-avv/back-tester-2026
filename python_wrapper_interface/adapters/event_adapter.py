"""Event adapters: convert engine-internal "dirty" events to clean types.

This is the **anti-corruption layer** between the C++ engine (or any other
producer of raw events) and the strategy.  Strategies see only the clean
dataclasses from :mod:`python_wrapper_interface.types`; engines see only
their native message format.

The C++ team should look at :class:`MockEventAdapter` as the reference
implementation, then copy :class:`CppEventAdapterTemplate` and fill in the
``NotImplementedError`` bodies using their pybind11-bound struct fields.

The historical :class:`DefaultEventAdapter` and :class:`GroupTwoLegacyAdapter`
classes are kept for backwards compatibility with earlier tests and the
existing :class:`~python_wrapper_interface.engines.cpp_engine.CppBacktestEngine`
stub.
"""

from __future__ import annotations

import abc
from typing import Any

from python_wrapper_interface.adapters.price import decode_mantissa_exp
from python_wrapper_interface.types import (
    BookUpdate,
    Fill,
    Reject,
    Side,
    Trade,
)

_SIDE_STR_MAP: dict[str, Side] = {"B": Side.BUY, "S": Side.SELL}
_SIDE_INT_MAP: dict[int, Side] = {1: Side.BUY, 2: Side.SELL}

_MICROS_TO_NANOS: int = 1_000


class IEventAdapter(abc.ABC):
    """Maps engine-internal "dirty" events to clean Python dataclasses.

    Every method accepts the raw event object (whatever the producer emits)
    and returns the corresponding clean dataclass from
    :mod:`python_wrapper_interface.types`.
    """

    @abc.abstractmethod
    def to_book_update(self, raw: Any) -> BookUpdate:
        """Convert a raw book-update event.

        Parameters
        ----------
        raw : Any
            Engine-internal event object.

        Returns
        -------
        BookUpdate
        """

    @abc.abstractmethod
    def to_trade(self, raw: Any) -> Trade:
        """Convert a raw trade event.

        Parameters
        ----------
        raw : Any

        Returns
        -------
        Trade
        """

    @abc.abstractmethod
    def to_fill(self, raw: Any) -> Fill:
        """Convert a raw fill event.

        Parameters
        ----------
        raw : Any

        Returns
        -------
        Fill
        """

    @abc.abstractmethod
    def to_reject(self, raw: Any) -> Reject:
        """Convert a raw reject event.

        Parameters
        ----------
        raw : Any

        Returns
        -------
        Reject
        """


# ---------------------------------------------------------------------------
# Mock adapter — works against engines/_raw_events.py
# ---------------------------------------------------------------------------


class MockEventAdapter(IEventAdapter):
    """Reference implementation paired with :class:`MockBacktestEngine`.

    Performs the same kinds of conversions the C++ adapter will need:

    * ``ts_micros`` → ``timestamp_ns`` (multiply by 1000).
    * ``header.sequence`` → ``seq_no`` (flatten the nested header).
    * ``bid_px_mantissa`` / ``bid_px_exp`` → ``bid_price`` (decode).
    * ``side_char`` (``'B'``/``'S'``) → :class:`Side`.
    * ``instrument_symbol`` (str) → ``instrument_id`` (int) via the
      symbol map injected at construction.

    Parameters
    ----------
    instrument_map : dict[str, int]
        Maps human-readable symbols like ``"EURUSD_F_202506"`` to integer
        instrument identifiers.  The mapping is consulted lazily; missing
        symbols are auto-assigned a fresh id so the mock pipeline keeps
        running with no external configuration.
    """

    def __init__(self, instrument_map: dict[str, int]) -> None:
        self._map: dict[str, int] = dict(instrument_map)
        self._next_auto_id: int = max(self._map.values(), default=0) + 1

    def _resolve(self, symbol: str) -> int:
        iid = self._map.get(symbol)
        if iid is None:
            iid = self._next_auto_id
            self._next_auto_id += 1
            self._map[symbol] = iid
        return iid

    def to_book_update(self, raw: Any) -> BookUpdate:
        return BookUpdate(
            instrument_id=self._resolve(raw.instrument_symbol),
            timestamp_ns=raw.ts_micros * _MICROS_TO_NANOS,
            seq_no=raw.header.sequence,
            bid_price=decode_mantissa_exp(raw.bid_px_mantissa, raw.bid_px_exp),
            ask_price=decode_mantissa_exp(raw.ask_px_mantissa, raw.ask_px_exp),
            bid_size=raw.bid_size,
            ask_size=raw.ask_size,
        )

    def to_trade(self, raw: Any) -> Trade:
        return Trade(
            instrument_id=self._resolve(raw.instrument_symbol),
            timestamp_ns=raw.ts_micros * _MICROS_TO_NANOS,
            seq_no=raw.header.sequence,
            price=decode_mantissa_exp(raw.px_mantissa, raw.px_exp),
            size=raw.qty,
            aggressor_side=_SIDE_STR_MAP[raw.side_char],
        )

    def to_fill(self, raw: Any) -> Fill:
        return Fill(
            order_id=raw.exch_order_id,
            client_order_id=raw.cl_ord_id,
            instrument_id=self._resolve(raw.instrument_symbol),
            timestamp_ns=raw.ts_micros * _MICROS_TO_NANOS,
            side=_SIDE_STR_MAP[raw.side_char],
            fill_price=decode_mantissa_exp(raw.px_mantissa, raw.px_exp),
            fill_size=raw.qty,
        )

    def to_reject(self, raw: Any) -> Reject:
        return Reject(
            order_id=raw.exch_order_id,
            client_order_id=raw.cl_ord_id,
            instrument_id=self._resolve(raw.instrument_symbol),
            timestamp_ns=raw.ts_micros * _MICROS_TO_NANOS,
            reason=raw.reject_text,
        )


# ---------------------------------------------------------------------------
# C++ template — for the C++ team to fill in
# ---------------------------------------------------------------------------


class CppEventAdapterTemplate(IEventAdapter):
    """Skeleton for the C++ event adapter.

    Copy this class, rename it to ``CppEventAdapter``, and fill in the
    method bodies using your pybind11-bound struct fields.  See
    :class:`MockEventAdapter` for a working reference implementation that
    exercises the same kinds of conversions you will need.

    Notes
    -----
    Conventions in the project's interface contract
        * Prices: ``{mantissa, exponent}`` pairs — decode with
          :func:`python_wrapper_interface.adapters.price.decode_mantissa_exp`.
        * Timestamps: microseconds in C++, nanoseconds in Python — multiply
          by ``1000``.
        * Side: ``'B'``/``'S'`` strings in C++, :class:`Side` enum in
          Python.
        * Instrument: string symbols in C++, integer ids in Python — keep a
          ``dict[str, int]`` map.
    """

    def __init__(self, instrument_map: dict[str, int]) -> None:
        self._map = dict(instrument_map)

    def to_book_update(self, raw: Any) -> BookUpdate:
        """Convert a pybind11-bound C++ book-update struct.

        Expected C++ fields (rename as needed):
            * ``raw.instrument_symbol`` : ``std::string``
            * ``raw.ts_micros``         : ``int64_t``
            * ``raw.header.sequence``   : ``uint64_t``
            * ``raw.bid_px_mantissa``   : ``int64_t``
            * ``raw.bid_px_exp``        : ``int8_t``
            * ``raw.bid_size``          : ``uint32_t``
            * ``raw.ask_px_mantissa``   : ``int64_t``
            * ``raw.ask_px_exp``        : ``int8_t``
            * ``raw.ask_size``          : ``uint32_t``

        Returns
        -------
        BookUpdate
        """
        raise NotImplementedError(
            "C++ team / Group 2: implement using raw.{instrument_symbol, "
            "ts_micros, header.sequence, bid_px_mantissa, bid_px_exp, "
            "bid_size, ask_px_mantissa, ask_px_exp, ask_size}."
        )

    def to_trade(self, raw: Any) -> Trade:
        """Convert a pybind11-bound C++ trade struct.

        Expected C++ fields:
            * ``raw.instrument_symbol``
            * ``raw.ts_micros``
            * ``raw.header.sequence``
            * ``raw.px_mantissa`` / ``raw.px_exp``
            * ``raw.qty``
            * ``raw.side_char`` (``'B'``/``'S'``)

        Returns
        -------
        Trade
        """
        raise NotImplementedError(
            "C++ team / Group 2: implement using raw.{instrument_symbol, "
            "ts_micros, header.sequence, px_mantissa, px_exp, qty, side_char}."
        )

    def to_fill(self, raw: Any) -> Fill:
        """Convert a pybind11-bound C++ fill struct.

        Expected C++ fields:
            * ``raw.exch_order_id`` / ``raw.cl_ord_id``
            * ``raw.instrument_symbol``
            * ``raw.ts_micros``
            * ``raw.side_char``
            * ``raw.px_mantissa`` / ``raw.px_exp``
            * ``raw.qty``

        Returns
        -------
        Fill
        """
        raise NotImplementedError(
            "C++ team / Group 1: implement using raw.{exch_order_id, "
            "cl_ord_id, instrument_symbol, ts_micros, side_char, "
            "px_mantissa, px_exp, qty}."
        )

    def to_reject(self, raw: Any) -> Reject:
        """Convert a pybind11-bound C++ reject struct.

        Expected C++ fields:
            * ``raw.exch_order_id`` / ``raw.cl_ord_id``
            * ``raw.instrument_symbol``
            * ``raw.ts_micros``
            * ``raw.reject_text``

        Returns
        -------
        Reject
        """
        raise NotImplementedError(
            "C++ team / Group 1: implement using raw.{exch_order_id, "
            "cl_ord_id, instrument_symbol, ts_micros, reject_text}."
        )


# ---------------------------------------------------------------------------
# Backwards-compatible historical adapters (kept for existing tests)
# ---------------------------------------------------------------------------


class DefaultEventAdapter(IEventAdapter):
    """Direct 1:1 mapping — raw field names match clean field names."""

    def to_book_update(self, raw: Any) -> BookUpdate:
        return BookUpdate(
            instrument_id=raw.instrument_id,
            timestamp_ns=raw.timestamp_ns,
            seq_no=raw.seq_no,
            bid_price=raw.bid_price,
            ask_price=raw.ask_price,
            bid_size=raw.bid_size,
            ask_size=raw.ask_size,
        )

    def to_trade(self, raw: Any) -> Trade:
        return Trade(
            instrument_id=raw.instrument_id,
            timestamp_ns=raw.timestamp_ns,
            seq_no=raw.seq_no,
            price=raw.price,
            size=raw.size,
            aggressor_side=_SIDE_INT_MAP[raw.aggressor_side],
        )

    def to_fill(self, raw: Any) -> Fill:
        return Fill(
            order_id=raw.order_id,
            client_order_id=raw.client_order_id,
            instrument_id=raw.instrument_id,
            timestamp_ns=raw.timestamp_ns,
            side=_SIDE_INT_MAP[raw.side],
            fill_price=raw.fill_price,
            fill_size=raw.fill_size,
        )

    def to_reject(self, raw: Any) -> Reject:
        return Reject(
            order_id=raw.order_id,
            client_order_id=raw.client_order_id,
            instrument_id=raw.instrument_id,
            timestamp_ns=raw.timestamp_ns,
            reason=raw.reason,
        )


class GroupTwoLegacyAdapter(IEventAdapter):
    """Non-trivial mapping for an older Group 2 legacy message format.

    Demonstrates nested header extraction, side-character mapping, and
    ``{mantissa, exponent}`` price decoding.  Retained for compatibility
    with the original adapter test suite.
    """

    def to_book_update(self, raw: Any) -> BookUpdate:
        return BookUpdate(
            instrument_id=raw.instr,
            timestamp_ns=raw.header.ts_ns,
            seq_no=raw.header.sequence,
            bid_price=decode_mantissa_exp(raw.bid_mantissa, raw.bid_exp),
            ask_price=decode_mantissa_exp(raw.ask_mantissa, raw.ask_exp),
            bid_size=raw.bid_qty,
            ask_size=raw.ask_qty,
        )

    def to_trade(self, raw: Any) -> Trade:
        return Trade(
            instrument_id=raw.instr,
            timestamp_ns=raw.header.ts_ns,
            seq_no=raw.header.sequence,
            price=decode_mantissa_exp(raw.trade_mantissa, raw.trade_exp),
            size=raw.qty,
            aggressor_side=_SIDE_STR_MAP[raw.side_str],
        )

    def to_fill(self, raw: Any) -> Fill:
        return Fill(
            order_id=raw.exch_order_id,
            client_order_id=raw.cl_ord_id,
            instrument_id=raw.instr,
            timestamp_ns=raw.header.ts_ns,
            side=_SIDE_STR_MAP[raw.side_str],
            fill_price=decode_mantissa_exp(raw.px_mantissa, raw.px_exp),
            fill_size=raw.qty,
        )

    def to_reject(self, raw: Any) -> Reject:
        return Reject(
            order_id=raw.exch_order_id,
            client_order_id=raw.cl_ord_id,
            instrument_id=raw.instr,
            timestamp_ns=raw.header.ts_ns,
            reason=raw.reject_text,
        )


__all__ = [
    "CppEventAdapterTemplate",
    "DefaultEventAdapter",
    "GroupTwoLegacyAdapter",
    "IEventAdapter",
    "MockEventAdapter",
]
