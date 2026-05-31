"""Self-contained mock backtest engine that exercises the adapter layer.

End-to-end picture::

    IDataAdapter ── raw L3 ──▶ MockBacktestEngine
                                  │
                                  ▼  (raw BookUpdate / Trade / Fill)
                          IEventAdapter
                                  │
                                  ▼  (clean dataclasses)
                              Strategy
                                  │
                                  ▼  (clean Order)
                          IOrderAdapter
                                  │
                                  ▼  (raw dict command)
                          MockBacktestEngine (resting book)

Every value that crosses the engine ↔ strategy boundary passes through an
adapter; the strategy never sees a raw type and the engine never sees an
:class:`Order` directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterator

import pandas as pd

from python_wrapper_interface.adapters.data_adapter import (
    IDataAdapter,
    SyntheticDataAdapter,
)
from python_wrapper_interface.adapters.event_adapter import (
    IEventAdapter,
    MockEventAdapter,
)
from python_wrapper_interface.adapters.order_adapter import (
    IOrderAdapter,
    MockOrderAdapter,
)
from python_wrapper_interface.adapters.price import (
    decode_mantissa_exp,
    encode_mantissa_exp,
)
from python_wrapper_interface.engines._raw_events import (
    RawAdd,
    RawBookUpdate,
    RawCancel,
    RawFill,
    RawTrade,
    RawTradeTick,
    _new_header,
)
from python_wrapper_interface.interfaces import (
    IBacktestEngine,
    IMarketDataFeed,
    IOrderGateway,
)
from python_wrapper_interface.runner import ProgressInfo, Result
from python_wrapper_interface.strategy import Strategy
from python_wrapper_interface.types import (
    PRICE_SCALE,
    Order,
    OrderStatus,
    Side,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Engine-internal bookkeeping
# ---------------------------------------------------------------------------


@dataclass
class _InstrumentState:
    """Top-of-book maintained by the engine (scaled-int prices)."""

    bid_price: int = 0
    ask_price: int = 0
    bid_size: int = 0
    ask_size: int = 0
    seq_no: int = 0


@dataclass
class _RestingOrder:
    """A strategy-submitted order living in the engine's resting book.

    Stored as the *raw command dict* produced by :class:`IOrderAdapter`,
    plus the original ``Order`` for fill bookkeeping (PnL needs the
    enum-typed side).
    """

    raw_cmd: dict
    original: Order
    order_id: int
    status: OrderStatus = OrderStatus.ACKED
    filled_size: int = 0


# ---------------------------------------------------------------------------
# Gateway / feed inner classes
# ---------------------------------------------------------------------------


class _MockOrderGateway(IOrderGateway):
    """Routes clean Orders through the order adapter into the engine."""

    def __init__(self, engine: "MockBacktestEngine") -> None:
        self._engine = engine

    def send_order(self, order: Order) -> int:
        return self._engine._on_send_order(order)

    def cancel_order(self, client_order_id: int) -> None:
        self._engine._on_cancel_order(client_order_id)


class _MockMarketDataFeed(IMarketDataFeed):
    """Exposes top-of-book to the strategy in scaled-int form."""

    def __init__(self, engine: "MockBacktestEngine") -> None:
        self._engine = engine

    def best_bid(self, instrument_id: int) -> int | None:
        state = self._engine._instruments.get(instrument_id)
        if state is None or state.bid_price <= 0:
            return None
        return state.bid_price

    def best_ask(self, instrument_id: int) -> int | None:
        state = self._engine._instruments.get(instrument_id)
        if state is None or state.ask_price <= 0:
            return None
        return state.ask_price

    def subscribe(self, instrument_id: int) -> None:
        # No-op for the mock — all instruments produced by the data
        # adapter are automatically delivered.
        pass


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------


_SIDE_CHAR_TO_SIDE: dict[str, Side] = {"B": Side.BUY, "S": Side.SELL}


def _default_symbol_for(instrument_id: int) -> str:
    """Build a deterministic symbol for a bare integer instrument id."""
    return f"INSTR_{instrument_id}"


class MockBacktestEngine(IBacktestEngine):
    """Pure-Python engine that ingests raw L3 events and feeds a strategy.

    Parameters
    ----------
    data_adapter : IDataAdapter | None
        Source of raw L3 events.  Defaults to :class:`SyntheticDataAdapter`
        built from the convenience kwargs below.
    event_adapter : IEventAdapter | None
        Converts the engine's raw events to clean dataclasses.  Defaults
        to :class:`MockEventAdapter` initialised from the data adapter's
        instrument map.
    order_adapter : IOrderAdapter | None
        Converts clean :class:`Order` commands to raw engine commands.
        Defaults to :class:`MockOrderAdapter`.
    instrument_ids : list[int] | None
        Convenience: integer ids to back the default
        :class:`SyntheticDataAdapter`.  Ignored if ``data_adapter`` is
        provided.
    num_events : int
        Number of L3 events for the default data adapter.
    base_price : float
        Starting mid in real units for the default data adapter.
    spread_bps : float
        Retained for backwards compatibility — converted to
        ``spread_ticks`` internally.
    volatility : float
        Annualised volatility for the default data adapter.
    seed : int | None
        RNG seed for the default data adapter.
    """

    def __init__(
        self,
        data_adapter: IDataAdapter | None = None,
        event_adapter: IEventAdapter | None = None,
        order_adapter: IOrderAdapter | None = None,
        *,
        instrument_ids: list[int] | None = None,
        num_events: int = 10_000,
        base_price: float = 1.10,
        spread_bps: float = 2.0,
        volatility: float = 0.10,
        seed: int | None = 42,
    ) -> None:
        # Resolve the data adapter first; its instrument map drives the
        # event adapter's initial state.
        if data_adapter is None:
            ids = instrument_ids or [1001]
            symbol_map = {_default_symbol_for(i): i for i in ids}
            spread_ticks = max(1, int(base_price * spread_bps / 10_000 * PRICE_SCALE))
            data_adapter = SyntheticDataAdapter(
                instruments=symbol_map,
                n_events=num_events,
                base_price=base_price,
                volatility=volatility,
                spread_ticks=spread_ticks,
                seed=seed,
            )

        self._data_adapter: IDataAdapter = data_adapter
        self._instrument_map: dict[str, int] = data_adapter.instruments()
        # If the data adapter offers no map, allow the event adapter to
        # discover symbols lazily.
        self._event_adapter: IEventAdapter = (
            event_adapter or MockEventAdapter(self._instrument_map)
        )
        self._order_adapter: IOrderAdapter = order_adapter or MockOrderAdapter()

        self._gateway = _MockOrderGateway(self)
        self._feed = _MockMarketDataFeed(self)
        self._strategy: Strategy | None = None

        self._instruments: dict[int, _InstrumentState] = {}
        # Seed states for the symbols we know up front so best_bid/ask
        # return None until the first ADD lands rather than tripping a
        # KeyError.
        for sym, iid in self._instrument_map.items():
            self._instruments[iid] = _InstrumentState()

        self._resting_orders: dict[int, _RestingOrder] = {}
        self._next_exch_order_id: int = 1

        self._fills: list[dict[str, object]] = []
        self._order_log: list[dict[str, object]] = []
        self._pnl_snapshots: list[dict[str, object]] = []
        self._position: dict[int, int] = {iid: 0 for iid in self._instruments}
        self._realised_pnl: float = 0.0

        self._progress = ProgressInfo()
        self._by_instrument: dict[int, dict[str, int]] = {
            iid: {"sent": 0, "filled": 0, "rejected": 0}
            for iid in self._instruments
        }

        self._data_iter: Iterator | None = None
        self._event_idx: int = 0
        self._total_events_hint: int = 0
        self._loaded: bool = False

    # -- IBacktestEngine ------------------------------------------------------

    def load(
        self,
        data_path: str | None = None,
        date_range: tuple[str, str] | None = None,
    ) -> None:
        self._data_adapter.load(data_path, date_range)
        # Refresh the symbol map and instrument states in case the data
        # adapter discovered new instruments during ``load()``.
        self._instrument_map = self._data_adapter.instruments() or self._instrument_map
        for sym, iid in self._instrument_map.items():
            self._instruments.setdefault(iid, _InstrumentState())
            self._position.setdefault(iid, 0)
            self._by_instrument.setdefault(
                iid, {"sent": 0, "filled": 0, "rejected": 0}
            )
        try:
            self._total_events_hint = len(self._data_adapter)  # type: ignore[arg-type]
        except TypeError:
            self._total_events_hint = 0
        self._loaded = True

    def register_strategy(self, strategy: Strategy) -> None:
        self._strategy = strategy
        if getattr(strategy, "_ctx", None) is None:
            # Auto-bind so tests / scripts that call register_strategy
            # directly (i.e. without BacktestRunner) still work.
            from python_wrapper_interface.strategy import StrategyContext

            strategy._bind(StrategyContext(gateway=self._gateway, feed=self._feed))

    def order_gateway(self) -> IOrderGateway:
        return self._gateway

    def market_data_feed(self) -> IMarketDataFeed:
        return self._feed

    def step(self) -> bool:
        if not self._loaded:
            self.load()
        if self._data_iter is None:
            self._data_iter = iter(self._data_adapter)

        try:
            raw_l3 = next(self._data_iter)
        except StopIteration:
            return False

        self._event_idx += 1
        if self._total_events_hint:
            self._progress.percent_done = min(
                1.0, self._event_idx / self._total_events_hint
            )
        self._progress.last_timestamp_ns = raw_l3.ts_micros * 1_000

        sym = raw_l3.instrument_symbol
        if sym not in self._instrument_map:
            self._instrument_map[sym] = (max(self._instruments) + 1) if self._instruments else 1
            iid = self._instrument_map[sym]
            self._instruments[iid] = _InstrumentState()
            self._position[iid] = 0
            self._by_instrument[iid] = {"sent": 0, "filled": 0, "rejected": 0}
        iid = self._instrument_map[sym]
        state = self._instruments[iid]
        state.seq_no += 1

        if isinstance(raw_l3, RawAdd):
            self._apply_add(state, raw_l3)
            self._emit_book_update(state, raw_l3.ts_micros, sym)
            self._check_resting_fills(iid, state, raw_l3.ts_micros)
        elif isinstance(raw_l3, RawCancel):
            # Cancels of non-top orders don't move the book; just emit a
            # refreshed book update so the strategy still sees the tick.
            self._emit_book_update(state, raw_l3.ts_micros, sym)
        elif isinstance(raw_l3, RawTradeTick):
            self._emit_trade(state, raw_l3, sym)
            self._check_resting_fills(iid, state, raw_l3.ts_micros)
        else:
            logger.warning("unknown raw L3 event type: %r", type(raw_l3))

        return True

    def progress(self) -> ProgressInfo:
        self._progress.current_pnl = self._realised_pnl
        self._progress.by_instrument = {
            k: dict(v) for k, v in self._by_instrument.items()
        }
        return self._progress

    def build_result(self) -> Result:
        if self._pnl_snapshots:
            pnl_df = pd.DataFrame(self._pnl_snapshots)
        else:
            pnl_df = pd.DataFrame(columns=["timestamp_ns", "cumulative_pnl"])

        if self._fills:
            fills_df = pd.DataFrame(self._fills)
        else:
            fills_df = pd.DataFrame(
                columns=[
                    "order_id", "client_order_id", "instrument_id",
                    "timestamp_ns", "side", "fill_price", "fill_size",
                    "mid_price",
                ]
            )

        if self._order_log:
            order_log_df = pd.DataFrame(self._order_log)
        else:
            order_log_df = pd.DataFrame(
                columns=[
                    "client_order_id", "order_id", "instrument_id",
                    "side", "price", "size", "status", "timestamp_ns",
                ]
            )

        return Result(
            pnl_series=pnl_df,
            fills_df=fills_df,
            order_log_df=order_log_df,
        )

    # -- internal: book maintenance ------------------------------------------

    @staticmethod
    def _apply_add(state: _InstrumentState, raw_add: RawAdd) -> None:
        px = decode_mantissa_exp(raw_add.px_mantissa, raw_add.px_exp)
        if raw_add.side_char == "B":
            if state.bid_price == 0 or px >= state.bid_price:
                state.bid_price = px
                state.bid_size = raw_add.qty
        else:
            if state.ask_price == 0 or px <= state.ask_price:
                state.ask_price = px
                state.ask_size = raw_add.qty

    def _emit_book_update(
        self,
        state: _InstrumentState,
        ts_micros: int,
        sym: str,
    ) -> None:
        bid_m, bid_e = encode_mantissa_exp(state.bid_price)
        ask_m, ask_e = encode_mantissa_exp(state.ask_price)
        raw_bu = RawBookUpdate(
            instrument_symbol=sym,
            ts_micros=ts_micros,
            header=_new_header(state.seq_no),
            bid_px_mantissa=bid_m,
            bid_px_exp=bid_e,
            bid_size=state.bid_size,
            ask_px_mantissa=ask_m,
            ask_px_exp=ask_e,
            ask_size=state.ask_size,
        )
        clean = self._event_adapter.to_book_update(raw_bu)
        if self._strategy is not None:
            self._strategy.on_book_update(clean)

    def _emit_trade(
        self,
        state: _InstrumentState,
        raw_tick: RawTradeTick,
        sym: str,
    ) -> None:
        raw_trade = RawTrade(
            instrument_symbol=sym,
            ts_micros=raw_tick.ts_micros,
            header=_new_header(state.seq_no),
            px_mantissa=raw_tick.px_mantissa,
            px_exp=raw_tick.px_exp,
            qty=raw_tick.qty,
            side_char=raw_tick.side_char,
        )
        clean = self._event_adapter.to_trade(raw_trade)
        if self._strategy is not None:
            self._strategy.on_trade(clean)

    # -- internal: order handling --------------------------------------------

    def _on_send_order(self, order: Order) -> int:
        raw_cmd = self._order_adapter.to_engine_new_order(order)
        if not isinstance(raw_cmd, dict) or raw_cmd.get("op") != "new":
            raise ValueError(
                f"MockBacktestEngine expects dict-shaped 'new' commands "
                f"from the order adapter; got {raw_cmd!r}"
            )
        oid = self._next_exch_order_id
        self._next_exch_order_id += 1
        rec = _RestingOrder(
            raw_cmd=raw_cmd,
            original=order,
            order_id=oid,
        )
        self._resting_orders[order.client_order_id] = rec

        self._progress.orders_sent += 1
        stats = self._by_instrument.setdefault(
            order.instrument_id, {"sent": 0, "filled": 0, "rejected": 0}
        )
        stats["sent"] += 1

        self._order_log.append({
            "client_order_id": order.client_order_id,
            "order_id": oid,
            "instrument_id": order.instrument_id,
            "side": order.side.name,
            "price": order.price,
            "size": order.size,
            "status": OrderStatus.ACKED.value,
            "timestamp_ns": self._progress.last_timestamp_ns,
        })

        # Try to fill immediately against the current book.
        state = self._instruments.get(order.instrument_id)
        if state is not None:
            self._try_fill(rec, state, self._progress.last_timestamp_ns // 1_000)

        return order.client_order_id

    def _on_cancel_order(self, client_order_id: int) -> None:
        raw_cmd = self._order_adapter.to_engine_cancel(client_order_id)
        if not isinstance(raw_cmd, dict) or raw_cmd.get("op") != "cancel":
            raise ValueError(
                f"MockBacktestEngine expects dict-shaped 'cancel' commands "
                f"from the order adapter; got {raw_cmd!r}"
            )
        rec = self._resting_orders.get(client_order_id)
        if rec is None:
            return
        if rec.status in (OrderStatus.ACKED, OrderStatus.PARTIALLY_FILLED):
            rec.status = OrderStatus.CANCELLED
            self._progress.orders_cancelled += 1

    def _check_resting_fills(
        self,
        instrument_id: int,
        state: _InstrumentState,
        ts_micros: int,
    ) -> None:
        for rec in list(self._resting_orders.values()):
            if (
                rec.original.instrument_id == instrument_id
                and rec.status in (OrderStatus.ACKED, OrderStatus.PARTIALLY_FILLED)
            ):
                self._try_fill(rec, state, ts_micros)

    def _try_fill(
        self,
        rec: _RestingOrder,
        state: _InstrumentState,
        ts_micros: int,
    ) -> None:
        order = rec.original
        crosses = False
        if order.side == Side.BUY and state.ask_price > 0:
            crosses = order.price >= state.ask_price
            fill_price = state.ask_price
        elif order.side == Side.SELL and state.bid_price > 0:
            crosses = order.price <= state.bid_price
            fill_price = state.bid_price
        else:
            return

        if not crosses:
            return

        fill_size = order.size - rec.filled_size
        if fill_size <= 0:
            return
        rec.filled_size += fill_size
        rec.status = OrderStatus.FILLED

        mid = (state.bid_price + state.ask_price) // 2 if state.bid_price and state.ask_price else fill_price
        sign = 1 if order.side == Side.BUY else -1
        self._position.setdefault(order.instrument_id, 0)
        self._position[order.instrument_id] += sign * fill_size
        pnl_change = -sign * fill_price * fill_size / PRICE_SCALE
        self._realised_pnl += pnl_change

        self._progress.orders_filled += 1
        stats = self._by_instrument.setdefault(
            order.instrument_id, {"sent": 0, "filled": 0, "rejected": 0}
        )
        stats["filled"] += 1

        # Emit a RawFill, route through event_adapter, deliver clean Fill.
        sym = next(
            (s for s, i in self._instrument_map.items() if i == order.instrument_id),
            _default_symbol_for(order.instrument_id),
        )
        fill_m, fill_e = encode_mantissa_exp(fill_price)
        raw_fill = RawFill(
            exch_order_id=rec.order_id,
            cl_ord_id=order.client_order_id,
            instrument_symbol=sym,
            ts_micros=ts_micros,
            header=_new_header(state.seq_no),
            side_char="B" if order.side == Side.BUY else "S",
            px_mantissa=fill_m,
            px_exp=fill_e,
            qty=fill_size,
        )
        clean_fill = self._event_adapter.to_fill(raw_fill)

        self._fills.append({
            "order_id": rec.order_id,
            "client_order_id": order.client_order_id,
            "instrument_id": order.instrument_id,
            "timestamp_ns": clean_fill.timestamp_ns,
            "side": order.side.name,
            "fill_price": fill_price,
            "fill_size": fill_size,
            "mid_price": mid,
        })

        self._pnl_snapshots.append({
            "timestamp_ns": clean_fill.timestamp_ns,
            "cumulative_pnl": self._realised_pnl,
        })

        if self._strategy is not None:
            self._strategy.on_fill(clean_fill)
