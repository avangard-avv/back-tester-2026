"""Tests for MockBacktestEngine."""

from __future__ import annotations

from python_wrapper_interface.engines.mock_engine import MockBacktestEngine
from python_wrapper_interface.strategy import Strategy
from python_wrapper_interface.types import BookUpdate, Fill, Side, Trade


class _CountingStrategy(Strategy):
    def __init__(self) -> None:
        super().__init__()
        self.book_updates = 0
        self.trades = 0
        self.fills: list[Fill] = []

    def on_book_update(self, update: BookUpdate) -> None:
        self.book_updates += 1

    def on_trade(self, trade: Trade) -> None:
        self.trades += 1


class _AggressiveStrategy(Strategy):
    """Sends a buy order on every book update."""

    def __init__(self) -> None:
        super().__init__()
        self.fills: list[Fill] = []

    def on_book_update(self, update: BookUpdate) -> None:
        ask = self.best_ask(update.instrument_id)
        if ask is not None:
            self.send_order(update.instrument_id, Side.BUY, ask, 1)

    def on_fill(self, fill: Fill) -> None:
        self.fills.append(fill)


class TestMockEngineBasic:
    def test_generates_events(self) -> None:
        engine = MockBacktestEngine(num_events=100, seed=1)
        engine.load(".", ("2024-01-01", "2024-01-02"))
        strat = _CountingStrategy()
        engine.register_strategy(strat)

        count = 0
        while engine.step():
            count += 1

        assert count == 100
        assert strat.book_updates + strat.trades == 100
        assert strat.book_updates > 0
        assert strat.trades > 0

    def test_progress_updates(self) -> None:
        engine = MockBacktestEngine(num_events=50, seed=2)
        engine.load(".", ("2024-01-01", "2024-01-02"))
        strat = _CountingStrategy()
        engine.register_strategy(strat)

        while engine.step():
            pass

        prog = engine.progress()
        assert prog.percent_done == 1.0
        assert prog.last_timestamp_ns > 0

    def test_build_result_dataframes(self) -> None:
        engine = MockBacktestEngine(num_events=50, seed=3)
        engine.load(".", ("2024-01-01", "2024-01-02"))
        strat = _CountingStrategy()
        engine.register_strategy(strat)

        while engine.step():
            pass

        result = engine.build_result()
        assert "timestamp_ns" in result.pnl_series.columns or result.pnl_series.empty
        assert list(result.order_log_df.columns) == [
            "client_order_id", "order_id", "instrument_id",
            "side", "price", "size", "status", "timestamp_ns",
        ] or result.order_log_df.empty


class TestMockEngineFills:
    def test_fill_on_aggressive_order(self) -> None:
        engine = MockBacktestEngine(
            instrument_ids=[1001],
            num_events=200,
            seed=10,
        )
        engine.load(".", ("2024-01-01", "2024-01-02"))
        strat = _AggressiveStrategy()
        engine.register_strategy(strat)

        while engine.step():
            pass

        assert len(strat.fills) > 0
        for fill in strat.fills:
            assert fill.side == Side.BUY
            assert fill.fill_size == 1

    def test_pnl_tracked(self) -> None:
        engine = MockBacktestEngine(
            instrument_ids=[1001],
            num_events=200,
            seed=11,
        )
        engine.load(".", ("2024-01-01", "2024-01-02"))
        strat = _AggressiveStrategy()
        engine.register_strategy(strat)

        while engine.step():
            pass

        result = engine.build_result()
        assert not result.pnl_series.empty
        assert not result.fills_df.empty

    def test_order_statistics(self) -> None:
        engine = MockBacktestEngine(
            instrument_ids=[1001],
            num_events=100,
            seed=12,
        )
        engine.load(".", ("2024-01-01", "2024-01-02"))
        strat = _AggressiveStrategy()
        engine.register_strategy(strat)

        while engine.step():
            pass

        prog = engine.progress()
        assert prog.orders_sent > 0
        assert prog.orders_filled > 0
        assert prog.orders_sent >= prog.orders_filled
        assert 1001 in prog.by_instrument


class TestMockEngineMultiInstrument:
    def test_two_instruments(self) -> None:
        engine = MockBacktestEngine(
            instrument_ids=[1001, 2002],
            num_events=500,
            seed=20,
        )
        engine.load(".", ("2024-01-01", "2024-01-02"))
        strat = _AggressiveStrategy()
        engine.register_strategy(strat)

        while engine.step():
            pass

        prog = engine.progress()
        assert 1001 in prog.by_instrument
        assert 2002 in prog.by_instrument
