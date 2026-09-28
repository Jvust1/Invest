# Invest 接续：500 元决策终态 + ChatGPT 云端研究 + 开源生态

先读 `AGENTS.md`、`governance/project_state.json`、`governance/assistant_cloud_result.json`、`governance/upstream_ecosystem_result.json`、`docs/CURRENT_STATE.md`、`docs/PROJECT_NORTH_STAR.md`、`docs/OPEN_SOURCE_ECOSYSTEM.md`、`governance/artifact_manifest.json`、`governance/pending_sync.json`，然后核实 live PR/CI。

当前仓库 `Jvust/Invest`，开发分支 `feat/chatgpt-cloud-research-20260927` / Draft PR #9，未合并 main。当前已验证 head `5f6865b47967448651525cb992249003e2654721`，CI run `36327856647`，Ubuntu/Windows × Python 3.11/3.12 全部成功。

## 产品 North Star

当用户说“我现在有 500 元，怎么投？”时，目标不是只返回行情指标，而是把研究结果转成金额级、可执行、可复盘的人民币投资决策支持：现金保留、资产/标的资格、金额、分批、最小交易单位、手续费/税费、流动性、主要风险、失效条件和重新评估条件。

如果真实交易约束不满足，允许答案是暂不交易、只投入一部分、改用更适合小资金的 ETF / 现金方案，或等待资金积累。

## 默认研究操作

普通公开研究继续优先走 ChatGPT 云端路径，不要求用户本地 Python/CMD/Token。provider 必须显式；失败保留证据，换源创建独立 job，不静默 fallback。当前验证成功 provider 为 `akshare_tencent`。

## 开源生态

机器清单 `invest/upstream_registry.json`，统一路由 `invest/upstreams.py`，当前纳入 33 个项目。P0 是 PyPortfolioOpt / Riskfolio-Lib / skfolio + 真实离散金额与交易成本层；P1 是双日历、双风险指标以及 Hikyuu / Zipline / bt 独立验证；P2 再扩展 Qlib / Alphalens / FinGPT / FinBERT / RD-Agent / FinRL。

默认不 vendor 第三方源码。MIT/Apache/BSD 可作为 adapter 候选；GPL/AGPL/许可证不明确先 reference-only。软件许可与行情数据权利分开判断。

## Drive 长期成果

原云端研究包仍是 `Invest-ChatGPT-Cloud-Research-v0.1-20260927.zip`，ID `1kumrq8YMaRZWbaf12HpWdCOo4F9itvjh`。

本轮新增 Drive 快照：`Invest-500CNY-OpenSource-Ecosystem-Checkpoint-20260928`，ID `1vFoLqrAZmcrbmyHbXJUbLSpFSqImMJhZ81jfon-1Wwk`，位于 Invest 文件夹，已完成内容回读验证。该快照只保存成果与身份信息，不复制第三方仓库源码。

## 不要混淆

公开云端研究不等于正式授权执行行情。不要据此自动打开 frozen holdout、连接券商或下单。正式 execution-data、真实许可、三种真实市场环境、样本外/前向观察与独立评审仍是独立工作线。
