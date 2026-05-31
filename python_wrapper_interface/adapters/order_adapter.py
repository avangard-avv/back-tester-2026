"""Order adapters: convert clean ``Order`` commands to engine-internal form.

Mirror image of :mod:`.event_adapter` — events flow engine→strategy and pass
through :class:`IEventAdapter`; commands flow strategy→engine and pass
through :class:`IOrderAdapter`.

The C++ team should look at :class:`MockOrderAdapter` as the reference
implementation, then copy :class:`CppOrderAdapterTemplate` and fill in the
``NotImplementedError`` bodies using their pybind11 message factories.
"""

from __future__ import annotations

import abc
from typing import Any

from python_wrapper_interface.adapters.price import encode_mantissa_exp
from python_wrapper_interface.types import Order, Side


_SIDE_TO_CHAR: dict[Side, str] = {Side.BUY: "B", Side.SELL: "S"}
_SIDE_TO_CPP_INT: dict[Side, int] = {Side.BUY: 1, Side.SELL: 2}


class IOrderAdapter(abc.ABC):
    """Maps clean :class:`Order` commands to engine-internal messages."""

    @abc.abstractmethod
    def to_engine_new_order(self, order: Order) -> Any:
        """Build the engine's "new order" command.

        Parameters
        ----------
        order : Order
            Clean order command from the strategy.

        Returns
        -------
        Any
            Engine-native message (dict, struct, pybind object, …).
        """

    @abc.abstractmethod
    def to_engine_cancel(self, client_order_id: int) -> Any:
        """Build the engine's "cancel order" command.

        Parameters
        ----------
        client_order_id : int

        Returns
        -------
        Any
        """

    @abc.abstractmethod
    def to_engine_modify(
        self,
        client_order_id: int,
        new_price: int | None = None,
        new_size: int | None = None,
    ) -> Any:
        """Build the engine's "modify order" command.

        Parameters
        ----------
        client_order_id : int
        new_price : int | None
            New price in scaled-integer form, or ``None`` to keep current.
        new_size : int | None
            New size, or ``None`` to keep current.

        Returns
        -------
        Any
        """


# ---------------------------------------------------------------------------
# Mock adapter — produces dict-shaped commands for MockBacktestEngine
# ---------------------------------------------------------------------------


class MockOrderAdapter(IOrderAdapter):
    """Reference implementation paired with :class:`MockBacktestEngine`.

    Converts a clean :class:`Order` like
    ``Order(side=Side.BUY, price=11000, size=10)`` to the mock engine's
    raw command:
    ``{'op': 'new', 'side_char': 'B', 'px_mantissa': 11000, 'px_exp': -4,
       'qty': 10, ...}``.

    The C++ adapter will follow the same logic but emit a pybind11-bound
    struct instead of a dict.
    """

    def to_engine_new_order(self, order: Order) -> dict[str, Any]:
        mantissa, exp = encode_mantissa_exp(order.price)
        return {
            "op": "new",
            "client_order_id": order.client_order_id,
            "instrument_id": order.instrument_id,
            "side_char": _SIDE_TO_CHAR[order.side],
            "px_mantissa": mantissa,
            "px_exp": exp,
            "qty": order.size,
        }

    def to_engine_cancel(self, client_order_id: int) -> dict[str, Any]:
        return {
            "op": "cancel",
            "client_order_id": client_order_id,
        }

    def to_engine_modify(
        self,
        client_order_id: int,
        new_price: int | None = None,
        new_size: int | None = None,
    ) -> dict[str, Any]:
        cmd: dict[str, Any] = {
            "op": "modify",
            "client_order_id": client_order_id,
        }
        if new_price is not None:
            mantissa, exp = encode_mantissa_exp(new_price)
            cmd["new_px_mantissa"] = mantissa
            cmd["new_px_exp"] = exp
        if new_size is not None:
            cmd["new_qty"] = new_size
        return cmd


# ---------------------------------------------------------------------------
# C++ template
# ---------------------------------------------------------------------------


class CppOrderAdapterTemplate(IOrderAdapter):
    """Skeleton for the C++ order adapter.

    Copy this class, rename it to ``CppOrderAdapter``, and fill in the
    method bodies using the pybind11-bound message factories exposed by
    your engine module (e.g. ``cpp_module.NewOrder(...)``).  See
    :class:`MockOrderAdapter` for a reference implementation.

    Parameters
    ----------
    cpp_module : Any
        The pybind11-bound module exposing ``NewOrder``, ``CancelOrder``,
        and ``ModifyOrder`` factories.
    """

    def __init__(self, cpp_module: Any) -> None:
        self._cpp = cpp_module

    def to_engine_new_order(self, order: Order) -> Any:
        """Build a C++ ``NewOrder`` message.

        Expected fields on the C++ struct (rename as needed):
            * ``client_order_id`` : ``uint64_t``
            * ``instrument_id`` : ``uint32_t``
            * ``side`` : ``uint8_t`` (1=BUY, 2=SELL)  or ``side_char``
            * ``px_mantissa`` / ``px_exp`` : encoded via
              :func:`python_wrapper_interface.adapters.price.encode_mantissa_exp`.
            * ``qty`` : ``uint32_t``
        """
        raise NotImplementedError(
            "C++ team / Group 1: implement using self._cpp.NewOrder(...) "
            "with order.{client_order_id, instrument_id, side, price, size}. "
            "See MockOrderAdapter.to_engine_new_order for reference."
        )

    def to_engine_cancel(self, client_order_id: int) -> Any:
        """Build a C++ ``CancelOrder`` message.

        Expected fields:
            * ``client_order_id`` : ``uint64_t``
        """
        raise NotImplementedError(
            "C++ team / Group 1: implement using "
            "self._cpp.CancelOrder(client_order_id=client_order_id)."
        )

    def to_engine_modify(
        self,
        client_order_id: int,
        new_price: int | None = None,
        new_size: int | None = None,
    ) -> Any:
        """Build a C++ ``ModifyOrder`` message.

        Expected fields:
            * ``client_order_id`` : ``uint64_t``
            * ``new_px_mantissa`` / ``new_px_exp`` (optional)
            * ``new_qty`` : ``uint32_t`` (optional)
        """
        raise NotImplementedError(
            "C++ team / Group 1: implement using self._cpp.ModifyOrder(...). "
            "See MockOrderAdapter.to_engine_modify for reference."
        )


# ---------------------------------------------------------------------------
# Backwards-compatible historical adapter (kept for existing tests)
# ---------------------------------------------------------------------------


class DefaultOrderAdapter(IOrderAdapter):
    """Standard adapter that calls into a pybind11-bound C++ module.

    Retained for compatibility with the original adapter test suite and
    the existing ``CppBacktestEngine`` stub.

    Parameters
    ----------
    cpp_module : Any
        The C++ bindings module (or a mock exposing ``NewOrder``,
        ``CancelOrder``, ``ModifyOrder`` factories).
    """

    def __init__(self, cpp_module: Any) -> None:
        self._cpp = cpp_module

    def to_engine_new_order(self, order: Order) -> Any:
        return self.to_cpp_new_order(order)

    def to_engine_cancel(self, client_order_id: int) -> Any:
        return self.to_cpp_cancel(client_order_id)

    def to_engine_modify(
        self,
        client_order_id: int,
        new_price: int | None = None,
        new_size: int | None = None,
    ) -> Any:
        return self.to_cpp_modify(client_order_id, new_price, new_size)

    # -- original names (kept stable for existing callers) ------------------

    def to_cpp_new_order(self, order: Order) -> Any:
        return self._cpp.NewOrder(
            client_order_id=order.client_order_id,
            instrument_id=order.instrument_id,
            side=_SIDE_TO_CPP_INT[order.side],
            price=order.price,
            size=order.size,
        )

    def to_cpp_cancel(self, client_order_id: int) -> Any:
        return self._cpp.CancelOrder(client_order_id=client_order_id)

    def to_cpp_modify(
        self,
        client_order_id: int,
        new_price: int | None = None,
        new_size: int | None = None,
    ) -> Any:
        return self._cpp.ModifyOrder(
            client_order_id=client_order_id,
            new_price=new_price if new_price is not None else 0,
            new_size=new_size if new_size is not None else 0,
        )


__all__ = [
    "CppOrderAdapterTemplate",
    "DefaultOrderAdapter",
    "IOrderAdapter",
    "MockOrderAdapter",
]
