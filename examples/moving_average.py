"""Run: python examples/moving_average.py"""
import numpy as np
import pandas as pd
from invest import moving_average_signal, run_backtest, performance_summary

dates = pd.date_range("2020-01-01", periods=300, freq="B")
rng = np.random.default_rng(7)
close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0.0002, 0.01, len(dates)))), index=dates, name="Close")
signal = moving_average_signal(close, fast=20, slow=50)
result = run_backtest(close, signal, fee_bps=5)
print(performance_summary(result))
