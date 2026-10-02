"""Optuna adapter for time-series-safe SMA parameter search.

Upstream: optuna/optuna @
5c8e50d85b77dd5a1fd7e26e21f63debc81d6016 (MIT).
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

import numpy as np
import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from .pipeline import moving_average_signal, performance_summary, run_backtest


@dataclass(frozen=True)
class OptimizationResult:
    params: dict[str, int]
    score: float
    fold_scores: tuple[float, ...]
    trials: tuple[dict[str, Any], ...] = ()
    seed: int | None = None
    optimizer_version: str | None = None
    training_fingerprint: str = ''
    splits: int = 0
    fee_bps: float = 0.0
    score_metric: str = 'annualized_arithmetic_sharpe_zero_risk_free'


def _validated_close(close: pd.Series) -> pd.Series:
    series = pd.Series(close, dtype="float64")
    if (series.empty or not np.isfinite(series).all() or (series <= 0).any()
            or not series.index.is_unique or not series.index.is_monotonic_increasing):
        raise ValueError("history must contain finite positive prices in unique chronological order")
    return series


def _walkforward_score(
    close: pd.Series,
    *,
    fast: int,
    slow: int,
    fee_bps: float,
    splits: int,
) -> tuple[float, tuple[float, ...]]:
    series = _validated_close(close)
    if len(series) < max(slow * 2, splits + 2):
        raise ValueError("not enough history for walk-forward optimization")
    splitter = TimeSeriesSplit(n_splits=splits)
    scores: list[float] = []
    for train_idx, test_idx in splitter.split(series):
        window_idx = list(train_idx) + list(test_idx)
        window = series.iloc[window_idx]
        signal = moving_average_signal(window, fast=fast, slow=slow)
        result = run_backtest(window, signal, fee_bps=fee_bps)
        test_start = len(train_idx)
        summary = performance_summary(result.iloc[test_start:])
        scores.append(float(summary["sharpe"]))
    return sum(scores) / len(scores), tuple(scores)


def optimize_sma_walkforward(
    close: pd.Series,
    *,
    n_trials: int = 30,
    splits: int = 4,
    fee_bps: float = 5.0,
    study: Any | None = None,
    seed: int = 0,
) -> OptimizationResult:
    if type(n_trials) is not int or not 1 <= n_trials <= 100:
        raise ValueError("n_trials must be an integer from 1 to 100")
    if type(splits) is not int or not 2 <= splits <= 5:
        raise ValueError("splits must be an integer from 2 to 5")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("seed must be an integer from 0 to 2**32 - 1")
    if isinstance(fee_bps, bool) or not np.isfinite(fee_bps) or not 0 <= fee_bps < 10000:
        raise ValueError("fee_bps must be finite and between 0 and 10000")
    close = _validated_close(close)
    if len(close) > 10000:
        raise ValueError("optimization is limited to 10000 observations")
    first_train, _ = next(TimeSeriesSplit(n_splits=splits).split(close))
    slow_max = min(120, len(first_train))
    if slow_max < 10:
        raise ValueError("not enough history for a fully warmed first validation fold")
    owned_study = study is None
    if owned_study:
        try:
            import optuna
        except ImportError as exc:
            raise RuntimeError("Optuna is optional; install Invest with the 'optuna' extra") from exc
        study = optuna.create_study(direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed))
    elif getattr(study, "trials", ()):
        raise ValueError("use a fresh study; prior trials are not bound to this dataset or protocol")
    direction = getattr(study, "direction", None)
    if direction is not None and getattr(direction, "name", None) != "MAXIMIZE":
        raise ValueError("study direction must be maximize")

    fold_map: dict[int, tuple[float, ...]] = {}
    trials: list[dict[str, Any]] = []

    def objective(trial: Any) -> float:
        fast = int(trial.suggest_int("fast", 3, min(30, slow_max - 2)))
        slow = int(trial.suggest_int("slow", max(fast + 2, 10), slow_max))
        if not 3 <= fast <= min(30, slow_max - 2) or not max(fast + 2, 10) <= slow <= slow_max:
            raise ValueError("trial parameters fall outside the declared search space")
        score, folds = _walkforward_score(
            close,
            fast=fast,
            slow=slow,
            fee_bps=fee_bps,
            splits=splits,
        )
        number = int(getattr(trial, "number", len(fold_map)))
        fold_map[number] = folds
        if not np.isfinite(score):
            raise ValueError("non-finite validation score")
        trials.append({'number': number, 'params': {'fast': fast, 'slow': slow},
                       'score': score, 'fold_scores': folds})
        return score

    study.optimize(objective, n_trials=n_trials)
    best = study.best_trial
    best_number = int(getattr(best, "number", 0))
    if best_number not in fold_map:
        raise ValueError("best trial was not evaluated on this dataset and protocol")
    return OptimizationResult(
        params={"fast": int(best.params["fast"]), "slow": int(best.params["slow"])},
        score=float(best.value),
        fold_scores=fold_map[best_number],
        trials=tuple(trials),
        seed=seed if owned_study else None,
        optimizer_version=optuna.__version__ if owned_study else None,
        training_fingerprint=hashlib.sha256(
            pd.util.hash_pandas_object(close, index=True).to_numpy(dtype='<u8').tobytes()
        ).hexdigest(),
        splits=splits,
        fee_bps=float(fee_bps),
    )
