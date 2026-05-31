"""Python Strategy API for the Eurex backtester.

Public API — users should import exclusively from this package::

    from python_wrapper_interface import (
        Strategy, BacktestRunner, Result, ProgressInfo,
        BookUpdate, Trade, Fill, Reject, Order, Side, OrderStatus,
        PRICE_SCALE,
    )

Everything under ``_cpp/`` and ``adapters/`` is private.
"""

from python_wrapper_interface.engines.cpp_engine import CppBacktestEngine
from python_wrapper_interface.engines.mock_engine import MockBacktestEngine
from python_wrapper_interface.runner import BacktestRunner, ProgressInfo, Result
from python_wrapper_interface.strategy import Strategy
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

__all__ = [
    "BacktestRunner",
    "BookUpdate",
    "CppBacktestEngine",
    "Fill",
    "MockBacktestEngine",
    "Order",
    "OrderStatus",
    "PRICE_SCALE",
    "ProgressInfo",
    "Reject",
    "Result",
    "Side",
    "Strategy",
    "Trade",
]
