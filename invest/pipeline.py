"""Research pipeline that connects market data, signals, and backtests."""
from __future__ import annotations
import numpy as np
import pandas as pd

def moving_average_signal(close: pd.Series, fast: int = 20, slow: int = 50) -> pd.Series:
    """Return a long/flat SMA crossover signal (1 or 0)."""
    if fast <= 0 or slow <= 0 or fast >= slow:
        raise ValueError("fast and slow must be positive and fast < slow")
    close = pd.Series(close, dtype="float64")
    fast_ma = close.rolling(fast, min_periods=fast).mean()
    slow_ma = close.rolling(slow, min_periods=slow).mean()
    return (fast_ma > slow_ma).astype("int8").rename("signal")

def run_backtest(close: pd.Series, signal: pd.Series, fee_bps: float = 0.0) -> pd.DataFrame:
    """Run a long/flat close-to-close backtest without look-ahead."""
    if fee_bps < 0:
        raise ValueError("fee_bps cannot be negative")
    prices = pd.Series(close, dtype="float64").rename("close")
    positions = pd.Series(signal, index=prices.index, dtype="float64").fillna(0.0)
    if not prices.index.equals(positions.index):
        positions = positions.reindex(prices.index).fillna(0.0)
    asset_returns = prices.pct_change().fillna(0.0)
    turnover = positions.diff().abs().fillna(positions.abs())
    costs = turnover * (fee_bps / 10_000.0)
    strategy_returns = positions.shift(1).fillna(0.0) * asset_returns - costs
    equity = (1.0 + strategy_returns).cumprod()
    return pd.DataFrame({
        "close": prices,
        "signal": positions,
        "asset_return": asset_returns,
        "turnover": turnover,
        "strategy_return": strategy_returns,
        "equity": equity,
    })

def performance_summary(result: pd.DataFrame, periods_per_year: int = 252) -> dict[str, float]:
    """Summarize only the supplied returns, even when result is a time slice.

    The supplied equity column may include earlier training history. Rebuild
    normalized equity from this slice's returns so neither its cumulative return
    nor drawdown can accidentally include returns outside the evaluation window.
    """
    if periods_per_year <= 0:
        raise ValueError("periods_per_year must be positive")
    returns = pd.Series(result["strategy_return"], dtype="float64")
    if not np.isfinite(returns).all() or (returns < -1.0).any():
        raise ValueError("strategy returns must be finite and cannot lose more than 100%")
    equity = (1.0 + returns).cumprod()
    if returns.empty:
        return {"total_return": 0.0, "annualized_return": 0.0,
                "annualized_volatility": 0.0, "sharpe": 0.0,
                "max_drawdown": 0.0}
    total = float(equity.iloc[-1] - 1.0)
    years = max(len(returns) / periods_per_year, 1 / periods_per_year)
    annual = float((1.0 + total) ** (1.0 / years) - 1.0)
    volatility = float(returns.std(ddof=1) * np.sqrt(periods_per_year)) if len(returns) > 1 else 0.0
    sharpe = float(returns.mean() * periods_per_year / volatility) if volatility > 0 else 0.0
    drawdown = equity / equity.cummax().clip(lower=1.0) - 1.0
    return {"total_return": total, "annualized_return": annual,
            "annualized_volatility": volatility, "sharpe": sharpe,
            "max_drawdown": float(drawdown.min())}

def run_a_share_sma_backtest(
    symbol: str,
    start_date: str = "20200101",
    end_date: str = "20500101",
    fast: int = 20,
    slow: int = 50,
    fee_bps: float = 5.0,
    adjust: str = "qfq",
    timeout: float = 15,
    provider: str = "direct",
    provider_instance=None,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Fetch A-share history and run the Invest SMA pipeline end to end.

    provider="direct" uses Invest's dependency-light Eastmoney HTTP adapter.
    provider="akshare" uses the optional native AKShare package adapter.
    A provider_instance may be injected for deterministic tests or custom runtime wiring.
    """
    normalized_provider = str(provider).strip().casefold()
    if provider_instance is not None:
        history = provider_instance.history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
    elif normalized_provider == "direct":
        from .providers.akshare_eastmoney import fetch_a_share_daily
        history = fetch_a_share_daily(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
            timeout=timeout,
        )
    elif normalized_provider == "akshare":
        from .providers.akshare_native import AKShareProvider
        history = AKShareProvider().history(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            adjust=adjust,
        )
    else:
        raise ValueError("provider must be 'direct' or 'akshare'")
    if history.empty:
        raise ValueError(f"no market data returned for symbol {symbol}")
    signal = moving_average_signal(history["close"], fast=fast, slow=slow)
    result = run_backtest(history["close"], signal, fee_bps=fee_bps)
    from copy import deepcopy
    for key in ("market_data", "duckdb_replay"):
        if key in history.attrs:
            result.attrs[key] = deepcopy(history.attrs[key])
    return result, performance_summary(result)
