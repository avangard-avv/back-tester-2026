"""Data adapters: produce raw L3-like events that engines ingest.

Engines consume the iterable yielded by an :class:`IDataAdapter` and
internally maintain an order book.  Two implementations are shipped:

* :class:`SyntheticDataAdapter` — generates a deterministic GBM stream of
  L3 ADD/CANCEL/TRADE events with no external data required.  This is
  what makes the end-to-end mock pipeline self-contained.
* :class:`NdjsonDataAdapterTemplate` — stub for HW1/HW2's NDJSON L3
  reader.  Will be filled in once the historical data format is finalised.
"""

from __future__ import annotations

import abc
import logging
from collections.abc import Iterable, Iterator
from typing import Any

import numpy as np

from python_wrapper_interface.engines._raw_events import (
    RawAdd,
    RawCancel,
    RawTradeTick,
    _new_header,
)

logger = logging.getLogger(__name__)


RawL3Event = RawAdd | RawCancel | RawTradeTick


class IDataAdapter(abc.ABC):
    """Source of raw L3-like events consumed by a backtest engine.

    The engine drives the iterator one event at a time inside ``step()``.
    """

    @abc.abstractmethod
    def load(
        self,
        data_path: str | None = None,
        date_range: tuple[str, str] | None = None,
    ) -> None:
        """Set up the data source.

        Parameters
        ----------
        data_path : str | None
            Path to a file or directory (implementation-defined).
        date_range : tuple[str, str] | None
            Optional ``(start, end)`` ISO-8601 strings.
        """

    @abc.abstractmethod
    def __iter__(self) -> Iterator[RawL3Event]:
        """Yield raw L3 events until exhausted."""

    def instruments(self) -> dict[str, int]:
        """Return the ``{symbol: instrument_id}`` map the engine should use.

        Returns
        -------
        dict[str, int]
        """
        return {}


# ---------------------------------------------------------------------------
# Synthetic GBM data adapter
# ---------------------------------------------------------------------------


_DEFAULT_INSTRUMENT_MAP: dict[str, int] = {"EURUSD_F_202506": 1001}


class SyntheticDataAdapter(IDataAdapter):
    """Generate a deterministic stream of L3 events from a GBM walk.

    The price path is a discretised geometric Brownian motion.  Each tick
    produces one L3 event with the following mix:

    * 70% :class:`RawAdd` — a fresh order at best bid or best ask.
    * 20% :class:`RawCancel` — cancel a previously added order.
    * 10% :class:`RawTradeTick` — a trade against the top of book.

    Parameters
    ----------
    instruments : dict[str, int] | None
        ``{symbol: instrument_id}`` map. Defaults to a single instrument
        ``{"EURUSD_F_202506": 1001}``.
    n_events : int
        Total number of L3 events to emit. Default ``10_000``.
    base_price : float
        Starting mid price in real units, e.g. ``1.10``.
    volatility : float
        Annualised volatility for the GBM model.
    spread_ticks : int
        Half-spread expressed in price ticks (where one tick is
        ``1 / PRICE_SCALE`` units of price).
    seed : int | None
        RNG seed for reproducibility.
    """

    def __init__(
        self,
        instruments: dict[str, int] | None = None,
        n_events: int = 10_000,
        base_price: float = 1.10,
        volatility: float = 0.10,
        spread_ticks: int = 2,
        seed: int | None = 42,
    ) -> None:
        self._instruments: dict[str, int] = dict(
            instruments if instruments is not None else _DEFAULT_INSTRUMENT_MAP
        )
        self._n_events = int(n_events)
        self._base_price = float(base_price)
        self._volatility = float(volatility)
        self._spread_ticks = int(spread_ticks)
        self._seed = seed
        self._events: list[RawL3Event] = []
        self._loaded = False

    def instruments(self) -> dict[str, int]:
        return dict(self._instruments)

    def load(
        self,
        data_path: str | None = None,
        date_range: tuple[str, str] | None = None,
    ) -> None:
        """Generate the entire event stream up front (deterministic)."""
        logger.debug(
            "SyntheticDataAdapter.load(n_events=%d, seed=%s)",
            self._n_events,
            self._seed,
        )
        rng = np.random.default_rng(self._seed)
        symbols = list(self._instruments.keys())
        n = self._n_events

        # GBM parameters: one event per ~100 ms.
        dt = (100e-3) / (252 * 24 * 3600)
        vol = self._volatility
        log_returns = rng.normal(0.0, vol * np.sqrt(dt), size=(n, len(symbols)))
        log_paths = np.cumsum(log_returns, axis=0)
        mid_paths = self._base_price * np.exp(log_paths)  # shape (n, S)

        base_ts_micros = 1_700_000_000_000_000  # 2023-11-14 ish, in micros
        interval_micros = 100_000  # 100 ms

        event_types = rng.choice(
            ["add", "cancel", "trade"],
            size=n,
            p=[0.70, 0.20, 0.10],
        )
        sides = rng.choice(["B", "S"], size=n)
        symbol_idx = rng.integers(0, len(symbols), size=n)
        qtys = rng.integers(1, 50, size=n).astype(int)

        scale_digits = 4  # matches PRICE_SCALE = 10_000

        events: list[RawL3Event] = []
        live_order_ids: dict[str, list[int]] = {s: [] for s in symbols}
        next_order_id = 1

        for i in range(n):
            sym = symbols[int(symbol_idx[i])]
            mid = float(mid_paths[i, int(symbol_idx[i])])
            mid_scaled = int(round(mid * 10 ** scale_digits))
            half = self._spread_ticks
            best_bid = mid_scaled - half
            best_ask = mid_scaled + half
            ts = base_ts_micros + i * interval_micros
            header = _new_header(sequence=i + 1)
            etype = event_types[i]
            side = sides[i]

            if etype == "add":
                px = best_bid if side == "B" else best_ask
                oid = next_order_id
                next_order_id += 1
                live_order_ids[sym].append(oid)
                events.append(
                    RawAdd(
                        instrument_symbol=sym,
                        ts_micros=int(ts),
                        header=header,
                        order_id=oid,
                        side_char=str(side),
                        px_mantissa=int(px),
                        px_exp=-scale_digits,
                        qty=int(qtys[i]),
                    )
                )
            elif etype == "cancel" and live_order_ids[sym]:
                idx = int(rng.integers(0, len(live_order_ids[sym])))
                oid = live_order_ids[sym].pop(idx)
                events.append(
                    RawCancel(
                        instrument_symbol=sym,
                        ts_micros=int(ts),
                        header=header,
                        order_id=oid,
                    )
                )
            else:
                # trade — or cancel fallback when no live orders to cancel
                px = best_ask if side == "B" else best_bid
                events.append(
                    RawTradeTick(
                        instrument_symbol=sym,
                        ts_micros=int(ts),
                        header=header,
                        px_mantissa=int(px),
                        px_exp=-scale_digits,
                        qty=int(qtys[i]),
                        side_char=str(side),
                    )
                )

        self._events = events
        self._loaded = True

    def __iter__(self) -> Iterator[RawL3Event]:
        if not self._loaded:
            self.load()
        return iter(self._events)

    def __len__(self) -> int:
        return len(self._events) if self._loaded else self._n_events


# ---------------------------------------------------------------------------
# NDJSON template — for HW1/HW2's historical-replay reader
# ---------------------------------------------------------------------------


class NdjsonDataAdapterTemplate(IDataAdapter):
    """Skeleton for a newline-delimited-JSON L3 reader.

    Copy this class, rename it to ``NdjsonDataAdapter`` and fill in
    :meth:`load` and :meth:`__iter__` using the HW1/HW2 NDJSON format
    described below.

    Notes
    -----
    Expected NDJSON line format (one JSON object per line)
        Each line has at minimum::

            {
              "ts_micros":         <int>,
              "seq":               <int>,
              "instrument_symbol": "<string>",
              "type":              "add" | "cancel" | "trade",
              "order_id":          <int>,        # add/cancel
              "side":              "B" | "S",    # add/trade
              "px_mantissa":       <int>,        # add/trade
              "px_exp":            <int>,        # add/trade
              "qty":               <int>         # add/trade
            }

        Files may be gzip-compressed (``.ndjson.gz``); the implementation
        should sniff the extension.  ``date_range`` filters lines by
        ``ts_micros``.

    Parameters
    ----------
    instruments : dict[str, int] | None
        ``{symbol: instrument_id}`` map.  May be empty — the adapter is
        expected to auto-discover symbols on first sight.
    """

    def __init__(self, instruments: dict[str, int] | None = None) -> None:
        self._instruments = dict(instruments or {})

    def instruments(self) -> dict[str, int]:
        return dict(self._instruments)

    def load(
        self,
        data_path: str | None = None,
        date_range: tuple[str, str] | None = None,
    ) -> None:
        """Open the NDJSON file(s) and prepare the event iterator.

        Notes
        -----
        Implementation outline
            1. Resolve ``data_path`` (file vs. directory glob).
            2. Open with ``gzip.open`` if the suffix is ``.gz``,
               ``open`` otherwise.
            3. Skip lines whose ``ts_micros`` falls outside ``date_range``.
            4. Auto-discover symbols not in ``self._instruments``.
        """
        raise NotImplementedError(
            "HW1/HW2 team: implement NDJSON parsing per the docstring."
        )

    def __iter__(self) -> Iterator[RawL3Event]:
        """Yield raw L3 events parsed from NDJSON.

        Notes
        -----
        Each line should be converted to one of :class:`RawAdd`,
        :class:`RawCancel`, or :class:`RawTradeTick` according to the
        ``type`` field.
        """
        raise NotImplementedError(
            "HW1/HW2 team: implement NDJSON parsing per the docstring."
        )


__all__ = [
    "IDataAdapter",
    "NdjsonDataAdapterTemplate",
    "RawL3Event",
    "SyntheticDataAdapter",
]
