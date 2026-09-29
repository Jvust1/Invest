# Invest 当前状态｜500 元金额级决策支持

更新：2026-09-29。GitHub `Jvust/Invest` 为代码、状态和决策的权威来源。

## 当前开发链

- 最新功能：Draft [PR #17](https://github.com/Jvust/Invest/pull/17)，分支 `feat/500cny-replay-risk-report-20260929`，基于 PR #16。
- 完整回归验证的功能提交为 `735b1638c2e00ef5a14ce9b0e37b180f3946ddc7`；PR #9–#17 继续保持 Draft / Open / Unmerged，`main` 未修改。
- 主矩阵 run `36531969490`：Ubuntu/Windows × Python 3.11/3.12 全过，每组 532 项，11 项可选测试跳过。
- 新增净值→风险报告三库合同 run `36531969541`：真实 `bt==1.2.3` + `quantstats==0.0.86` + `empyrical-reloaded==0.5.12` 的 40 交易日与全现金两项合成案例通过。
- 风险指标 run `36531969509`、bt run `36531969518`、双日历 run `36531969551`、三优化器 run `36531969501`、PyPortfolioOpt run `36531969530` 均通过。

## 已完成实现

- #9：ChatGPT → Actions → artifact 公开研究链路；Tencent 39 日 smoke，保留 Eastmoney 失败记录。
- #10：离散数量、整手、费用、流动性与现金约束。
- #11–#12：PyPortfolioOpt、Riskfolio-Lib、skfolio 最小方差和金额结果交叉比较。
- #13：XSHG/SSE 双日历及观测缺口核查。
- #15：[QuantStats/Empyrical 指标契约](RISK_METRICS_CROSSCHECK.md)：现已扩展为累计收益、年化收益、年化波动率、最大回撤、Sharpe、Sortino 六项。
- #16：[bt 固定配置回放](BT_ALLOCATION_REPLAY.md)：逐日核对现金、持仓、净值与费用，含全现金及不同资产费率。
- #17：[净值→收益→风险报告闭环](REPLAY_RISK_REPORT.md)：只有 Invest/bt 逐日一致后才生成风险报告；首日收益相对初始资金计算，显式保留入场费用拖累；少于 30 个共同观测或回放分歧时 fail-closed。

## 下一步与未完成项

1. 建立 Hikyuu / Zipline-reloaded 隔离合成数据合同，明确初始化/bundle、交易日历、成交与费用规则差异。
2. 获得真实授权行情、provenance、停复牌、公司行动和历史规则有效期证据后，才扩展真实市场结论。
3. 三个真实市场环境、冻结 holdout、前向观察、独立审查、真实设备与重复使用价值仍待完成。

所有输出仍为 `PUBLIC_RESEARCH_ONLY` / `SCENARIO_ONLY`。本轮只证明软件合同在合成输入下成立，不代表真实收益、信号质量或成交能力。Drive 既有 checkpoint 已追加 PR #17 并回读验证，revision `ANLCKQm_NtGARTWf2gCAp3WZlHxCO52sRBJ9qA7e3IKyRWTEwMHLfO14T20-2VR68bxr0k8_w_tj9z8DMTIVG0kgE81p3dg1lUhn8_oqpOw`。
