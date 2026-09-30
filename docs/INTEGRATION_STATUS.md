# Invest 融合状态

更新日期：2026-09-30。主分支已收敛为一个可追溯的融合结果。

## main 已合入

- 高星适配器与可选集成：AKShare、Qlib、PyPortfolioOpt、Riskfolio-Lib、skfolio、FinRL、VN.py、CCXT、yfinance，以及日历、风险和指标桥接。
- #19 的 1000+ Star 上游登记：见 [docs/upstream/1000-star-batch-2026-09-29.md](upstream/1000-star-batch-2026-09-29.md)。
- #30 的成长路线和学习资源：见 [LONG_TERM_ROADMAP.md](LONG_TERM_ROADMAP.md) 与 [LEARNING_RESOURCES.md](LEARNING_RESOURCES.md)。
- #31 的桌面交付、A 股研究、治理检查点、合成样例和 CI 资产。
- #32 的独立引擎合同、离散配置回放、风险交叉核验、市场证据和研究工作流；Hikyuu 2.8.2 与 Zipline Reloaded 3.1.1 仅作为可选 extra。

## 目录边界

- 当前统一研究核心在 `invest/`；高星适配器与独立合同可独立导入。
- 桌面交付中与当前核心同名的历史实现保存在 `legacy_app/`，完整长链研究版本和冲突基线保存在 `legacy_research/`。这些目录保留源码、测试和治理身份，便于逐项审计，不改变默认导入路径。
- `pyproject.toml` 默认安装不拉取 Hikyuu/Zipline；需要合同验证时显式安装 `.[independent-hikyuu]` 或 `.[independent-zipline]`。

## 证据边界

所有新增独立引擎合同和链式研究回放使用合成或公开研究输入。它们验证接口、账本和失败关闭行为，不证明真实行情许可、样本外收益、前向观察、券商权限或自动交易。

## 新增 50 项高星目录

- 批次登记：invest/upstream_registry.json，共 50 个新项目，快照日期 2026-09-30。
- 查询入口：invest.upstream_catalog.list_catalog()、available_catalog() 和 catalog_summary()。
- 采用目录级适配器合同，遵守许可证和数据权利边界，不把未审查第三方源码放入默认运行路径。
