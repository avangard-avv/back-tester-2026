"""Base class for user-defined trading strategies.

Users subclass :class:`Strategy`, override the callbacks they need, and use
the action helpers (``send_order``, ``cancel_order``) plus market-state
getters (``best_bid``, ``best_ask``) to implement their logic.
"""

from __future__ import annotations

import abc
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

from python_wrapper_interface.types import Order, Side

if TYPE_CHECKING:
    from python_wrapper_interface.interfaces import IMarketDataFeed, IOrderGateway
    from python_wrapper_interface.types import BookUpdate, Fill, Reject, Trade

logger = logging.getLogger(__name__)


@dataclass
class StrategyContext:
    """Injected by the runner before ``on_start()``.

    Parameters
    ----------
    gateway : IOrderGateway
        Order submission gateway.
    feed : IMarketDataFeed
        Market-data state provider.
    """

    gateway: IOrderGateway
    feed: IMarketDataFeed


class Strategy(abc.ABC):
    """Abstract base class for a trading strategy.

    Lifecycle
    ---------
    1. Runner calls ``_bind(context)`` to inject dependencies.
    2. ``on_start()`` — strategy initialisation.
    3. Event callbacks (``on_book_update``, ``on_trade``, ``on_fill``,
       ``on_reject``) are invoked as events arrive.
    4. ``on_stop()`` — cleanup after the event stream is exhausted.

    All callbacks have empty default implementations so the user only
    overrides what is needed.
    """

    def __init__(self) -> None:
        self._ctx: StrategyContext | None = None
        self._next_client_order_id: int = 1

    # -- internal ------------------------------------------------------------

    def _bind(self, ctx: StrategyContext) -> None:
        """Attach the strategy context (called by the runner)."""
        self._ctx = ctx

    def _require_ctx(self) -> StrategyContext:
        if self._ctx is None:
            raise RuntimeError(
                "Strategy is not bound to a context. "
                "Use BacktestRunner.run() to execute the strategy."
            )
        return self._ctx

    # -- lifecycle ------------------------------------------------------------

    def on_start(self) -> None:
        """Called once before the first event. Override to initialise state."""

    def on_stop(self) -> None:
        """Called once after the last event. Override to finalise state."""

    # -- event callbacks (override as needed) ---------------------------------

    def on_book_update(self, update: BookUpdate) -> None:
        """Called on each top-of-book update.

        Parameters
        ----------
        update : BookUpdate
        """

    def on_trade(self, trade: Trade) -> None:
        """Called on each exchange trade.

        Parameters
        ----------
        trade : Trade
        """

    def on_fill(self, fill: Fill) -> None:
        """Called when an order is filled (fully or partially).

        Parameters
        ----------
        fill : Fill
        """

    def on_reject(self, reject: Reject) -> None:
        """Called when an order is rejected.

        Parameters
        ----------
        reject : Reject
        """

    # -- actions --------------------------------------------------------------

    def send_order(
        self,
        instrument_id: int,
        side: Side,
        price: int,
        size: int,
    ) -> int:
        """Submit a new limit order.

        Parameters
        ----------
        instrument_id : int
            Eurex product identifier.
        side : Side
            BUY or SELL.
        price : int
            Limit price (scaled integer).
        size : int
            Order quantity.

        Returns
        -------
        int
            The ``client_order_id`` assigned to this order.
        """
        ctx = self._require_ctx()
        cid = self._next_client_order_id
        self._next_client_order_id += 1
        order = Order(
            instrument_id=instrument_id,
            side=side,
            price=price,
            size=size,
            client_order_id=cid,
        )
        ctx.gateway.send_order(order)
        logger.debug("sent order cid=%d %s %d@%d", cid, side.name, size, price)
        return cid

    def cancel_order(self, client_order_id: int) -> None:
        """Request cancellation of a live order.

        Parameters
        ----------
        client_order_id : int
            The strategy-assigned order identifier.
        """
        ctx = self._require_ctx()
        ctx.gateway.cancel_order(client_order_id)
        logger.debug("cancel requested cid=%d", client_order_id)

    # -- market-state getters -------------------------------------------------

    def best_bid(self, instrument_id: int) -> int | None:
        """Return the current best bid price (scaled int) or ``None``.

        Parameters
        ----------
        instrument_id : int
            Eurex product identifier.

        Returns
        -------
        int | None
        """
        return self._require_ctx().feed.best_bid(instrument_id)

    def best_ask(self, instrument_id: int) -> int | None:
        """Return the current best ask price (scaled int) or ``None``.

        Parameters
        ----------
        instrument_id : int
            Eurex product identifier.

        Returns
        -------
        int | None
        """
        return self._require_ctx().feed.best_ask(instrument_id)
