"""VN.py interoperability helpers."""
from __future__ import annotations

import pandas as pd

_REQUIRED = {"open", "high", "low", "close", "volume"}

def to_vnpy_records(history: pd.DataFrame, symbol: str) -> list[dict]:
    """Convert an indexed OHLCV frame to VN.py-compatible bar records."""
    missing = _REQUIRED.difference(history.columns)
    if missing:
        raise ValueError(f"history is missing columns: {sorted(missing)}")
    frame = history.copy()
    frame.index = pd.to_datetime(frame.index)
    records = []
    for timestamp, row in frame.sort_index().iterrows():
        records.append({
            "symbol": symbol,
            "datetime": timestamp.to_pydatetime(),
            "open_price": float(row["open"]),
            "high_price": float(row["high"]),
            "low_price": float(row["low"]),
            "close_price": float(row["close"]),
            "volume": float(row["volume"]),
        })
    return records

def to_vnpy_bars(history: pd.DataFrame, symbol: str, exchange: str = "SSE", gateway_name: str = "INVEST"):
    """Build VN.py BarData objects when the optional vnpy package is installed."""
    try:
        from vnpy.trader.constant import Exchange, Interval
        from vnpy.trader.object import BarData
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("VN.py is optional; install the 'vnpy' extra to build BarData") from exc
    exchange_enum = Exchange[exchange]
    return [
        BarData(
            gateway_name=gateway_name,
            symbol=record["symbol"],
            exchange=exchange_enum,
            datetime=record["datetime"],
            interval=Interval.DAILY,
            volume=record["volume"],
            open_price=record["open_price"],
            high_price=record["high_price"],
            low_price=record["low_price"],
            close_price=record["close_price"],
        )
        for record in to_vnpy_records(history, symbol)
    ]
