# `python_wrapper_interface` — Python Strategy API for the Eurex backtester

What this is
------------
A pure-Python event-driven backtester for Eurex EUR/USD futures and
options.  It ships with a synthetic data source and a mock matching
engine so you can write and test strategies **today**, with no C++
build.  When the C++ engine lands later, only the adapter wiring
changes; your strategy code stays the same.

Install + 30-second quick start
-------------------------------
```bash
pip install -e .             # from the repo root
python -m python_wrapper_interface.examples.mean_reversion
```
This runs the bundled mean-reversion strategy on 5 000 synthetic L3
events, prints fills, and opens a matplotlib PnL plot.

Architecture in one diagram
---------------------------
```
SyntheticDataAdapter           (yields raw L3-like Add/Cancel/Trade events)
        │
        ▼
MockBacktestEngine             (maintains an in-memory LOB,
        │                       emits "C++-style" raw events)
        ▼
MockEventAdapter               (raw  →  clean dataclass)
        │
        ▼
Strategy.on_book_update(...)   (clean BookUpdate / Trade / Fill / Reject)
        │
        ▼
strategy.send_order(...)       (clean Order)
        │
        ▼
MockOrderAdapter               (clean  →  raw command dict)
        │
        ▼
MockBacktestEngine             (resting book, fill simulation)
        │
        ▼
MockEventAdapter               (raw Fill / Reject  →  clean)
        │
        ▼
Strategy.on_fill(...) / on_reject(...)
```
Any value that crosses the engine ↔ strategy boundary passes through an
adapter.  The strategy never sees a raw type; the engine never sees an
`Order` directly.

The three adapter families
--------------------------
**A. Event + Order adapters** (`adapters/event_adapter.py`,
`adapters/order_adapter.py`)
* `IEventAdapter` — engine→strategy event conversion.
  Reference impl: `MockEventAdapter`. C++ stub: `CppEventAdapterTemplate`.
* `IOrderAdapter` — strategy→engine command conversion.
  Reference impl: `MockOrderAdapter`. C++ stub: `CppOrderAdapterTemplate`.

**B. Data adapter** (`adapters/data_adapter.py`)
* `IDataAdapter` — yields raw L3 events (`RawAdd` / `RawCancel` /
  `RawModify` / `RawTradeTick`).
  Reference impl: `SyntheticDataAdapter` (deterministic GBM walk).
  Stub for HW1/HW2's historical replay: `NdjsonDataAdapterTemplate`.

**C. Visualization adapter** (`adapters/viz_adapter.py`)
* `IResultVisualizer` — renders a `Result` to a figure.
  Reference impl: `MatplotlibVisualizer`. Stub: `PlotlyVisualizerTemplate`.

For the C++ team: how to plug in your engine
--------------------------------------------
The mock pipeline is a working reference for the production wiring.
Concrete checklist:

1. **Implement `CppEventAdapterTemplate` methods** in
   `adapters/event_adapter.py` using your pybind11-bound structs.  Each
   method has a NumPy-style docstring listing the expected C++ field
   names (`raw.bid_px_mantissa`, `raw.header.sequence`, etc.).  Use
   `MockEventAdapter` as a reference — it performs exactly the same
   conversions on dataclasses that mimic your C++ shapes.

2. **Implement `CppOrderAdapterTemplate` methods** in
   `adapters/order_adapter.py` using your `cpp_module.NewOrder(...)` /
   `CancelOrder(...)` / `ModifyOrder(...)` factories.

3. **Optionally implement `NdjsonDataAdapterTemplate`** if you want
   historical replay (HW1/HW2 NDJSON format described in the
   docstring).  For live or in-memory data, point the engine at any
   `IDataAdapter` you like.

4. **Instantiate `CppBacktestEngine`** with your filled-in adapters:
   ```python
   engine = CppBacktestEngine(
       event_adapter=CppEventAdapter(instrument_map),
       order_adapter=CppOrderAdapter(cpp_module),
   )
   runner = BacktestRunner(engine)
   ```
   The strategy code is unchanged.

Writing your own strategy
-------------------------
```python
from python_wrapper_interface import (
    BacktestRunner, MockBacktestEngine, Side, Strategy,
)

class BuyEveryTick(Strategy):
    def on_book_update(self, update):
        if update.ask_price > 0:
            self.send_order(update.instrument_id, Side.BUY, update.ask_price, 1)
    def on_fill(self, fill):
        print(fill)

engine = MockBacktestEngine(num_events=1_000, seed=42)
result = BacktestRunner(engine).run(
    BuyEveryTick(),
    data_path=".",
    date_range=("2024-01-01", "2024-01-02"),
)
result.plot_pnl()
```

Plugging in your own adapter
----------------------------
See `examples/custom_adapter_example.py`: a `FrozenBookAdapter` wraps
`MockEventAdapter`, overrides only `to_book_update`, and the
mean-reversion strategy now fires zero orders.  This is the same shape
of plumbing the C++ team will use — only the override surface differs.

Running tests
-------------
```bash
pytest python_wrapper_interface/tests/ -v
```
Eighty tests cover types, the strategy lifecycle, the runner, the mock
engine, all three adapter families (round-trip + swap + template-
raises-NotImplementedError), and end-to-end smoke runs.
