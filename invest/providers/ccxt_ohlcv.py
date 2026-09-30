"""CCXT OHLCV provider for crypto exchange data."""
from __future__ import annotations

import pandas as pd

_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]

def normalize_ccxt_ohlcv(rows) -> pd.DataFrame:
    """Normalize CCXT's six-column OHLCV payload into Invest's indexed schema."""
    frame = pd.DataFrame(list(rows))
    if frame.empty or frame.shape[1] < 6:
        raise ValueError("CCXT OHLCV payload must contain six columns")
    frame = frame.iloc[:, :6].copy()
    frame.columns = _COLUMNS
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], unit="ms", utc=True).dt.tz_localize(None)
    frame = frame.set_index("timestamp").sort_index()
    return frame[["open", "high", "low", "close", "volume"]].astype(float)

def fetch_ccxt_ohlcv(exchange_id: str, symbol: str, timeframe: str = "1d", since=None, limit: int = 1000, params=None) -> pd.DataFrame:
    """Fetch OHLCV through any CCXT exchange class."""
    try:
        import ccxt
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("CCXT is optional; install the 'ccxt' extra to fetch crypto data") from exc
    exchange_type = getattr(ccxt, exchange_id, None)
    if exchange_type is None:
        raise ValueError(f"unknown CCXT exchange: {exchange_id}")
    exchange = exchange_type({"enableRateLimit": True})
    rows = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit, params=params or {})
    return normalize_ccxt_ohlcv(rows)
