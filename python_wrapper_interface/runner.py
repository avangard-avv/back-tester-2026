"""Backtest runner, result container, and progress reporting.

:class:`BacktestRunner` orchestrates the event loop: it wires a
:class:`Strategy` to an :class:`IBacktestEngine`, drives ``step()`` until
exhaustion, and returns a :class:`Result` with pandas DataFrames.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from python_wrapper_interface.interfaces import IBacktestEngine
from python_wrapper_interface.strategy import Strategy, StrategyContext

logger = logging.getLogger(__name__)


@dataclass
class ProgressInfo:
    """Snapshot of simulation progress and order statistics.

    Parameters
    ----------
    percent_done : float
        Fraction of events processed (0.0 – 1.0).
    last_timestamp_ns : int
        Timestamp of the most recent event.
    current_pnl : float
        Cumulative realised PnL at this point.
    orders_sent : int
        Total orders submitted.
    orders_cancelled : int
        Total cancellation requests.
    orders_filled : int
        Total fills received.
    orders_rejected : int
        Total rejects received.
    by_instrument : dict[int, dict[str, int]]
        Per-instrument breakdown (keys: ``sent``, ``filled``, ``rejected``).
    """

    percent_done: float = 0.0
    last_timestamp_ns: int = 0
    current_pnl: float = 0.0
    orders_sent: int = 0
    orders_cancelled: int = 0
    orders_filled: int = 0
    orders_rejected: int = 0
    by_instrument: dict[int, dict[str, int]] = field(default_factory=dict)


@dataclass
class Result:
    """Final backtest output.

    Contains three DataFrames and a convenience plotting method.

    Parameters
    ----------
    pnl_series : pd.DataFrame
        Columns: ``timestamp_ns``, ``cumulative_pnl``.
    fills_df : pd.DataFrame
        One row per fill with columns matching :class:`Fill` fields.
    order_log_df : pd.DataFrame
        Full order lifecycle log.
    """

    pnl_series: pd.DataFrame
    fills_df: pd.DataFrame
    order_log_df: pd.DataFrame

    def plot_pnl(self) -> object:
        """Plot cumulative PnL using the default matplotlib visualizer.

        Returns
        -------
        matplotlib.figure.Figure
            The figure object (also shown on screen).

        Notes
        -----
        Delegates to
        :class:`python_wrapper_interface.adapters.viz_adapter.MatplotlibVisualizer`.
        Pass a different :class:`IResultVisualizer` directly if you want a
        non-default rendering.
        """
        from python_wrapper_interface.adapters.viz_adapter import (
            MatplotlibVisualizer,
        )

        return MatplotlibVisualizer(show=True).plot_pnl(self)


class BacktestRunner:
    """Drives the backtest event loop.

    Parameters
    ----------
    engine : IBacktestEngine
        The engine implementation to use (mock or C++).
    """

    def __init__(self, engine: IBacktestEngine) -> None:
        self._engine = engine

    def run(
        self,
        strategy: Strategy,
        data_path: str,
        date_range: tuple[str, str],
        progress_callback: Callable[[ProgressInfo], None] | None = None,
        progress_interval_s: float = 30.0,
    ) -> Result:
        """Execute a full backtest.

        Parameters
        ----------
        strategy : Strategy
            The user strategy to run.
        data_path : str
            Path to historical data.
        date_range : tuple[str, str]
            ``(start_date, end_date)`` ISO-8601 strings.
        progress_callback : Callable[[ProgressInfo], None] | None
            Optional callback invoked periodically with progress stats.
        progress_interval_s : float
            Minimum wall-clock seconds between progress callbacks (default 30).

        Returns
        -------
        Result
            DataFrames with PnL, fills, and order log.
        """
        engine = self._engine

        logger.info("loading data from %s for %s", data_path, date_range)
        engine.load(data_path, date_range)

        ctx = StrategyContext(
            gateway=engine.order_gateway(),
            feed=engine.market_data_feed(),
        )
        strategy._bind(ctx)
        engine.register_strategy(strategy)

        logger.info("starting strategy %s", type(strategy).__name__)
        strategy.on_start()

        last_progress_time = time.monotonic()

        while engine.step():
            now = time.monotonic()
            if (
                progress_callback is not None
                and now - last_progress_time >= progress_interval_s
            ):
                progress_callback(engine.progress())
                last_progress_time = now

        strategy.on_stop()
        logger.info("strategy stopped")

        if progress_callback is not None:
            progress_callback(engine.progress())

        return engine.build_result()
