"""Tests for python_wrapper_interface.types."""

from __future__ import annotations

import pytest

from python_wrapper_interface.types import (
    PRICE_SCALE,
    BookUpdate,
    Fill,
    Order,
    OrderStatus,
    Reject,
    Side,
    Trade,
)


class TestSideEnum:
    def test_values(self) -> None:
        assert Side.BUY.value == 1
        assert Side.SELL.value == 2

    def test_members(self) -> None:
        assert set(Side) == {Side.BUY, Side.SELL}


class TestOrderStatus:
    def test_all_states(self) -> None:
        expected = {
            "PENDING", "ACKED", "FILLED",
            "PARTIALLY_FILLED", "CANCELLED", "REJECTED",
        }
        assert {s.value for s in OrderStatus} == expected


class TestBookUpdate:
    def test_frozen(self) -> None:
        bu = BookUpdate(
            instrument_id=1001, timestamp_ns=100, seq_no=1,
            bid_price=11000, ask_price=11002, bid_size=10, ask_size=20,
        )
        with pytest.raises(AttributeError):
            bu.bid_price = 999  # type: ignore[misc]

    def test_repr(self) -> None:
        bu = BookUpdate(
            instrument_id=1001, timestamp_ns=100, seq_no=1,
            bid_price=11000, ask_price=11002, bid_size=10, ask_size=20,
        )
        assert "BookUpdate" in repr(bu)
        assert "1001" in repr(bu)


class TestTrade:
    def test_fields(self) -> None:
        t = Trade(
            instrument_id=1001, timestamp_ns=200, seq_no=2,
            price=11001, size=5, aggressor_side=Side.BUY,
        )
        assert t.aggressor_side == Side.BUY
        assert t.size == 5


class TestFill:
    def test_fields(self) -> None:
        f = Fill(
            order_id=42, client_order_id=1, instrument_id=1001,
            timestamp_ns=300, side=Side.SELL,
            fill_price=11000, fill_size=10,
        )
        assert f.side == Side.SELL
        assert f.fill_price == 11000


class TestReject:
    def test_fields(self) -> None:
        r = Reject(
            order_id=0, client_order_id=1, instrument_id=1001,
            timestamp_ns=400, reason="insufficient margin",
        )
        assert "margin" in r.reason


class TestOrder:
    def test_default_client_order_id(self) -> None:
        o = Order(instrument_id=1001, side=Side.BUY, price=11000, size=10)
        assert o.client_order_id == 0

    def test_with_client_order_id(self) -> None:
        o = Order(
            instrument_id=1001, side=Side.BUY,
            price=11000, size=10, client_order_id=7,
        )
        assert o.client_order_id == 7


class TestPriceScale:
    def test_value(self) -> None:
        assert PRICE_SCALE == 10_000

    def test_round_trip(self) -> None:
        real = 1.1234
        scaled = int(real * PRICE_SCALE)
        assert scaled == 11234
        assert abs(scaled / PRICE_SCALE - real) < 1e-9
