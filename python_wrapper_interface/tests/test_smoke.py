"""End-to-end smoke tests for the mock pipeline.

These tests exercise the full data → engine → adapter → strategy →
adapter → engine flow without any C++ dependency.
"""

from __future__ import annotations

import pandas as pd

from python_wrapper_interface import (
    BacktestRunner,
    BookUpdate,
    Fill,
    MockBacktestEngine,
    Side,
    Strategy,
    Trade,
)
from python_wrapper_interface.engines._raw_events import (
    RawBookUpdate,
    RawTrade,
)
from python_wrapper_interface.runner import ProgressInfo


class _Recorder(Strategy):
    """Captures every callback for downstream assertions."""

    def __init__(self) -> None:
        super().__init__()
        self.book_updates: list[BookUpdate] = []
        self.trades: list[Trade] = []
        self.fills: list[Fill] = []

    def on_book_update(self, update: BookUpdate) -> None:
        self.book_updates.append(update)

    def on_trade(self, trade: Trade) -> None:
        self.trades.append(trade)

    def on_fill(self, fill: Fill) -> None:
        self.fills.append(fill)


class _Aggressive(Strategy):
    """Crosses the spread on every book update — guaranteed to fill."""

    def __init__(self) -> None:
        super().__init__()
        self.fills: list[Fill] = []

    def on_book_update(self, update: BookUpdate) -> None:
        if update.ask_price > 0:
            self.send_order(
                update.instrument_id, Side.BUY, update.ask_price, 1,
            )

    def on_fill(self, fill: Fill) -> None:
        self.fills.append(fill)


# ---------------------------------------------------------------------------


class TestEngineRunsToCompletion:
    def test_engine_runs_to_completion(self) -> None:
        engine = MockBacktestEngine(num_events=200, seed=1)
        engine.load(".", ("2024-01-01", "2024-01-02"))
        recorder = _Recorder()
        engine.register_strategy(recorder)

        n = 0
        while engine.step():
            n += 1

        assert n == 200
        assert len(recorder.book_updates) + len(recorder.trades) == n


class TestStrategyReceivesCleanDataclasses:
    def test_strategy_sees_clean_BookUpdate_not_RawBookUpdate(self) -> None:
        engine = MockBacktestEngine(num_events=50, seed=2)
        engine.load(".", ("2024-01-01", "2024-01-02"))
        recorder = _Recorder()
        engine.register_strategy(recorder)

        while engine.step():
            pass

        assert recorder.book_updates, "expected at least one book update"
        first = recorder.book_updates[0]
        assert isinstance(first, BookUpdate)
        assert not isinstance(first, RawBookUpdate)

        if recorder.trades:
            t = recorder.trades[0]
            assert isinstance(t, Trade)
            assert not isinstance(t, RawTrade)
            assert isinstance(t.aggressor_side, Side)


class TestOrdersGetFilled:
    def test_aggressive_strategy_sees_on_fill(self) -> None:
        engine = MockBacktestEngine(num_events=300, seed=10)
        engine.load(".", ("2024-01-01", "2024-01-02"))
        strat = _Aggressive()
        engine.register_strategy(strat)

        while engine.step():
            pass

        assert len(strat.fills) > 0
        for fill in strat.fills:
            assert isinstance(fill, Fill)
            assert fill.side == Side.BUY
            assert fill.fill_size == 1


class TestResultDataframesSchema:
    def test_result_columns(self) -> None:
        engine = MockBacktestEngine(num_events=200, seed=11)
        runner = BacktestRunner(engine)
        result = runner.run(
            _Aggressive(), data_path=".",
            date_range=("2024-01-01", "2024-01-02"),
        )
        assert isinstance(result.pnl_series, pd.DataFrame)
        assert isinstance(result.fills_df, pd.DataFrame)
        assert isinstance(result.order_log_df, pd.DataFrame)

        assert "timestamp_ns" in result.pnl_series.columns
        assert "cumulative_pnl" in result.pnl_series.columns

        for col in (
            "order_id", "client_order_id", "instrument_id",
            "timestamp_ns", "side", "fill_price", "fill_size", "mid_price",
        ):
            assert col in result.fills_df.columns

        for col in (
            "client_order_id", "order_id", "instrument_id",
            "side", "price", "size", "status", "timestamp_ns",
        ):
            assert col in result.order_log_df.columns


class TestProgressCallbackInvoked:
    def test_progress_callback_invoked(self) -> None:
        engine = MockBacktestEngine(num_events=100, seed=12)
        runner = BacktestRunner(engine)
        reports: list[ProgressInfo] = []
        runner.run(
            _Recorder(), data_path=".",
            date_range=("2024-01-01", "2024-01-02"),
            progress_callback=reports.append,
            progress_interval_s=0.0,
        )
        assert reports, "expected at least one progress report"
        assert reports[-1].percent_done == 1.0


class TestReproducibility:
    def test_same_seed_same_fills(self) -> None:
        def run_once(seed: int) -> list[tuple]:
            engine = MockBacktestEngine(num_events=300, seed=seed)
            runner = BacktestRunner(engine)
            strat = _Aggressive()
            runner.run(
                strat, data_path=".",
                date_range=("2024-01-01", "2024-01-02"),
            )
            return [(f.timestamp_ns, f.fill_price, f.fill_size) for f in strat.fills]

        a = run_once(seed=42)
        b = run_once(seed=42)
        assert a == b, "same seed must produce identical fills"
