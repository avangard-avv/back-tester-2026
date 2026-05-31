"""C++ engine wrapper using pybind11 bindings (stub).

When the native ``_cpp`` module is built, this class will mirror
:class:`~python_wrapper_interface.engines.mock_engine.MockBacktestEngine` but
delegate to the C++ event loop.  Until then, construction raises a
friendly :class:`RuntimeError` directing the user to
:class:`MockBacktestEngine`.

The class accepts the same adapter constructor arguments as the mock
engine — when the C++ bindings land, the only thing that changes is which
concrete adapters get plugged in.
"""

from __future__ import annotations

import logging

from python_wrapper_interface.adapters.event_adapter import (
    CppEventAdapterTemplate,
    IEventAdapter,
)
from python_wrapper_interface.adapters.order_adapter import (
    CppOrderAdapterTemplate,
    IOrderAdapter,
)
from python_wrapper_interface.interfaces import (
    IBacktestEngine,
    IMarketDataFeed,
    IOrderGateway,
)
from python_wrapper_interface.runner import ProgressInfo, Result
from python_wrapper_interface.strategy import Strategy

logger = logging.getLogger(__name__)

try:
    from python_wrapper_interface import _cpp as _cpp_module

    _CPP_AVAILABLE = hasattr(_cpp_module, "BacktestEngine")
except ImportError:  # pragma: no cover — defensive
    _cpp_module = None
    _CPP_AVAILABLE = False


class CppBacktestEngine(IBacktestEngine):
    """Production engine backed by the pybind11-bound C++ event loop.

    Parameters
    ----------
    event_adapter : IEventAdapter | None
        Converts C++ events to clean dataclasses.  Defaults to
        :class:`CppEventAdapterTemplate` — the C++ team should plug in
        their filled-in concrete adapter here.
    order_adapter : IOrderAdapter | None
        Converts clean orders to C++ commands.  Defaults to
        :class:`CppOrderAdapterTemplate`.

    Raises
    ------
    RuntimeError
        On construction whenever the C++ bindings are not yet available.
        Use :class:`MockBacktestEngine` in the meantime.
    """

    def __init__(
        self,
        event_adapter: IEventAdapter | None = None,
        order_adapter: IOrderAdapter | None = None,
    ) -> None:
        if not _CPP_AVAILABLE:
            raise RuntimeError(
                "C++ bindings not yet available — use MockBacktestEngine "
                "from python_wrapper_interface for now. Once the C++ team "
                "ships pybind11 bindings: (1) fill in "
                "CppEventAdapterTemplate, (2) fill in "
                "CppOrderAdapterTemplate, (3) re-instantiate "
                "CppBacktestEngine(event_adapter=..., order_adapter=...)."
            )

        self._event_adapter: IEventAdapter = (
            event_adapter or CppEventAdapterTemplate(instrument_map={})
        )
        self._order_adapter: IOrderAdapter = (
            order_adapter or CppOrderAdapterTemplate(cpp_module=_cpp_module)
        )
        self._cpp_engine = _cpp_module.BacktestEngine()  # type: ignore[union-attr]
        self._strategy: Strategy | None = None

    # The remaining IBacktestEngine methods become real once the C++
    # bindings land.  They are stubbed defensively so the class still
    # satisfies the ABC contract for static checkers.

    def load(self, data_path: str, date_range: tuple[str, str]) -> None:  # pragma: no cover
        raise NotImplementedError("C++ bindings not yet available.")

    def step(self) -> bool:  # pragma: no cover
        raise NotImplementedError("C++ bindings not yet available.")

    def register_strategy(self, strategy: Strategy) -> None:  # pragma: no cover
        self._strategy = strategy

    def order_gateway(self) -> IOrderGateway:  # pragma: no cover
        raise NotImplementedError("C++ bindings not yet available.")

    def market_data_feed(self) -> IMarketDataFeed:  # pragma: no cover
        raise NotImplementedError("C++ bindings not yet available.")

    def progress(self) -> ProgressInfo:  # pragma: no cover
        return ProgressInfo()

    def build_result(self) -> Result:  # pragma: no cover
        raise NotImplementedError("C++ bindings not yet available.")
