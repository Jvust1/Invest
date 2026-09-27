# Invest 当前状态：ChatGPT 云端公开研究 + 开源量化生态

当前开发分支 `feat/chatgpt-cloud-research-20260927`，Draft PR #9 基于 PR #8。

## 最终产品方向

Invest 的 North Star 已更新为：用户只需要告诉 ChatGPT 当前可投资的人民币资金，例如“我现在有 500 元，怎么投？”，ChatGPT + Invest 应输出金额级、可执行、可解释、可复盘的方案，包括现金保留、候选资产、投入金额、分批方式、交易约束、主要风险、失效条件和下一次评估条件。

系统允许在用户明确请求时给出具体金额级决策支持，但不自动下单、不连接券商、不承诺收益。

## ChatGPT 云端公开研究

云端运行基线代码 `f2ab93b6a23c57517d1348e4efe5dd8703386289`；四矩阵回归 run `36315941217`。首次成功任务提交 `e093baa3265bae4d00239932c47def79be2a55b1`，云端 run `36316010850`。

普通公开研究不要求用户本机安装 Python、运行 CMD 或准备 Token。用户直接在 ChatGPT 中说明标的和研究范围；ChatGPT 负责写入唯一 job、观察 GitHub Actions、读取结果并继续分析。

数据源显式写入请求；一个 provider 失败时不在同一次运行中偷偷换源。首次 Eastmoney 云端尝试失败并保留证据；独立 Tencent 任务成功。

成功 smoke：
- 标的：600000.SH
- 请求：2026-08-01～2026-09-25
- 实际交易日：2026-08-03～2026-09-24，共 39 日
- 首/末收盘：9.63 / 9.00
- 区间价格变化：-6.54%
- 5/20 交易日变化：-0.66% / -0.77%
- 收盘序列最大回撤：-6.85%
- 日收益年化波动率：18.90%
- MA5 / MA20：9.02 / 9.184；MA60 样本不足

以上是链路验收与描述性研究，不是收益保证。

## 2026-09-27 开源生态扩展

已把 GitHub 上筛选出的 **33 个开源量化项目** 纳入 Invest 的机器可读能力池，而不是整包复制第三方源码。

新增：
- `invest/upstream_registry.json`：33 个项目、能力、接入阶段、许可证和目标；
- `invest/upstreams.py`：按 capability / stage / license 选择上游，并给出“500 元配置”推荐技术栈；
- `tests/test_upstreams.py`：registry 唯一性、许可证门、能力覆盖和小资金技术栈测试；
- `docs/OPEN_SOURCE_ECOSYSTEM.md`：完整接入策略；
- `governance/upstream_ecosystem_result.json`：治理回执；
- registry 已加入 Python package data。

生态代码 head `f1bc308f7f63090f383bbd966db96537fe0a7d81` 已通过 CI run `36327696881`：Ubuntu/Windows × Python 3.11/3.12 四个 job 全部成功，源码 compile 检查也全部成功。

当前 33 个项目覆盖：
- 中国市场数据与行情；
- A 股与独立回测；
- 组合优化与风险预算；
- 风险/绩效分析；
- 交易日历和技术指标；
- 因子/机器学习/自动实验；
- 金融新闻和情绪研究。

高优先级 P0/P1：PyPortfolioOpt、Riskfolio-Lib、skfolio、exchange_calendars、pandas_market_calendars、QuantStats、Empyrical、Hikyuu、Zipline-reloaded、bt、Qlib、Alphalens。

注意：本次“纳入”完成的是**可治理的上游能力层、选择路由与验证框架**。除 AKShare / RQAlpha 等已有路径外，大部分第三方功能尚未变成运行时 adapter；下一阶段应逐个做版本锁定、输入输出转换和交叉验证，而不是未经验证直接安装全部依赖。

## 开源许可证与数据边界

默认不复制第三方源码：
- MIT / Apache-2.0 / BSD-2-Clause / BSD-3-Clause：可进入直接 adapter 候选；
- GPL / AGPL / GitHub 未确认许可证：先保持 reference-only；
- 软件许可证永远不等于底层行情数据使用权。

因此 backtrader、backtesting.py、vectorbt、OpenBB、stockstats 等不会因为“开源”就直接拷入 Invest 源码。

## 500 元路径的下一步

优先顺序：
1. PyPortfolioOpt / Riskfolio-Lib / skfolio 组合 adapter；
2. 把连续权重离散成真实 500 元可买数量；
3. 加入最小交易单位、佣金/最低佣金、税费、流动性与剩余现金；
4. exchange_calendars + pandas_market_calendars 双日历交叉检查；
5. QuantStats + Empyrical 风险指标交叉检查；
6. Hikyuu / Zipline / bt 独立历史验证；
7. Qlib / Alphalens 因子研究；
8. FinGPT / FinBERT / FinRL / RD-Agent 保持实验支线，不能越过风险和执行约束直接生成交易动作。

## 长期归档与边界

Drive 原 Invest 目录已有 `Invest-ChatGPT-Cloud-Research-v0.1-20260927.zip`，云端模式证据已回读验证。此次开源生态主要是 GitHub 代码/治理扩展，没有重复打包第三方仓库到 Drive。

所有公开云端行情仍标记 `PUBLIC_RESEARCH_ONLY`。正式 execution-data、frozen holdout、forward observation、broker 连接和真实下单均未启用。

权威回执：
- `governance/assistant_cloud_result.json`
- `governance/upstream_ecosystem_result.json`
