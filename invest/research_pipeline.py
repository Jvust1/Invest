"""A-share research bundle: provider -> optional features -> deterministic backtest."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .pipeline import moving_average_signal, performance_summary, run_backtest


@dataclass(frozen=True)
class AShareResearchBundle:
    market: pd.DataFrame
    backtest: pd.DataFrame
    summary: dict[str, float]


def run_a_share_research_bundle(
    provider: Any,
    symbol: str,
    *,
    start_date: str = "20200101",
    end_date: str = "20500101",
    adjust: str = "qfq",
    feature_engineer: Any | None = None,
    fast: int = 20,
    slow: int = 50,
    fee_bps: float = 5.0,
) -> AShareResearchBundle:
    """Fetch one normalized frame, enrich it, then run the existing SMA baseline."""
    history = provider.history(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        adjust=adjust,
    )
    if not isinstance(history, pd.DataFrame) or history.empty:
        raise ValueError("provider returned no market data")
    if "close" not in history.columns:
        raise ValueError("normalized market data must include close")

    market = history.copy()
    if feature_engineer is not None:
        transform = getattr(feature_engineer, "transform", None)
        if not callable(transform):
            raise TypeError("feature_engineer must provide transform(frame)")
        market = transform(market)

    signal = moving_average_signal(history["close"], fast=fast, slow=slow)
    backtest = run_backtest(history["close"], signal, fee_bps=fee_bps)
    return AShareResearchBundle(
        market=market,
        backtest=backtest,
        summary=performance_summary(backtest),
    )
