"""Technical feature adapters based on Stockstats."""
from __future__ import annotations

import pandas as pd

from ._vendor import load_vendor

def add_stockstats_features(ohlcv: pd.DataFrame, window: int = 14) -> pd.DataFrame:
    """Add RSI, MACD and Bollinger features to an OHLCV frame."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(ohlcv.columns)
    if missing:
        raise ValueError(f"missing OHLCV columns: {sorted(missing)}")
    if window <= 0:
        raise ValueError("window must be positive")
    load_vendor("stockstats", module="stockstats")
    from stockstats import StockDataFrame
    frame = StockDataFrame.retype(ohlcv.copy())
    frame[f"rsi_{window}"]
    frame["macd"]
    frame["boll"]
    return pd.DataFrame({
        **{column: ohlcv[column] for column in ohlcv.columns},
        f"rsi_{window}": frame[f"rsi_{window}"],
        "macd": frame["macd"],
        "boll": frame["boll"],
    }, index=ohlcv.index)
