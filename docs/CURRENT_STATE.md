# Invest 当前状态｜500 元金额级决策支持

更新：2026-09-28。GitHub `Jvust/Invest` 为代码、状态和决策的权威来源。

## 当前开发链

- 最新功能：Draft [PR #16](https://github.com/Jvust/Invest/pull/16)，分支 `feat/500cny-bt-replay-20260928`。完整回归验证的功能代码为 `28eb16994d784162d0c96944cc5f9da356a3e702`；同步提交只更新文档与治理状态，PR 实时 head/CI 仍需核对。
- PR #9–#16 是依次堆叠的草稿链，#14 为状态同步。均未合并，main 未修改。
- 本次功能主矩阵 run `36391774329`：Ubuntu/Windows × Python 3.11/3.12 全过，每组 526 项（9 项缺可选依赖而跳过）。
- bt 真实依赖 run `36391774331`：三个合成情景实际执行通过；双风险指标 `36391774665`、双日历 `36391774808`、三优化器 `36391774377`、PyPortfolioOpt `36391774326` 均通过。
- 固定版本 bt 1.2.3 的持仓汇总触发 pandas 链式赋值警告；适配器已改读各资产序列，集成测试将该警告提升为错误。

## 已完成实现

- #9：ChatGPT → Actions → artifact 公开研究链路；Tencent 39 日 smoke，保留 Eastmoney 失败记录。
- #10：离散数量、整手、费用、流动性与现金约束。
- #11–#12：PyPortfolioOpt、Riskfolio-Lib、skfolio 最小方差和金额结果交叉比较。
- #13：XSHG/SSE 双日历及观测缺口核查。
- #15：[QuantStats/Empyrical 指标契约](RISK_METRICS_CROSSCHECK.md)：年化波动率、回撤和零无风险利率 Sharpe；常数收益明确标记未定义。
- #16：[bt 固定配置回放](BT_ALLOCATION_REPLAY.md)：对首日离散数量逐日核对现金、持仓、净值与费用，含全现金及不同资产费率。它只验证固定配置账务，不验证选股信号或真实市场成交。

## 下一步与未完成项

1. 将 bt 回放曲线按明确的初始资金和入场费用口径转换为日收益，接入双风险指标。
2. 建立 Hikyuu/Zipline 隔离合成数据合同，明确初始化/bundle、日历和成交规则差异。
3. 真实授权行情、来源证据、停复牌/公司行动/规则有效期、三个真实市场环境、冻结 holdout、前向观察、独立审查和真实设备验收仍待完成。

所有输出仍为 `PUBLIC_RESEARCH_ONLY` / `SCENARIO_ONLY`。本次合成用例不能代表真实收益。Drive 既有 checkpoint 保留；PR #15/#16 已追加并回读验证，文档修订号 `ANLCKQk8k7ln9Hc1fe9_DAVYAbSmCl4t5gIIC0HHNda-rH3T0WCryINeokt6DbTbnW_Lcz5Bs872ukVynkZOZWGjtz2LbDTEHE14STQ3-gY`。
