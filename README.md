# Invest

A composable investment research and backtesting toolkit.

## Included open-source components

The third_party/ tree brings in reusable modules from the MIT-licensed bt,
ta, and quantstats projects. See THIRD_PARTY.md for exact revisions and
attribution.

## Quick start

    python -m pip install -e .
    python examples/moving_average.py

The first integration layer in invest.pipeline supports an SMA crossover,
fee-aware long/flat backtests, and summary statistics. It avoids look-ahead by
applying each signal on the following bar.
