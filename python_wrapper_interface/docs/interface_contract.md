# Interface Contract — Groups 1/2/3/4

This document is the single source of truth for field names, types, and encoding
conventions shared across the four groups of the Eurex EUR/USD backtester.

## Common Fields

| Field              | Type     | Description                                              |
|--------------------|----------|----------------------------------------------------------|
| `instrument_id`    | `uint32` | Eurex product identifier (e.g. FGBL future = 1001)       |
| `timestamp_ns`     | `int64`  | Nanoseconds since Unix epoch (1970-01-01T00:00:00Z)      |
| `order_id`         | `uint64` | Exchange-assigned unique order identifier                 |
| `client_order_id`  | `uint64` | Strategy-assigned order identifier (Group 4 only)        |
| `seq_no`           | `uint64` | Per-instrument monotonic sequence number (market data)    |
| `trading_engine_id`| `uint32` | Eurex matching-engine partition (T7 engine id)            |

## Price Encoding

All prices are encoded as **scaled integers** with a fixed scale factor.

| Constant          | Value   | Meaning                                        |
|-------------------|---------|-------------------------------------------------|
| `PRICE_SCALE`     | `10000` | 1 price unit = 0.0001; e.g. 1.1234 → `11234`   |
| `PRICE_TICK_SIZE` | `1`     | Minimum price increment in scaled units          |

### Alternative Price Format (Group 2 Legacy)

Some Group 2 messages encode prices as `{mantissa: int64, exponent: int8}`.
Conversion: `scaled_price = mantissa * 10^(SCALE_DIGITS + exponent)` where
`SCALE_DIGITS = 4`.

## Side Encoding

| Group   | Format     | BUY   | SELL  |
|---------|------------|-------|-------|
| Group 1 | `uint8`    | `1`   | `2`   |
| Group 2 | `string`   | `"B"` | `"S"` |
| Group 4 | `enum Side`| `BUY` | `SELL` |

## Order Status

```
PENDING → ACKED → FILLED | PARTIALLY_FILLED | CANCELLED | REJECTED
```

## Market Data Messages

### BookUpdate (Group 2 → Group 4)

| Field            | C++ type   | Python type | Notes                          |
|------------------|------------|-------------|--------------------------------|
| `instrument_id`  | `uint32`   | `int`       |                                |
| `timestamp_ns`   | `int64`    | `int`       |                                |
| `seq_no`         | `uint64`   | `int`       | Monotonic per instrument       |
| `bid_price`      | `int64`    | `int`       | Scaled by PRICE_SCALE          |
| `ask_price`      | `int64`    | `int`       | Scaled by PRICE_SCALE          |
| `bid_size`       | `uint32`   | `int`       |                                |
| `ask_size`       | `uint32`   | `int`       |                                |

### Trade (Group 2 → Group 4)

| Field            | C++ type   | Python type | Notes                          |
|------------------|------------|-------------|--------------------------------|
| `instrument_id`  | `uint32`   | `int`       |                                |
| `timestamp_ns`   | `int64`    | `int`       |                                |
| `seq_no`         | `uint64`   | `int`       |                                |
| `price`          | `int64`    | `int`       | Scaled by PRICE_SCALE          |
| `size`           | `uint32`   | `int`       |                                |
| `aggressor_side` | `uint8`    | `Side`      | Side of the aggressor          |

## Order Messages

### NewOrder (Group 4 → Group 1)

| Field              | C++ type | Python type | Notes                        |
|--------------------|----------|-------------|------------------------------|
| `client_order_id`  | `uint64` | `int`       | Assigned by BacktestRunner   |
| `instrument_id`    | `uint32` | `int`       |                              |
| `side`             | `uint8`  | `Side`      | 1=BUY, 2=SELL                |
| `price`            | `int64`  | `int`       | Scaled by PRICE_SCALE        |
| `size`             | `uint32` | `int`       |                              |

### Fill (Group 1 → Group 4)

| Field              | C++ type | Python type | Notes                        |
|--------------------|----------|-------------|------------------------------|
| `order_id`         | `uint64` | `int`       | Exchange-assigned             |
| `client_order_id`  | `uint64` | `int`       |                              |
| `instrument_id`    | `uint32` | `int`       |                              |
| `timestamp_ns`     | `int64`  | `int`       |                              |
| `side`             | `uint8`  | `Side`      |                              |
| `fill_price`       | `int64`  | `int`       | Scaled                       |
| `fill_size`        | `uint32` | `int`       |                              |

### Reject (Group 1 → Group 4)

| Field              | C++ type | Python type | Notes                        |
|--------------------|----------|-------------|------------------------------|
| `order_id`         | `uint64` | `int`       |                              |
| `client_order_id`  | `uint64` | `int`       |                              |
| `instrument_id`    | `uint32` | `int`       |                              |
| `timestamp_ns`     | `int64`  | `int`       |                              |
| `reason`           | `string` | `str`       | Human-readable reject reason |
