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

## 长期成长计划

[长期成长路线图](docs/LONG_TERM_ROADMAP.md)：按能力与证据推进 Invest 的研究、模拟和工作台扩展。

## 书籍与开源参考

[学习资源清单](docs/LEARNING_RESOURCES.md)：5 本书、12 项 GitHub 参考，按成长环节说明用途、许可与最小应用产物。

## 融合状态

[融合状态与目录边界](docs/INTEGRATION_STATUS.md)记录当前 main 已合入的高星适配器、桌面/研究归档和独立引擎合同。
