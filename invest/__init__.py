"""Invest: a small, composable research and backtesting toolkit."""
from .pipeline import moving_average_signal, run_backtest, performance_summary
__all__ = ["moving_average_signal", "run_backtest", "performance_summary"]
