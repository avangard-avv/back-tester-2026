"""Tests for BacktestRunner lifecycle and progress callback."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

from python_wrapper_interface.engines.mock_engine import MockBacktestEngine
from python_wrapper_interface.runner import BacktestRunner, ProgressInfo
from python_wrapper_interface.strategy import Strategy
from python_wrapper_interface.types import BookUpdate, Fill, Side, Trade


class _LifecycleStrategy(Strategy):
    def __init__(self) -> None:
        super().__init__()
        self.started = False
        self.stopped = False
        self.event_count = 0

    def on_start(self) -> None:
        self.started = True

    def on_stop(self) -> None:
        self.stopped = True

    def on_book_update(self, update: BookUpdate) -> None:
        self.event_count += 1

    def on_trade(self, trade: Trade) -> None:
        self.event_count += 1


class TestBacktestRunnerLifecycle:
    def test_on_start_on_stop_called(self) -> None:
        engine = MockBacktestEngine(num_events=50, seed=1)
        runner = BacktestRunner(engine)
        strat = _LifecycleStrategy()

        result = runner.run(strat, ".", ("2024-01-01", "2024-01-02"))

        assert strat.started is True
        assert strat.stopped is True
        assert strat.event_count == 50

    def test_result_has_dataframes(self) -> None:
        engine = MockBacktestEngine(num_events=50, seed=2)
        runner = BacktestRunner(engine)
        strat = _LifecycleStrategy()

        result = runner.run(strat, ".", ("2024-01-01", "2024-01-02"))

        assert hasattr(result, "pnl_series")
        assert hasattr(result, "fills_df")
        assert hasattr(result, "order_log_df")


class TestProgressCallback:
    def test_callback_invoked(self) -> None:
        engine = MockBacktestEngine(num_events=100, seed=3)
        runner = BacktestRunner(engine)
        strat = _LifecycleStrategy()

        progress_reports: list[ProgressInfo] = []

        result = runner.run(
            strat, ".", ("2024-01-01", "2024-01-02"),
            progress_callback=lambda p: progress_reports.append(p),
            progress_interval_s=0.0,
        )

        assert len(progress_reports) > 0
        last = progress_reports[-1]
        assert last.percent_done == 1.0

    def test_no_callback_if_none(self) -> None:
        engine = MockBacktestEngine(num_events=50, seed=4)
        runner = BacktestRunner(engine)
        strat = _LifecycleStrategy()

        result = runner.run(strat, ".", ("2024-01-01", "2024-01-02"))
        assert result is not None


class TestRunnerWithAggressiveStrategy:
    def test_fills_in_result(self) -> None:
        class _Aggressive(Strategy):
            def __init__(self) -> None:
                super().__init__()

            def on_book_update(self, update: BookUpdate) -> None:
                ask = self.best_ask(update.instrument_id)
                if ask is not None:
                    self.send_order(update.instrument_id, Side.BUY, ask, 1)

        engine = MockBacktestEngine(num_events=200, seed=5)
        runner = BacktestRunner(engine)
        strat = _Aggressive()

        result = runner.run(strat, ".", ("2024-01-01", "2024-01-02"))
        assert not result.fills_df.empty
        assert not result.pnl_series.empty
