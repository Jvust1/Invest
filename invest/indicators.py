"""Optional technical-analysis feature adapter for Invest.

Upstream: bukosabino/ta @
a890410710a6e483c9ba08da7f3dd5089e4b9dff (MIT).

This module produces research features only. It does not emit trade orders or
portfolio recommendations.
"""
from __future__ import annotations

from typing import Any

import pandas as pd


_REQUIRED_COLUMNS = ("high", "low", "close")


class TAFeatureEngineer:
    """Add a compact set of widely used indicators through injected ta classes."""

    def __init__(
        self,
        *,
        rsi_cls: Any,
        macd_cls: Any,
        bollinger_cls: Any,
        atr_cls: Any,
    ) -> None:
        for name, cls in {
            "rsi_cls": rsi_cls,
            "macd_cls": macd_cls,
            "bollinger_cls": bollinger_cls,
            "atr_cls": atr_cls,
        }.items():
            if not callable(cls):
                raise TypeError(f"{name} must be callable")
        self._rsi_cls = rsi_cls
        self._macd_cls = macd_cls
        self._bollinger_cls = bollinger_cls
        self._atr_cls = atr_cls

    def transform(self, frame: pd.DataFrame) -> pd.DataFrame:
        if not isinstance(frame, pd.DataFrame):
            raise TypeError("frame must be pandas.DataFrame")
        missing = [name for name in _REQUIRED_COLUMNS if name not in frame.columns]
        if missing:
            raise ValueError(f"missing required columns: {', '.join(missing)}")
        result = frame.copy()

        rsi = self._rsi_cls(close=result["close"], window=14)
        result["ta_rsi_14"] = rsi.rsi()

        macd = self._macd_cls(close=result["close"])
        result["ta_macd"] = macd.macd()
        result["ta_macd_signal"] = macd.macd_signal()
        result["ta_macd_diff"] = macd.macd_diff()

        bands = self._bollinger_cls(close=result["close"], window=20, window_dev=2)
        result["ta_bb_mid"] = bands.bollinger_mavg()
        result["ta_bb_high"] = bands.bollinger_hband()
        result["ta_bb_low"] = bands.bollinger_lband()

        atr = self._atr_cls(
            high=result["high"],
            low=result["low"],
            close=result["close"],
            window=14,
        )
        result["ta_atr_14"] = atr.average_true_range()
        return result


def create_ta_feature_engineer() -> TAFeatureEngineer:
    """Create the upstream-backed feature engineer lazily."""
    try:
        from ta.momentum import RSIIndicator
        from ta.trend import MACD
        from ta.volatility import AverageTrueRange, BollingerBands
    except ImportError as exc:
        raise RuntimeError(
            "ta is optional; install Invest with the 'technical' extra before enabling indicators"
        ) from exc

    return TAFeatureEngineer(
        rsi_cls=RSIIndicator,
        macd_cls=MACD,
        bollinger_cls=BollingerBands,
        atr_cls=AverageTrueRange,
    )
