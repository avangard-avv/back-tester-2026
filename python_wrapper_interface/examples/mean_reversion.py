"""Mean-reversion strategy on the synthetic Eurex mock engine.

Run this script to produce a matplotlib PnL plot and a fills-on-mid
overlay without any C++ dependency.

Strategy logic
--------------
* Maintain a rolling window of mids (size 100).
* Compute the z-score of the current mid against this window.
* If ``z > 1.5`` send a SELL limit at best bid (fade the up-move).
* If ``z < -1.5`` send a BUY limit at best ask (fade the down-move).
* Cancel any live order older than 200 ticks.
"""

from __future__ import annotations

import logging
from collections import deque

# Public package imports only — strategies must not touch ``adapters`` or
# ``engines`` directly.  Engine setup happens below in ``main()``.
from python_wrapper_interface import (
    BacktestRunner,
    BookUpdate,
    Fill,
    MockBacktestEngine,
    Side,
    Strategy,
)

logger = logging.getLogger(__name__)


class MeanReversion(Strategy):
    """Z-score mean-reversion strategy.

    Parameters
    ----------
    window : int
        Rolling-window length for the mid-price z-score.
    z_entry : float
        Absolute z-score threshold to enter a fade.
    max_age_ticks : int
        Cancel live orders older than this many ticks.
    size : int
        Order size in contracts.
    """

    def __init__(
        self,
        window: int = 100,
        z_entry: float = 1.5,
        max_age_ticks: int = 200,
        size: int = 1,
    ) -> None:
        super().__init__()
        self._window = window
        self._z_entry = z_entry
        self._max_age = max_age_ticks
        self._size = size

        self._mids: deque[float] = deque(maxlen=window)
        self._sum: float = 0.0
        self._sum_sq: float = 0.0
        self._tick: int = 0
        self._live: dict[int, int] = {}  # client_order_id → tick when sent

    def on_book_update(self, update: BookUpdate) -> None:
        self._tick += 1
        if update.bid_price <= 0 or update.ask_price <= 0:
            return
        mid = (update.bid_price + update.ask_price) / 2.0

        if len(self._mids) == self._window:
            old = self._mids[0]
            self._sum -= old
            self._sum_sq -= old * old
        self._mids.append(mid)
        self._sum += mid
        self._sum_sq += mid * mid

        self._cancel_stale()

        if len(self._mids) < self._window:
            return

        n = len(self._mids)
        mean = self._sum / n
        var = max(self._sum_sq / n - mean * mean, 0.0)
        if var <= 0:
            return
        std = var ** 0.5
        z = (mid - mean) / std

        if z > self._z_entry:
            cid = self.send_order(
                update.instrument_id, Side.SELL, update.bid_price, self._size,
            )
            self._live[cid] = self._tick
        elif z < -self._z_entry:
            cid = self.send_order(
                update.instrument_id, Side.BUY, update.ask_price, self._size,
            )
            self._live[cid] = self._tick

    def on_fill(self, fill: Fill) -> None:
        self._live.pop(fill.client_order_id, None)
        print(
            f"FILL cid={fill.client_order_id} {fill.side.name} "
            f"{fill.fill_size}@{fill.fill_price}"
        )

    def _cancel_stale(self) -> None:
        stale = [
            cid for cid, sent_tick in self._live.items()
            if self._tick - sent_tick > self._max_age
        ]
        for cid in stale:
            self.cancel_order(cid)
            self._live.pop(cid, None)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    engine = MockBacktestEngine(
        instrument_ids=[1001],
        num_events=5_000,
        base_price=1.10,
        volatility=0.20,
        seed=7,
    )
    runner = BacktestRunner(engine)
    strategy = MeanReversion()

    result = runner.run(
        strategy,
        data_path=".",
        date_range=("2024-01-01", "2024-01-02"),
    )

    print(f"\ntotal fills: {len(result.fills_df)}")
    if not result.pnl_series.empty:
        final_pnl = result.pnl_series["cumulative_pnl"].iloc[-1]
        print(f"final PnL: {final_pnl:.4f}")
    else:
        print("final PnL: 0.0 (no fills)")

    # Default visualizer (matplotlib) for the PnL curve.
    result.plot_pnl()

    # Explicit visualizer for the fills overlay.
    from python_wrapper_interface.adapters.viz_adapter import MatplotlibVisualizer

    import matplotlib.pyplot as plt

    MatplotlibVisualizer(show=False).plot_fills_on_mid(result)
    plt.show()


if __name__ == "__main__":
    main()
