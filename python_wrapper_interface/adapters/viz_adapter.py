"""Visualization adapters: produce plots from a :class:`Result`.

The default :class:`MatplotlibVisualizer` renders the standard PnL plot and
fills-on-mid overlay; :class:`PlotlyVisualizerTemplate` is a stub for an
interactive HTML alternative.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from python_wrapper_interface.runner import Result


class IResultVisualizer(abc.ABC):
    """Renders a backtest :class:`Result` to a figure object."""

    @abc.abstractmethod
    def plot_pnl(self, result: Result) -> Any:
        """Plot cumulative PnL over time.

        Parameters
        ----------
        result : Result

        Returns
        -------
        Any
            Figure object (caller may save or display it).
        """

    @abc.abstractmethod
    def plot_fills_on_mid(self, result: Result) -> Any:
        """Overlay fill prices on the mid-price series.

        Parameters
        ----------
        result : Result

        Returns
        -------
        Any
            Figure object.
        """


# ---------------------------------------------------------------------------
# Matplotlib — default working implementation
# ---------------------------------------------------------------------------


class MatplotlibVisualizer(IResultVisualizer):
    """Default visualizer using ``matplotlib.pyplot``.

    Parameters
    ----------
    show : bool
        If ``True``, call ``plt.show()`` after building the figure.
        Defaults to ``False`` so the figure can be inspected/saved by
        callers (tests, notebooks).
    """

    def __init__(self, show: bool = False) -> None:
        self._show = show

    def plot_pnl(self, result: Result) -> Any:
        import matplotlib.pyplot as plt
        import pandas as pd

        fig, ax = plt.subplots(figsize=(10, 4))
        if not result.pnl_series.empty:
            ts = pd.to_datetime(result.pnl_series["timestamp_ns"], unit="ns")
            ax.plot(ts, result.pnl_series["cumulative_pnl"], label="PnL")
            ax.set_ylabel("Cumulative PnL")
            ax.set_xlabel("Time")
            ax.legend()
            ax.grid(True, alpha=0.3)
        else:
            ax.text(
                0.5, 0.5, "no fills, no PnL",
                ha="center", va="center", transform=ax.transAxes,
            )
        fig.suptitle("Cumulative PnL")
        fig.tight_layout()
        if self._show:
            plt.show()
        return fig

    def plot_fills_on_mid(self, result: Result) -> Any:
        import matplotlib.pyplot as plt
        import pandas as pd

        from python_wrapper_interface.types import PRICE_SCALE

        fig, ax = plt.subplots(figsize=(10, 5))

        if result.fills_df.empty:
            ax.text(
                0.5, 0.5, "no fills to plot",
                ha="center", va="center", transform=ax.transAxes,
            )
            fig.suptitle("Fills on Mid Price")
            fig.tight_layout()
            if self._show:
                plt.show()
            return fig

        ts_fills = pd.to_datetime(result.fills_df["timestamp_ns"], unit="ns")
        prices = result.fills_df["fill_price"] / PRICE_SCALE

        if "mid_price" in result.fills_df.columns:
            ax.plot(
                ts_fills,
                result.fills_df["mid_price"] / PRICE_SCALE,
                color="grey",
                alpha=0.5,
                label="mid",
            )

        buys = result.fills_df["side"] == "BUY"
        sells = ~buys
        if buys.any():
            ax.scatter(
                ts_fills[buys], prices[buys],
                marker="^", color="green", s=40,
                label="buy fill", zorder=5,
            )
        if sells.any():
            ax.scatter(
                ts_fills[sells], prices[sells],
                marker="v", color="red", s=40,
                label="sell fill", zorder=5,
            )

        ax.set_ylabel("Price")
        ax.set_xlabel("Time")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.suptitle("Fills on Mid Price")
        fig.tight_layout()
        if self._show:
            plt.show()
        return fig


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------


class PlotlyVisualizerTemplate(IResultVisualizer):
    """Stub for an interactive Plotly-based visualizer.

    Copy this class, rename it to ``PlotlyVisualizer``, and fill in the
    methods using ``plotly.graph_objects``.  See
    :class:`MatplotlibVisualizer` for the data layout used by ``Result``.
    """

    def plot_pnl(self, result: Result) -> Any:
        raise NotImplementedError(
            "Visualization team: implement using plotly.graph_objects.Figure. "
            "See MatplotlibVisualizer.plot_pnl for the column layout."
        )

    def plot_fills_on_mid(self, result: Result) -> Any:
        raise NotImplementedError(
            "Visualization team: implement using plotly.graph_objects.Figure. "
            "See MatplotlibVisualizer.plot_fills_on_mid for the column layout."
        )


__all__ = [
    "IResultVisualizer",
    "MatplotlibVisualizer",
    "PlotlyVisualizerTemplate",
]
