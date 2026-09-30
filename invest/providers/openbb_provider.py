"""Optional OpenBB data-platform adapter for Invest.

Upstream: OpenBB-finance/OpenBB @
bbf1ab2020c2ce025333db56ece2036190fcad9c (Apache-2.0, current repository LICENSE).

The adapter keeps OpenBB optional and normalizes the public
obb.equity.price.historical(...).to_dataframe() path into Invest's OHLCV shape.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


_COLUMN_ALIASES = {
    "date": "date",
    "datetime": "date",
    "timestamp": "date",
    "open": "open",
    "high": "high",
    "low": "low",
    "close": "close",
    "adj_close": "adj_close",
    "adjusted_close": "adj_close",
    "volume": "volume",
}


def normalize_openbb_ohlcv(frame: pd.DataFrame, *, symbol: str = "") -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("OpenBB output must convert to pandas.DataFrame")
    result = frame.copy()
    result.columns = [str(column).strip().casefold() for column in result.columns]
    result = result.rename(columns={key: value for key, value in _COLUMN_ALIASES.items() if key in result.columns})

    if "date" not in result.columns:
        index_name = str(result.index.name or "").casefold()
        if index_name in {"date", "datetime", "timestamp"} or isinstance(result.index, pd.DatetimeIndex):
            result = result.reset_index()
            result = result.rename(columns={result.columns[0]: "date"})

    keep = [name for name in ("date", "open", "high", "low", "close", "adj_close", "volume") if name in result.columns]
    if "close" not in keep:
        raise ValueError("OpenBB historical output is missing close")
    result = result.loc[:, keep].copy()
    if "date" in result.columns:
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        result = result.dropna(subset=["date"]).set_index("date").sort_index()
    for name in ("open", "high", "low", "close", "adj_close", "volume"):
        if name in result.columns:
            result[name] = pd.to_numeric(result[name], errors="coerce")
    if symbol:
        result["symbol"] = str(symbol)
    return result


class OpenBBProvider:
    name = "openbb"

    def __init__(self, obb: Any | None = None) -> None:
        if obb is None:
            try:
                from openbb import obb
            except ImportError as exc:
                raise RuntimeError("OpenBB is optional; install Invest with the 'openbb' extra") from exc
        historical = getattr(getattr(getattr(obb, "equity", None), "price", None), "historical", None)
        if not callable(historical):
            raise TypeError("OpenBB client must provide obb.equity.price.historical()")
        self._obb = obb

    def history(self, symbol: str, **kwargs: Any) -> pd.DataFrame:
        ticker = str(symbol).strip()
        if not ticker:
            raise ValueError("symbol cannot be empty")
        output = self._obb.equity.price.historical(ticker, **kwargs)
        to_dataframe = getattr(output, "to_dataframe", None)
        if not callable(to_dataframe):
            raise TypeError("OpenBB result must provide to_dataframe()")
        return normalize_openbb_ohlcv(to_dataframe(), symbol=ticker)
