"""How to plug in your own adapter.

Demonstrates the canonical adapter pattern: the strategy code is identical
to ``mean_reversion.py``; we only swap the :class:`IEventAdapter`.  This
is the same plumbing the C++ team will use to plug in their
``CppEventAdapter`` — implement what you need, reuse the rest.

The custom adapter, :class:`FrozenBookAdapter`, rewrites every book update
to a constant bid/ask, so the strategy's z-score never crosses its
threshold and *no orders are sent at all*.  This makes the effect of the
swap easy to verify: baseline fills ≫ swapped fills.
"""

from __future__ import annotations

from typing import Any

from python_wrapper_interface import (
    BacktestRunner,
    BookUpdate,
    MockBacktestEngine,
)
from python_wrapper_interface.adapters.event_adapter import (
    IEventAdapter,
    MockEventAdapter,
)
from python_wrapper_interface.examples.mean_reversion import MeanReversion


class FrozenBookAdapter(IEventAdapter):
    """Custom event adapter that emits a constant book on every update.

    Wraps a :class:`MockEventAdapter` for trade / fill / reject conversion
    and overrides ``to_book_update`` to return a frozen snapshot.  Because
    the mid never moves, the rolling-window z-score is identically zero
    and the strategy fires no orders.
    """

    def __init__(
        self,
        instrument_map: dict[str, int],
        bid_price: int = 11_000,
        ask_price: int = 11_002,
        size: int = 100,
    ) -> None:
        self._inner = MockEventAdapter(instrument_map)
        self._bid = bid_price
        self._ask = ask_price
        self._size = size

    def to_book_update(self, raw: Any) -> BookUpdate:
        clean = self._inner.to_book_update(raw)
        return BookUpdate(
            instrument_id=clean.instrument_id,
            timestamp_ns=clean.timestamp_ns,
            seq_no=clean.seq_no,
            bid_price=self._bid,
            ask_price=self._ask,
            bid_size=self._size,
            ask_size=self._size,
        )

    def to_trade(self, raw: Any):
        return self._inner.to_trade(raw)

    def to_fill(self, raw: Any):
        return self._inner.to_fill(raw)

    def to_reject(self, raw: Any):
        return self._inner.to_reject(raw)


def _run(label: str, event_adapter: IEventAdapter | None) -> int:
    engine = MockBacktestEngine(
        instrument_ids=[1001],
        num_events=5_000,
        base_price=1.10,
        volatility=0.20,
        seed=7,
        event_adapter=event_adapter,
    )
    runner = BacktestRunner(engine)
    strategy = MeanReversion()
    result = runner.run(
        strategy,
        data_path=".",
        date_range=("2024-01-01", "2024-01-02"),
    )
    n = len(result.fills_df)
    pnl = (
        result.pnl_series["cumulative_pnl"].iloc[-1]
        if not result.pnl_series.empty
        else 0.0
    )
    print(f"{label}: fills={n}  final_pnl={pnl:.4f}")
    return n


def main() -> None:
    baseline = _run("baseline (MockEventAdapter)", event_adapter=None)
    swapped = _run(
        "swapped  (FrozenBookAdapter)",
        event_adapter=FrozenBookAdapter({"INSTR_1001": 1001}),
    )

    if baseline == swapped:
        print(
            "\nWARNING: swap produced identical fill counts — adapter swap "
            "had no effect (unlikely; check your custom adapter)."
        )
    else:
        print(
            f"\nadapter swap changed fill count "
            f"({baseline} → {swapped}) — the swap had effect."
        )


if __name__ == "__main__":
    main()
