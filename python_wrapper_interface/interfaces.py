"""Abstract interfaces for engine, order gateway, and market-data feed.

Every dependency on Groups 1/2/3 is expressed through these ABCs so that
concrete implementations (mock or C++) can be swapped transparently.
"""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from python_wrapper_interface.runner import ProgressInfo, Result
    from python_wrapper_interface.strategy import Strategy
    from python_wrapper_interface.types import Order, Side


class IOrderGateway(abc.ABC):
    """Sends orders to the matching engine and receives acknowledgements."""

    @abc.abstractmethod
    def send_order(self, order: Order) -> int:
        """Submit a new limit order.

        Parameters
        ----------
        order : Order
            The order to submit.

        Returns
        -------
        int
            The ``client_order_id`` assigned to this order.
        """

    @abc.abstractmethod
    def cancel_order(self, client_order_id: int) -> None:
        """Request cancellation of a live order.

        Parameters
        ----------
        client_order_id : int
            The strategy-assigned order identifier.
        """


class IMarketDataFeed(abc.ABC):
    """Provides current top-of-book state."""

    @abc.abstractmethod
    def best_bid(self, instrument_id: int) -> int | None:
        """Return the current best bid price (scaled int) or ``None``.

        Parameters
        ----------
        instrument_id : int
            Eurex product identifier.

        Returns
        -------
        int | None
            Best bid price, or ``None`` if no bid available.
        """

    @abc.abstractmethod
    def best_ask(self, instrument_id: int) -> int | None:
        """Return the current best ask price (scaled int) or ``None``.

        Parameters
        ----------
        instrument_id : int
            Eurex product identifier.

        Returns
        -------
        int | None
            Best ask price, or ``None`` if no ask available.
        """

    @abc.abstractmethod
    def subscribe(self, instrument_id: int) -> None:
        """Subscribe to market data for an instrument.

        Parameters
        ----------
        instrument_id : int
            Eurex product identifier.
        """


class IBacktestEngine(abc.ABC):
    """Main engine interface driving the event loop.

    Implementations produce market-data events, accept orders, simulate fills,
    and track PnL / statistics.
    """

    @abc.abstractmethod
    def load(self, data_path: str, date_range: tuple[str, str]) -> None:
        """Load historical data for the given date range.

        Parameters
        ----------
        data_path : str
            Path to data directory or file.
        date_range : tuple[str, str]
            ``(start_date, end_date)`` as ISO-8601 strings.
        """

    @abc.abstractmethod
    def step(self) -> bool:
        """Advance the simulation by one event.

        Returns
        -------
        bool
            ``True`` if an event was processed; ``False`` when the stream is
            exhausted.
        """

    @abc.abstractmethod
    def register_strategy(self, strategy: Strategy) -> None:
        """Attach a strategy to receive callbacks.

        Parameters
        ----------
        strategy : Strategy
            The strategy instance.
        """

    @abc.abstractmethod
    def order_gateway(self) -> IOrderGateway:
        """Return the order gateway used by this engine.

        Returns
        -------
        IOrderGateway
        """

    @abc.abstractmethod
    def market_data_feed(self) -> IMarketDataFeed:
        """Return the market-data feed used by this engine.

        Returns
        -------
        IMarketDataFeed
        """

    @abc.abstractmethod
    def progress(self) -> ProgressInfo:
        """Return current simulation progress and statistics.

        Returns
        -------
        ProgressInfo
        """

    @abc.abstractmethod
    def build_result(self) -> Result:
        """Build the final backtest result after the event loop ends.

        Returns
        -------
        Result
        """

    def config(self) -> dict[str, Any]:
        """Return engine configuration (optional override).

        Returns
        -------
        dict[str, Any]
        """
        return {}
