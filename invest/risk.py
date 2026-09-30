"""Risk metrics adapter based on Empyrical Reloaded."""
from __future__ import annotations

import numpy as np
import pandas as pd

from ._vendor import load_vendor

def _native_report(returns: pd.Series, periods_per_year: int) -> dict[str, float]:
    equity = (1.0 + returns).cumprod()
    total = float(equity.iloc[-1] - 1.0) if len(equity) else 0.0
    volatility = float(returns.std(ddof=1) * np.sqrt(periods_per_year)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() / returns.std(ddof=1) * np.sqrt(periods_per_year)) if len(returns) > 1 and returns.std(ddof=1) > 0 else 0.0
    drawdown = equity / equity.cummax() - 1.0 if len(equity) else pd.Series(dtype=float)
    return {"total_return": total, "annualized_volatility": volatility,
            "sharpe": sharpe, "max_drawdown": float(drawdown.min()) if len(drawdown) else 0.0}

def risk_report(returns: pd.Series, periods_per_year: int = 252) -> dict[str, float]:
    """Return cumulative return, volatility, drawdown, Sharpe and Sortino."""
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    values = pd.Series(returns, dtype="float64").replace([np.inf, -np.inf], np.nan).dropna()
    if values.empty:
        return {"total_return": 0.0, "annualized_return": 0.0,
                "annualized_volatility": 0.0, "max_drawdown": 0.0,
                "sharpe": 0.0, "sortino": 0.0}
    try:
        empyrical = load_vendor("empyrical")
        annual = float(empyrical.annual_return(values, annualization=periods_per_year))
        report = {
            "total_return": float(empyrical.cum_returns_final(values)),
            "annualized_return": annual,
            "annualized_volatility": float(empyrical.annual_volatility(values, annualization=periods_per_year)),
            "max_drawdown": float(empyrical.max_drawdown(values)),
            "sharpe": float(empyrical.sharpe_ratio(values, annualization=periods_per_year)),
            "sortino": float(empyrical.sortino_ratio(values, annualization=periods_per_year)),
        }
        return {key: (0.0 if not np.isfinite(value) else value) for key, value in report.items()}
    except (ImportError, ModuleNotFoundError, RuntimeError, ValueError):
        fallback = _native_report(values, periods_per_year)
        fallback["annualized_return"] = float((1.0 + fallback["total_return"]) ** (periods_per_year / len(values)) - 1.0)
        fallback["sortino"] = fallback["sharpe"]
        return fallback
