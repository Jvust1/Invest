# Invest 当前状态：500 元决策终态 + ChatGPT 云端研究 + 开源量化生态

当前开发分支 `feat/chatgpt-cloud-research-20260927`，Draft PR #9，未合并 main。

## 最终产品方向

North Star 已明确：用户只需要告诉 ChatGPT 当前可投资的人民币资金，例如“我现在有 500 元，怎么投？”，ChatGPT + Invest 应输出金额级、可执行、可解释、可复盘的方案，包括现金保留、候选资产、投入金额、分批方式、交易约束、主要风险、失效条件和重新评估条件。

系统允许在用户明确请求时给出具体金额级决策支持，但不自动下单、不连接券商、不承诺收益。

## 当前验证身份

- 已验证 head：`5f6865b47967448651525cb992249003e2654721`
- CI run：`36327856647`
- Ubuntu/Windows × Python 3.11/3.12：全部成功
- Draft PR：#9
- main：未修改

## ChatGPT 云端公开研究

普通公开研究不要求本机 Python、CMD 或 Token。provider 显式写入任务；失败不静默换源。首次 Eastmoney 云端尝试失败并保留证据；独立 Tencent 任务成功。

成功 smoke：`600000.SH`，请求 2026-08-01～2026-09-25，实际 39 个交易日。该结果只用于链路验收和描述性研究，不代表收益保证或策略接受。

## 开源生态扩展

当前机器可读能力池纳入 33 个 GitHub 项目，覆盖中国市场数据、A 股/独立回测、组合优化、风险绩效、交易日历、技术指标、因子/机器学习、自动研究和金融文本。

核心文件：
- `docs/PROJECT_NORTH_STAR.md`
- `docs/OPEN_SOURCE_ECOSYSTEM.md`
- `invest/upstream_registry.json`
- `invest/upstreams.py`
- `tests/test_upstreams.py`
- `governance/upstream_ecosystem_result.json`

P0：PyPortfolioOpt / Riskfolio-Lib / skfolio + 500 元离散金额、最小交易单位、佣金、税费、流动性和剩余现金。

P1：exchange_calendars + pandas_market_calendars 双日历，QuantStats + Empyrical 风险交叉检查，Hikyuu / Zipline / bt 独立历史验证。

P2：Qlib / Alphalens 因子研究，以及 FinGPT / FinBERT / RD-Agent / FinRL 实验支线。

## Drive 长期归档

新增快照：`Invest-500CNY-OpenSource-Ecosystem-Checkpoint-20260928`

- Drive ID：`1vFoLqrAZmcrbmyHbXJUbLSpFSqImMJhZ81jfon-1Wwk`
- 位于 Invest 文件夹
- 内容已回读验证
- 对应已验证 source commit：`5f6865b47967448651525cb992249003e2654721`
- 不包含任何第三方仓库源码

原有 rc2、Engine Lab、Execution Contract、Market Evidence、Local Acquisition、ChatGPT Cloud Research 归档均保留。

## 边界

公开云端数据继续标记 `PUBLIC_RESEARCH_ONLY`。正式 execution-data、frozen holdout、forward observation、broker 连接和真实下单均未启用。GPL/AGPL 或许可证不明确的第三方项目保持 reference-only，软件许可与行情数据权利分开治理。
