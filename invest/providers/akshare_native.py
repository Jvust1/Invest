"""Optional AKShare package adapter for A-share research.

Upstream: akfamily/akshare @
fac1e50ebf9b907960d6aab4c3df658559689f39 (MIT).

The existing akshare_eastmoney module remains the dependency-light direct
history fallback. This module uses the upstream Python package when installed,
which gives Invest a broader A-share surface without coupling core imports to
AKShare.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


_HISTORY_COLUMNS = {
    "日期": "date",
    "股票代码": "symbol",
    "开盘": "open",
    "收盘": "close",
    "最高": "high",
    "最低": "low",
    "成交量": "volume",
    "成交额": "turnover",
    "振幅": "amplitude",
    "涨跌幅": "change_pct",
    "涨跌额": "change",
    "换手率": "turnover_rate",
}

_SPOT_COLUMNS = {
    "代码": "symbol",
    "名称": "name",
    "最新价": "last",
    "涨跌幅": "change_pct",
    "涨跌额": "change",
    "成交量": "volume",
    "成交额": "turnover",
    "振幅": "amplitude",
    "最高": "high",
    "最低": "low",
    "今开": "open",
    "昨收": "previous_close",
    "量比": "volume_ratio",
    "换手率": "turnover_rate",
    "市盈率-动态": "pe_dynamic",
    "市净率": "pb",
    "总市值": "market_cap",
    "流通市值": "float_market_cap",
}


def _normalize_frame(frame: pd.DataFrame, columns: dict[str, str]) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        raise TypeError("AKShare provider must return pandas.DataFrame")
    result = frame.rename(columns=columns).copy()
    keep = [target for source, target in columns.items() if source in frame.columns]
    result = result.loc[:, keep]
    if "symbol" in result.columns:
        result["symbol"] = result["symbol"].astype(str).str.zfill(6)
    return result


def normalize_history(frame: pd.DataFrame) -> pd.DataFrame:
    result = _normalize_frame(frame, _HISTORY_COLUMNS)
    if "date" in result.columns:
        result["date"] = pd.to_datetime(result["date"], errors="coerce")
        result = result.dropna(subset=["date"]).set_index("date").sort_index()
    numeric = [
        name
        for name in (
            "open", "close", "high", "low", "volume", "turnover",
            "amplitude", "change_pct", "change", "turnover_rate",
        )
        if name in result.columns
    ]
    if numeric:
        result[numeric] = result[numeric].apply(pd.to_numeric, errors="coerce")
    return result


def normalize_spot(frame: pd.DataFrame) -> pd.DataFrame:
    result = _normalize_frame(frame, _SPOT_COLUMNS)
    numeric = [name for name in result.columns if name not in {"symbol", "name"}]
    if numeric:
        result[numeric] = result[numeric].apply(pd.to_numeric, errors="coerce")
    return result


class AKShareProvider:
    """Small, injected AKShare boundary for history + A-share spot snapshots."""

    name = "akshare"

    def __init__(self, module: Any | None = None) -> None:
        if module is None:
            try:
                import akshare as module
            except ImportError as exc:
                raise RuntimeError(
                    "AKShare is optional; install Invest with the 'akshare' extra"
                ) from exc
        for func_name in ("stock_zh_a_hist", "stock_zh_a_spot_em"):
            if not callable(getattr(module, func_name, None)):
                raise TypeError(f"AKShare module must provide {func_name}()")
        self._ak = module

    def history(
        self,
        symbol: str,
        *,
        start_date: str = "19700101",
        end_date: str = "20500101",
        period: str = "daily",
        adjust: str = "",
    ) -> pd.DataFrame:
        raw = self._ak.stock_zh_a_hist(
            symbol=str(symbol).zfill(6),
            period=period,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
        return normalize_history(raw)

    def spot(self) -> pd.DataFrame:
        return normalize_spot(self._ak.stock_zh_a_spot_em())
