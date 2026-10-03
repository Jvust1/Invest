"""Portfolio allocation adapters."""
from __future__ import annotations
import numpy as np
import pandas as pd
from ._vendor import load_vendor
from .paper_ledger import PaperLedger

def inverse_variance_weights(prices: pd.DataFrame) -> dict[str, float]:
    """Dependency-light fallback allocation for missing convex solvers."""
    if prices.shape[1] == 0:
        raise ValueError("prices must contain at least one asset")
    returns = prices.astype("float64").pct_change().dropna(how="all")
    variances = returns.var(ddof=1).replace([np.inf, -np.inf], np.nan)
    if variances.isna().all():
        raise ValueError("prices do not contain enough variation")
    variances = variances.fillna(variances.dropna().median()).clip(lower=np.finfo(float).eps)
    raw = 1.0 / variances
    weights = raw / raw.sum()
    return {str(name): float(value) for name, value in weights.items()}

def minimum_variance_weights(prices: pd.DataFrame, weight_bounds: tuple[float, float] = (0.0, 1.0)) -> dict[str, float]:
    """Use vendored PyPortfolioOpt when its optional solver stack is present."""
    if not isinstance(prices, pd.DataFrame) or prices.shape[1] == 0:
        raise ValueError("prices must be a non-empty DataFrame")
    lower, upper = weight_bounds
    if not 0 <= lower <= upper:
        raise ValueError("weight_bounds must satisfy 0 <= lower <= upper")
    try:
        from pypfopt import EfficientFrontier, expected_returns, risk_models
        load_vendor("pypfopt")
        mu = expected_returns.mean_historical_return(prices)
        covariance = risk_models.sample_cov(prices)
        optimizer = EfficientFrontier(mu, covariance, weight_bounds=weight_bounds)
        optimizer.min_volatility()
        cleaned = optimizer.clean_weights()
        return {str(name): float(value) for name, value in cleaned.items()}
    except (ImportError, ModuleNotFoundError, RuntimeError, ValueError):
        return inverse_variance_weights(prices)

def optimize_weights(returns, engine: str = "auto") -> dict[str, float]:
    """Select a portfolio engine behind one stable return-weights interface."""
    frame = pd.DataFrame(returns).astype(float)
    if frame.empty or frame.shape[1] == 0:
        raise ValueError("returns must contain at least one asset")
    if engine == "inverse_variance":
        return inverse_variance_weights((1.0 + frame).cumprod())
    if engine == "riskfolio":
        from .riskfolio_adapter import riskfolio_weights
        return riskfolio_weights(frame)
    if engine == "skfolio":
        from .skfolio_adapter import skfolio_weights
        return skfolio_weights(frame)
    if engine == "pypfopt":
        return minimum_variance_weights((1.0 + frame).cumprod())
    if engine == "auto":
        return optimize_weights(frame, engine="skfolio")
    raise ValueError("engine must be one of: auto, inverse_variance, pypfopt, riskfolio, skfolio")
