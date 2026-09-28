# Invest 接续说明

截至 2026-09-28 12:06:47 CST。先读 `AGENTS.md`、`governance/project_state.json`、`governance/assistant_cloud_result.json`、`governance/upstream_ecosystem_result.json`、`docs/CURRENT_STATE.md`、`docs/PROJECT_NORTH_STAR.md`、`docs/OPEN_SOURCE_ECOSYSTEM.md`、`governance/artifact_manifest.json` 与 `governance/pending_sync.json`，然后核实 GitHub 的实时 PR/CI。

## 当前分支与交付

- 功能最新 head：`c29dbd0b1cdb0bdc6247ffb6b4ab1f1406840cde`，PR #13 双日历，Draft/Open/Unmerged。
- PR #9–#13 是依次堆叠的草稿功能分支；本状态同步分支 `docs/invest-progress-sync-20260928` 基于 PR #13，拟作为 Draft PR #14。
- PR #13 主矩阵 run `36375284697` 四平台/Python 组合通过；双日历 run `36375284696`、优化器三合同 run `36375284617`、PyPortfolioOpt run `36375284652` 通过。
- Drive checkpoint：`Invest-500CNY-OpenSource-Ecosystem-Checkpoint-20260928`，ID `1vFoLqrAZmcrbmyHbXJUbLSpFSqImMJhZ81jfon-1Wwk`。已保留原快照并追加本次状态。

## 产品目标与实现

Invest 目标是将人民币金额输入转成受费用、整手、流动性与现金约束的可审计配置情景。#10 离散金额层、#11 PyPortfolioOpt、#12 Riskfolio-Lib/skfolio 三后端交叉核查、#13 XSHG/SSE 日历核查均已有实现和 CI 证据。#9 ChatGPT 云端公开研究链路可复用，失败 provider 记录保留且切源须显式开启新任务。

## 继续顺序

1. QuantStats 与 Empyrical 风险/绩效计算对照。
2. Hikyuu、Zipline-reloaded、bt 独立回测路径的适用性和合同核查。
3. 授权真实数据、许可、停牌、公司行动和规则有效日期证据；然后才能规划 frozen holdout 与 forward observation。

## 安全与范围

仅 `PUBLIC_RESEARCH_ONLY` / `SCENARIO_ONLY`。不要连接券商或下单，不自动打开 frozen holdout，不把合成输入或公开行情包装成真实收益证据。不得覆盖 main；每个功能 PR 保持 Draft，等待明确审查/合并指示。原 G1-G5/RC2 和历史证据文件保留，不因本状态同步重打包或替换。
