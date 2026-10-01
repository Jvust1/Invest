"""A-share research bundle: provider -> optional features -> deterministic backtest."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from .pipeline import moving_average_signal, performance_summary, run_backtest


@dataclass(frozen=True)
class AShareResearchBundle:
    market: pd.DataFrame
    backtest: pd.DataFrame
    summary: dict[str, float]
    optimization: Any | None = None
    research_split: dict[str, Any] | None = None


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
    optimization_trials: int | None = None,
    optimization_splits: int = 3,
    training_fraction: float = 0.7,
    optimization_seed: int = 0,
    optimization_study: Any | None = None,
) -> AShareResearchBundle:
    """Fetch once, optionally tune only an earlier prefix, then evaluate later.

    Optuna search is explicit opt-in and uses an in-memory study by default.
    The later evaluation is exploratory research, not a certified frozen
    holdout or the full A-share cash/execution engine in invest.engine.
    """
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

    optimization = None
    research_split = None
    if optimization_trials is not None:
        from .optuna_walkforward import _validated_close, optimize_sma_walkforward
        close = _validated_close(history['close'])
        if (isinstance(training_fraction, bool) or not np.isfinite(training_fraction)
                or not 0 < training_fraction < 1):
            raise ValueError('training_fraction must be finite and strictly between zero and one')
        # Decimal(str(...)) avoids truncating 360 * 0.7 to 251 because of
        # binary floating-point rounding at an exact observation boundary.
        cutoff = int(Decimal(str(training_fraction)) * len(close))
        if len(close) - cutoff < 20:
            raise ValueError('later evaluation requires at least 20 observations')
        optimization = optimize_sma_walkforward(
            close.iloc[:cutoff], n_trials=optimization_trials, splits=optimization_splits,
            fee_bps=fee_bps, seed=optimization_seed, study=optimization_study)
        fast, slow = optimization.params['fast'], optimization.params['slow']
        research_split = {
            'mode': 'EXPLORATORY_PREFIX_SEARCH_LATER_EVALUATION',
            'training_observations': cutoff, 'evaluation_observations': len(close) - cutoff,
            'training_start': str(close.index[0]), 'training_end': str(close.index[cutoff - 1]),
            'evaluation_start': str(close.index[cutoff]), 'evaluation_end': str(close.index[-1]),
            'frozen_holdout_opened': False,
            'scope': 'close_to_close_signal_research_not_a_share_cash_execution',
            'position_boundary': 'continuation_of_prior_signal; no artificial liquidation at split',
        }
    elif optimization_study is not None:
        raise ValueError('optimization_study requires optimization_trials')
    signal = moving_average_signal(history["close"], fast=fast, slow=slow)
    backtest = run_backtest(history["close"], signal, fee_bps=fee_bps)
    if research_split is not None:
        backtest = backtest.iloc[research_split['training_observations']:].copy()
        backtest['equity'] = (1 + backtest['strategy_return']).cumprod()

    from copy import deepcopy
    for key in ("market_data", "duckdb_replay"):
        if key in history.attrs:
            market.attrs[key] = deepcopy(history.attrs[key])
            backtest.attrs[key] = deepcopy(history.attrs[key])
    return AShareResearchBundle(
        market=market,
        backtest=backtest,
        summary=performance_summary(backtest),
        optimization=optimization,
        research_split=research_split,
    )
