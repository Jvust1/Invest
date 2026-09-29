# Invest 当前状态｜500 元金额级决策支持

更新：2026-09-29。GitHub `Jvust/Invest` 为代码、状态和决策的权威来源。

## 当前开发链

- 最新功能：Draft [PR #18](https://github.com/Jvust/Invest/pull/18)，分支 `feat/independent-engine-contracts-20260929`，基于 PR #17。
- 完整回归验证的功能提交：`3507e511e293c3004342896272bdd576c74f00b1`；PR #9–#18 继续 Draft / Open / Unmerged，`main` 未修改。
- 主矩阵 run `36532883762`：Ubuntu/Windows × Python 3.11/3.12 全过，每组 534 项，13 项可选测试跳过。
- 独立引擎 run `36532883781`：Hikyuu 2.8.2 与 Zipline Reloaded 3.1.1 两个 job 均成功；既有 bt、风险指标、日历、优化器、净值→风险报告合同继续全绿。

## 已完成实现

- #9–#13：公开研究链路、金额级离散配置、三优化器交叉比较、XSHG/SSE 双日历。
- #15：QuantStats / Empyrical 六项风险与绩效指标合同。
- #16：bt 固定配置逐日现金/持仓/净值/费用回放。
- #17：费用感知的净值→日收益→六项风险报告闭环。
- #18：[Hikyuu / Zipline 隔离预检](INDEPENDENT_ENGINE_CONTRACTS.md)：Hikyuu 临时内存 K 线 + ETF 费用原语通过；Zipline XSHG 日历 + 自定义 CSV bundle 注册生命周期通过。Hikyuu 首次初始化可能拉取其 hub 策略仓库，已记录为框架初始化副作用。

## 当前明确未完成

1. Hikyuu 真实合成 TradeManager/System 事件驱动成交合同：整手、费用取整、成交时点、T+1。
2. Zipline 真正的临时 bundle ingest + `run_algorithm`，以及与 Invest 对应的佣金/滑点/整手适配。
3. 授权真实行情、provenance、停复牌、公司行动、历史规则有效期、冻结 holdout、前向观察、独立审查和真实设备重复使用价值。

因此 #18 是**独立引擎 preflight**，不是“完整回测已验收”。所有输出仍为 `PUBLIC_RESEARCH_ONLY` / `SCENARIO_ONLY`。Drive checkpoint 已追加 #18 并回读验证，revision `ANLCKQmNxbR8J48dJPuptTkeRx-eRCIE3W0-_JPT0kMlqICLdeAhLrlseUWadcsR3O6NUU1x78FAglRINCNWMhxip7MPZxltmW1HE--5xss`。
