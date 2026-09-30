"""Fetch A-share data and run the fused Invest pipeline.

Usage:
    python examples/a_share_sma.py 000001
"""
from __future__ import annotations
import sys
from invest import run_a_share_sma_backtest

symbol = sys.argv[1] if len(sys.argv) > 1 else "000001"
result, summary = run_a_share_sma_backtest(symbol, fast=20, slow=50, adjust="qfq")
print("rows:", len(result))
print("summary:", summary)
