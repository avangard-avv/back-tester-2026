"""Tests for adapters (event, order, data, viz, price)."""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest

from python_wrapper_interface.adapters.data_adapter import (
    NdjsonDataAdapterTemplate,
    SyntheticDataAdapter,
)
from python_wrapper_interface.adapters.event_adapter import (
    CppEventAdapterTemplate,
    DefaultEventAdapter,
    GroupTwoLegacyAdapter,
    MockEventAdapter,
)
from python_wrapper_interface.adapters.order_adapter import (
    CppOrderAdapterTemplate,
    DefaultOrderAdapter,
    MockOrderAdapter,
)
from python_wrapper_interface.adapters.price import (
    decode_mantissa_exp,
    encode_mantissa_exp,
    from_scaled,
    to_scaled,
)
from python_wrapper_interface.adapters.viz_adapter import (
    MatplotlibVisualizer,
    PlotlyVisualizerTemplate,
)
from python_wrapper_interface.engines._raw_events import (
    RawAdd,
    RawBookUpdate,
    RawCancel,
    RawFill,
    RawTradeTick,
    _new_header,
)
from python_wrapper_interface.types import Order, Side


# -- price utilities ---------------------------------------------------------

class TestToScaled:
    def test_basic(self) -> None:
        assert to_scaled(Decimal("1.1234")) == 11234

    def test_zero(self) -> None:
        assert to_scaled(Decimal("0")) == 0

    def test_custom_scale(self) -> None:
        assert to_scaled(Decimal("2.5"), scale=100) == 250


class TestFromScaled:
    def test_basic(self) -> None:
        assert from_scaled(11234) == Decimal("1.1234")

    def test_round_trip(self) -> None:
        val = Decimal("3.1415")
        assert from_scaled(to_scaled(val)) == val


class TestDecodeMantissaExp:
    def test_negative_exp(self) -> None:
        assert decode_mantissa_exp(11234, -4) == 11234

    def test_zero_exp(self) -> None:
        assert decode_mantissa_exp(112, 0) == 1_120_000

    def test_positive_exp(self) -> None:
        assert decode_mantissa_exp(1, 1) == 100_000


# -- DefaultEventAdapter -----------------------------------------------------

class TestDefaultEventAdapter:
    def setup_method(self) -> None:
        self.adapter = DefaultEventAdapter()

    def test_to_book_update(self) -> None:
        raw = SimpleNamespace(
            instrument_id=1001, timestamp_ns=100, seq_no=1,
            bid_price=11000, ask_price=11002, bid_size=10, ask_size=20,
        )
        bu = self.adapter.to_book_update(raw)
        assert bu.instrument_id == 1001
        assert bu.bid_price == 11000

    def test_to_trade(self) -> None:
        raw = SimpleNamespace(
            instrument_id=1001, timestamp_ns=200, seq_no=2,
            price=11001, size=5, aggressor_side=1,
        )
        t = self.adapter.to_trade(raw)
        assert t.aggressor_side == Side.BUY
        assert t.size == 5

    def test_to_fill(self) -> None:
        raw = SimpleNamespace(
            order_id=42, client_order_id=1, instrument_id=1001,
            timestamp_ns=300, side=2,
            fill_price=11000, fill_size=10,
        )
        f = self.adapter.to_fill(raw)
        assert f.side == Side.SELL
        assert f.fill_price == 11000

    def test_to_reject(self) -> None:
        raw = SimpleNamespace(
            order_id=0, client_order_id=1, instrument_id=1001,
            timestamp_ns=400, reason="bad price",
        )
        r = self.adapter.to_reject(raw)
        assert r.reason == "bad price"


# -- GroupTwoLegacyAdapter ---------------------------------------------------

class TestGroupTwoLegacyAdapter:
    def setup_method(self) -> None:
        self.adapter = GroupTwoLegacyAdapter()

    def _header(self, ts: int = 100, seq: int = 1) -> SimpleNamespace:
        return SimpleNamespace(ts_ns=ts, sequence=seq)

    def test_to_book_update_with_mantissa_exp(self) -> None:
        raw = SimpleNamespace(
            instr=2002,
            header=self._header(),
            bid_mantissa=11234, bid_exp=-4,
            ask_mantissa=11236, ask_exp=-4,
            bid_qty=50, ask_qty=60,
        )
        bu = self.adapter.to_book_update(raw)
        assert bu.instrument_id == 2002
        assert bu.bid_price == 11234
        assert bu.ask_price == 11236
        assert bu.seq_no == 1

    def test_to_trade_string_side(self) -> None:
        raw = SimpleNamespace(
            instr=2002,
            header=self._header(ts=200, seq=2),
            trade_mantissa=11235, trade_exp=-4,
            qty=10, side_str="S",
        )
        t = self.adapter.to_trade(raw)
        assert t.aggressor_side == Side.SELL
        assert t.price == 11235

    def test_to_fill(self) -> None:
        raw = SimpleNamespace(
            exch_order_id=99, cl_ord_id=5, instr=2002,
            header=self._header(ts=300, seq=3),
            side_str="B",
            px_mantissa=11234, px_exp=-4, qty=20,
        )
        f = self.adapter.to_fill(raw)
        assert f.side == Side.BUY
        assert f.fill_size == 20

    def test_to_reject(self) -> None:
        raw = SimpleNamespace(
            exch_order_id=0, cl_ord_id=5, instr=2002,
            header=self._header(ts=400, seq=4),
            reject_text="instrument halted",
        )
        r = self.adapter.to_reject(raw)
        assert r.reason == "instrument halted"


# -- DefaultOrderAdapter -----------------------------------------------------

class TestDefaultOrderAdapter:
    def setup_method(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        mock_cpp = SimpleNamespace(
            NewOrder=lambda **kw: self.calls.append(("NewOrder", kw)) or SimpleNamespace(**kw),
            CancelOrder=lambda **kw: self.calls.append(("CancelOrder", kw)) or SimpleNamespace(**kw),
            ModifyOrder=lambda **kw: self.calls.append(("ModifyOrder", kw)) or SimpleNamespace(**kw),
        )
        self.adapter = DefaultOrderAdapter(mock_cpp)

    def test_to_cpp_new_order(self) -> None:
        order = Order(
            instrument_id=1001, side=Side.BUY,
            price=11000, size=10, client_order_id=7,
        )
        result = self.adapter.to_cpp_new_order(order)
        assert self.calls[-1][0] == "NewOrder"
        kw = self.calls[-1][1]
        assert kw["side"] == 1
        assert kw["client_order_id"] == 7

    def test_to_cpp_cancel(self) -> None:
        self.adapter.to_cpp_cancel(42)
        assert self.calls[-1] == ("CancelOrder", {"client_order_id": 42})

    def test_to_cpp_modify(self) -> None:
        self.adapter.to_cpp_modify(42, new_price=11500)
        kw = self.calls[-1][1]
        assert kw["client_order_id"] == 42
        assert kw["new_price"] == 11500
        assert kw["new_size"] == 0


# ---------------------------------------------------------------------------
# Price round trip
# ---------------------------------------------------------------------------


class TestPriceRoundTrip:
    def test_encode_decode_round_trip(self) -> None:
        for scaled in (1, 11_000, 12_345, 99_999):
            mantissa, exp = encode_mantissa_exp(scaled)
            assert decode_mantissa_exp(mantissa, exp) == scaled


# ---------------------------------------------------------------------------
# MockEventAdapter
# ---------------------------------------------------------------------------


def _mk_raw_book(symbol: str, bid_scaled: int, ask_scaled: int, seq: int = 1) -> RawBookUpdate:
    bid_m, bid_e = encode_mantissa_exp(bid_scaled)
    ask_m, ask_e = encode_mantissa_exp(ask_scaled)
    return RawBookUpdate(
        instrument_symbol=symbol,
        ts_micros=1_700_000_000_000_000,
        header=_new_header(seq),
        bid_px_mantissa=bid_m,
        bid_px_exp=bid_e,
        bid_size=10,
        ask_px_mantissa=ask_m,
        ask_px_exp=ask_e,
        ask_size=20,
    )


class TestMockEventAdapterRoundTrip:
    """Raw → clean preserves the semantically important fields."""

    def setup_method(self) -> None:
        self.adapter = MockEventAdapter({"EURUSD_F_202506": 1001})

    def test_book_update(self) -> None:
        raw = _mk_raw_book("EURUSD_F_202506", 11_000, 11_002, seq=5)
        clean = self.adapter.to_book_update(raw)
        assert clean.instrument_id == 1001
        assert clean.seq_no == 5
        assert clean.bid_price == 11_000
        assert clean.ask_price == 11_002
        assert clean.timestamp_ns == raw.ts_micros * 1_000

    def test_trade_string_side(self) -> None:
        raw = SimpleNamespace(
            instrument_symbol="EURUSD_F_202506",
            ts_micros=1_700_000_000_000_000,
            header=_new_header(7),
            px_mantissa=11_001,
            px_exp=-4,
            qty=5,
            side_char="S",
        )
        t = self.adapter.to_trade(raw)
        assert t.aggressor_side == Side.SELL
        assert t.size == 5
        assert t.price == 11_001

    def test_fill(self) -> None:
        raw = RawFill(
            exch_order_id=42, cl_ord_id=7,
            instrument_symbol="EURUSD_F_202506",
            ts_micros=1_700_000_000_000_001,
            header=_new_header(1),
            side_char="B", px_mantissa=11_002, px_exp=-4, qty=3,
        )
        f = self.adapter.to_fill(raw)
        assert f.order_id == 42
        assert f.client_order_id == 7
        assert f.instrument_id == 1001
        assert f.side == Side.BUY
        assert f.fill_price == 11_002
        assert f.fill_size == 3

    def test_auto_assigns_unknown_symbol(self) -> None:
        raw = _mk_raw_book("UNKNOWN_X", 1_000, 1_002)
        clean = self.adapter.to_book_update(raw)
        # Unknown symbol gets an auto-assigned id distinct from existing
        # ones.
        assert clean.instrument_id != 1001


# ---------------------------------------------------------------------------
# MockOrderAdapter — round-trip with MockEventAdapter via RawFill
# ---------------------------------------------------------------------------


class TestMockOrderAdapter:
    def setup_method(self) -> None:
        self.adapter = MockOrderAdapter()

    def test_new_order_dict_shape(self) -> None:
        order = Order(
            instrument_id=1001, side=Side.BUY,
            price=11_000, size=10, client_order_id=7,
        )
        cmd = self.adapter.to_engine_new_order(order)
        assert cmd["op"] == "new"
        assert cmd["client_order_id"] == 7
        assert cmd["side_char"] == "B"
        assert cmd["qty"] == 10
        # Decoded mantissa/exp must round-trip to the original scaled price.
        assert decode_mantissa_exp(cmd["px_mantissa"], cmd["px_exp"]) == 11_000

    def test_cancel(self) -> None:
        cmd = self.adapter.to_engine_cancel(42)
        assert cmd == {"op": "cancel", "client_order_id": 42}

    def test_modify_price_only(self) -> None:
        cmd = self.adapter.to_engine_modify(42, new_price=11_500)
        assert cmd["op"] == "modify"
        assert decode_mantissa_exp(cmd["new_px_mantissa"], cmd["new_px_exp"]) == 11_500
        assert "new_qty" not in cmd


# ---------------------------------------------------------------------------
# Cpp templates raise NotImplementedError (proves they're real stubs)
# ---------------------------------------------------------------------------


class TestCppEventAdapterTemplateRaises:
    def setup_method(self) -> None:
        self.adapter = CppEventAdapterTemplate({"EURUSD_F_202506": 1001})

    def test_book_update_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.adapter.to_book_update(SimpleNamespace())

    def test_trade_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.adapter.to_trade(SimpleNamespace())

    def test_fill_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.adapter.to_fill(SimpleNamespace())

    def test_reject_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.adapter.to_reject(SimpleNamespace())


class TestCppOrderAdapterTemplateRaises:
    def setup_method(self) -> None:
        self.adapter = CppOrderAdapterTemplate(cpp_module=SimpleNamespace())

    def test_new_order_raises(self) -> None:
        order = Order(instrument_id=1001, side=Side.BUY, price=1, size=1)
        with pytest.raises(NotImplementedError):
            self.adapter.to_engine_new_order(order)

    def test_cancel_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.adapter.to_engine_cancel(1)

    def test_modify_raises(self) -> None:
        with pytest.raises(NotImplementedError):
            self.adapter.to_engine_modify(1, new_price=1)


# ---------------------------------------------------------------------------
# SyntheticDataAdapter and NdjsonDataAdapterTemplate
# ---------------------------------------------------------------------------


class TestSyntheticDataAdapter:
    def test_event_count_matches(self) -> None:
        adapter = SyntheticDataAdapter(n_events=500, seed=1)
        adapter.load()
        evts = list(adapter)
        assert len(evts) == 500

    def test_deterministic(self) -> None:
        a = SyntheticDataAdapter(n_events=200, seed=1)
        a.load()
        b = SyntheticDataAdapter(n_events=200, seed=1)
        b.load()
        events_a = [(e.instrument_symbol, e.ts_micros, type(e).__name__) for e in a]
        events_b = [(e.instrument_symbol, e.ts_micros, type(e).__name__) for e in b]
        assert events_a == events_b

    def test_yields_all_three_event_kinds(self) -> None:
        adapter = SyntheticDataAdapter(n_events=2_000, seed=4)
        adapter.load()
        kinds = {type(e).__name__ for e in adapter}
        assert "RawAdd" in kinds
        assert "RawCancel" in kinds or "RawTradeTick" in kinds


class TestNdjsonTemplateRaises:
    def test_load_raises(self) -> None:
        a = NdjsonDataAdapterTemplate()
        with pytest.raises(NotImplementedError):
            a.load("file.ndjson", ("2024-01-01", "2024-01-02"))

    def test_iter_raises(self) -> None:
        a = NdjsonDataAdapterTemplate()
        with pytest.raises(NotImplementedError):
            list(iter(a))


# ---------------------------------------------------------------------------
# Adapter swap actually changes engine behavior
# ---------------------------------------------------------------------------


class TestEventAdapterSwapAffectsEngine:
    """A swapped event adapter changes what the strategy sees → changes fills."""

    def test_frozen_book_eliminates_fills(self) -> None:
        from python_wrapper_interface.examples.custom_adapter_example import (
            FrozenBookAdapter,
            _run,
        )

        baseline = _run("baseline", event_adapter=None)
        swapped = _run(
            "frozen", event_adapter=FrozenBookAdapter({"INSTR_1001": 1001}),
        )
        assert baseline > 0
        assert swapped == 0


class TestOrderAdapterSwapAffectsEngine:
    """A swapped order adapter is observed by the engine's resting book."""

    def test_custom_order_adapter_observed(self) -> None:
        from python_wrapper_interface import (
            BacktestRunner,
            BookUpdate,
            MockBacktestEngine,
            Side,
            Strategy,
        )
        from python_wrapper_interface.adapters.order_adapter import IOrderAdapter

        captured: list[dict] = []

        class CapturingAdapter(IOrderAdapter):
            def __init__(self) -> None:
                self._inner = MockOrderAdapter()

            def to_engine_new_order(self, order):
                cmd = self._inner.to_engine_new_order(order)
                captured.append(cmd)
                return cmd

            def to_engine_cancel(self, client_order_id):
                return self._inner.to_engine_cancel(client_order_id)

            def to_engine_modify(self, client_order_id, new_price=None, new_size=None):
                return self._inner.to_engine_modify(client_order_id, new_price, new_size)

        class _Aggressive(Strategy):
            def on_book_update(self, update: BookUpdate) -> None:
                if update.ask_price > 0:
                    self.send_order(update.instrument_id, Side.BUY, update.ask_price, 1)

        engine = MockBacktestEngine(
            num_events=200, seed=7,
            order_adapter=CapturingAdapter(),
        )
        BacktestRunner(engine).run(
            _Aggressive(), data_path=".",
            date_range=("2024-01-01", "2024-01-02"),
        )
        assert captured, "the swapped order adapter must have been called"
        assert all(c["op"] == "new" for c in captured)


# ---------------------------------------------------------------------------
# Visualization adapter
# ---------------------------------------------------------------------------


class TestMatplotlibVisualizer:
    def test_plot_returns_figure(self) -> None:
        import matplotlib
        matplotlib.use("Agg")
        from python_wrapper_interface import BacktestRunner, MockBacktestEngine
        from python_wrapper_interface.strategy import Strategy

        engine = MockBacktestEngine(num_events=200, seed=9)
        result = BacktestRunner(engine).run(
            Strategy.__subclasses__()[0]() if False else _BareStrategy(),
            data_path=".",
            date_range=("2024-01-01", "2024-01-02"),
        )
        viz = MatplotlibVisualizer(show=False)
        assert viz.plot_pnl(result) is not None
        assert viz.plot_fills_on_mid(result) is not None


class _BareStrategy:
    """Minimal Strategy subclass for the visualizer test."""

    def __new__(cls) -> object:
        from python_wrapper_interface import Strategy

        class _S(Strategy):
            def on_book_update(self, update) -> None:
                pass

        return _S()


class TestPlotlyTemplateRaises:
    def test_pnl_raises(self) -> None:
        viz = PlotlyVisualizerTemplate()
        with pytest.raises(NotImplementedError):
            viz.plot_pnl(None)  # type: ignore[arg-type]

    def test_fills_raises(self) -> None:
        viz = PlotlyVisualizerTemplate()
        with pytest.raises(NotImplementedError):
            viz.plot_fills_on_mid(None)  # type: ignore[arg-type]
