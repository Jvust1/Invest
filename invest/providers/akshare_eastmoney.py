"""Small A-share daily-history provider derived from AKShare.

Source reference: akfamily/akshare at commit
0191689d57c667b7c7a198fd0cf97316837ef311, module
akshare/stock_feature/stock_hist_em.py (MIT License).

This adapter keeps only the stable Eastmoney history endpoint contract and
returns Invest's English column names. It does not bundle the full AKShare
package or promise that an upstream data endpoint will remain available.
"""
from __future__ import annotations

import pandas as pd
import requests

_ENDPOINT = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
_FIELDS = "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61,f116"
_PERIODS = {"daily": "101", "weekly": "102", "monthly": "103"}
_ADJUSTMENTS = {"": "0", "qfq": "1", "hfq": "2"}

def fetch_a_share_daily(
    symbol: str,
    start_date: str = "19700101",
    end_date: str = "20500101",
    period: str = "daily",
    adjust: str = "",
    timeout: float = 15,
) -> pd.DataFrame:
    """Fetch one A-share history and normalize it for Invest.

    symbol is a six-digit code. Dates use YYYYMMDD. The returned frame is
    indexed by date and has OHLCV plus turnover columns.
    """
    symbol = str(symbol).zfill(6)
    if period not in _PERIODS:
        raise ValueError(f"period must be one of {sorted(_PERIODS)}")
    if adjust not in _ADJUSTMENTS:
        raise ValueError(f"adjust must be one of {sorted(_ADJUSTMENTS)}")
    market = "1" if symbol.startswith("6") else "0"
    params = {
        "fields1": "f1,f2,f3,f4,f5,f6",
        "fields2": _FIELDS,
        "ut": "7eea3edcaed734bea9cbfc24409ed989",
        "klt": _PERIODS[period],
        "fqt": _ADJUSTMENTS[adjust],
        "secid": f"{market}.{symbol}",
        "beg": start_date,
        "end": end_date,
    }
    response = requests.get(_ENDPOINT, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    rows = (payload.get("data") or {}).get("klines") or []
    columns = ["date", "open", "close", "high", "low", "volume",
               "turnover", "amplitude", "change_pct", "change",
               "turnover_rate", "symbol"]
    if not rows:
        return pd.DataFrame(columns=columns[1:]).rename_axis("date")
    # AKShare's pinned source adds symbol after parsing eleven kline values;
    # f116 in the request does not make symbol an extra returned CSV column.
    frame = pd.DataFrame([row.split(",") for row in rows], columns=columns[:-1])
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    numeric = [c for c in columns if c not in {"date", "symbol"}]
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="coerce")
    frame["symbol"] = symbol
    return frame.set_index("date").sort_index()
