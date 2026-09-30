"""Yahoo Finance historical OHLCV provider."""
from __future__ import annotations

import pandas as pd

_REQUIRED = ["open", "high", "low", "close", "volume"]

def normalize_yfinance_ohlcv(data: pd.DataFrame) -> pd.DataFrame:
    """Normalize yfinance output, including single-ticker MultiIndex columns."""
    frame = data.copy()
    if isinstance(frame.columns, pd.MultiIndex):
        levels = [str(value).lower() for value in frame.columns.get_level_values(0)]
        if any(value in _REQUIRED for value in levels):
            frame.columns = frame.columns.get_level_values(0)
        else:
            frame.columns = frame.columns.get_level_values(-1)
    frame.columns = [str(column).lower().replace(" ", "_") for column in frame.columns]
    missing = set(_REQUIRED).difference(frame.columns)
    if missing:
        raise ValueError(f"yfinance data is missing columns: {sorted(missing)}")
    frame.index = pd.to_datetime(frame.index)
    if getattr(frame.index, "tz", None) is not None:
        frame.index = frame.index.tz_localize(None)
    return frame[_REQUIRED].dropna(how="all").astype(float).sort_index()

def fetch_yfinance_ohlcv(ticker: str, start=None, end=None, period: str = "max", interval: str = "1d", auto_adjust: bool = False, **kwargs) -> pd.DataFrame:
    """Download Yahoo Finance candles through the optional yfinance package."""
    try:
        import yfinance as yf
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("yfinance is optional; install the 'yfinance' extra to fetch Yahoo data") from exc
    data = yf.download(
        tickers=ticker,
        start=start,
        end=end,
        period=period,
        interval=interval,
        auto_adjust=auto_adjust,
        progress=False,
        **kwargs,
    )
    return normalize_yfinance_ohlcv(data)
