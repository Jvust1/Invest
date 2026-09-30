"""Optuna adapter for time-series-safe SMA parameter search.

Upstream: optuna/optuna @
5c8e50d85b77dd5a1fd7e26e21f63debc81d6016 (MIT).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd
from sklearn.model_selection import TimeSeriesSplit

from .pipeline import moving_average_signal, performance_summary, run_backtest


@dataclass(frozen=True)
class OptimizationResult:
    params: dict[str, int]
    score: float
    fold_scores: tuple[float, ...]


def _walkforward_score(
    close: pd.Series,
    *,
    fast: int,
    slow: int,
    fee_bps: float,
    splits: int,
) -> tuple[float, tuple[float, ...]]:
    series = pd.Series(close, dtype="float64").dropna()
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
) -> OptimizationResult:
    if n_trials < 1:
        raise ValueError("n_trials must be positive")
    if splits < 2:
        raise ValueError("splits must be at least 2")
    if study is None:
        try:
            import optuna
        except ImportError as exc:
            raise RuntimeError("Optuna is optional; install Invest with the 'optuna' extra") from exc
        study = optuna.create_study(direction="maximize")

    fold_map: dict[int, tuple[float, ...]] = {}

    def objective(trial: Any) -> float:
        fast = int(trial.suggest_int("fast", 3, 30))
        slow = int(trial.suggest_int("slow", max(fast + 2, 10), 120))
        score, folds = _walkforward_score(
            close,
            fast=fast,
            slow=slow,
            fee_bps=fee_bps,
            splits=splits,
        )
        number = int(getattr(trial, "number", len(fold_map)))
        fold_map[number] = folds
        return score

    study.optimize(objective, n_trials=n_trials)
    best = study.best_trial
    best_number = int(getattr(best, "number", 0))
    return OptimizationResult(
        params={"fast": int(best.params["fast"]), "slow": int(best.params["slow"])},
        score=float(best.value),
        fold_scores=fold_map.get(best_number, ()),
    )
