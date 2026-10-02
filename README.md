# Invest

A composable investment research and backtesting toolkit.

## ChatGPT 普通聊天研究插件

[聊天插件接入与验收](docs/CHAT_PLUGIN.md)：16 个只读 MCP 工具、GitHub/Drive
有界检索、私有结构化资料索引、人民币配置/组合/风险情景。使用 `pip install -e '.[chat]'`。
目标账户插件注册、授权与普通 Chat 实测仍须独立完成；不将软件测试写成真实投资能力。
[0.2 升级](docs/CHAT_UPGRADE_0_2.md)：接入诊断、调用者历史数据质量检查、精确金额和搜索完整性修复。

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

## 50 项高星融合目录

[2026-09-30 高星开源项目 50 项融合目录](docs/HIGH_STAR_50_INTEGRATION.md)记录新批次的来源、星标、许可证和能力标签。
