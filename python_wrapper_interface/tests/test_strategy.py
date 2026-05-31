"""Tests for python_wrapper_interface.strategy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from python_wrapper_interface.interfaces import IMarketDataFeed, IOrderGateway
from python_wrapper_interface.strategy import Strategy, StrategyContext
from python_wrapper_interface.types import BookUpdate, Fill, Order, Reject, Side, Trade


class _StubGateway(IOrderGateway):
    def __init__(self) -> None:
        self.sent: list[Order] = []
        self.cancelled: list[int] = []

    def send_order(self, order: Order) -> int:
        self.sent.append(order)
        return order.client_order_id

    def cancel_order(self, client_order_id: int) -> None:
        self.cancelled.append(client_order_id)


class _StubFeed(IMarketDataFeed):
    def __init__(self) -> None:
        self.bids: dict[int, int] = {1001: 11000}
        self.asks: dict[int, int] = {1001: 11002}

    def best_bid(self, instrument_id: int) -> int | None:
        return self.bids.get(instrument_id)

    def best_ask(self, instrument_id: int) -> int | None:
        return self.asks.get(instrument_id)

    def subscribe(self, instrument_id: int) -> None:
        pass


class _TestStrategy(Strategy):
    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.stopped = False
        self.updates: list[BookUpdate] = []
        self.trades: list[Trade] = []
        self.fills: list[Fill] = []
        self.rejects: list[Reject] = []

    def on_start(self) -> None:
        self.started = True

    def on_stop(self) -> None:
        self.stopped = True

    def on_book_update(self, update: BookUpdate) -> None:
        self.updates.append(update)

    def on_trade(self, trade: Trade) -> None:
        self.trades.append(trade)

    def on_fill(self, fill: Fill) -> None:
        self.fills.append(fill)

    def on_reject(self, reject: Reject) -> None:
        self.rejects.append(reject)


class TestStrategyUnbound:
    def test_send_order_raises_without_context(self) -> None:
        s = _TestStrategy()
        with pytest.raises(RuntimeError, match="not bound"):
            s.send_order(1001, Side.BUY, 11000, 10)

    def test_best_bid_raises_without_context(self) -> None:
        s = _TestStrategy()
        with pytest.raises(RuntimeError, match="not bound"):
            s.best_bid(1001)


class TestStrategyBound:
    def setup_method(self) -> None:
        self.gw = _StubGateway()
        self.feed = _StubFeed()
        self.ctx = StrategyContext(gateway=self.gw, feed=self.feed)
        self.strategy = _TestStrategy()
        self.strategy._bind(self.ctx)

    def test_send_order_assigns_client_id(self) -> None:
        cid1 = self.strategy.send_order(1001, Side.BUY, 11000, 10)
        cid2 = self.strategy.send_order(1001, Side.SELL, 11002, 5)
        assert cid1 == 1
        assert cid2 == 2
        assert len(self.gw.sent) == 2
        assert self.gw.sent[0].client_order_id == 1

    def test_cancel_order(self) -> None:
        self.strategy.cancel_order(42)
        assert self.gw.cancelled == [42]

    def test_best_bid_ask(self) -> None:
        assert self.strategy.best_bid(1001) == 11000
        assert self.strategy.best_ask(1001) == 11002
        assert self.strategy.best_bid(9999) is None

    def test_callbacks_default_empty(self) -> None:
        bare = Strategy.__subclasses__
        s = _TestStrategy()
        s._bind(self.ctx)
        bu = BookUpdate(
            instrument_id=1001, timestamp_ns=100, seq_no=1,
            bid_price=11000, ask_price=11002, bid_size=10, ask_size=20,
        )
        s.on_book_update(bu)
        assert len(s.updates) == 1
