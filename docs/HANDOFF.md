# Invest 接续说明

截至 2026-09-28。先按 `AGENTS.md` 读取治理文件，再核对实时 PR/CI。

## 接续位置

- Draft [PR #16](https://github.com/Jvust/Invest/pull/16) / `feat/500cny-bt-replay-20260928`，基于 PR #15。
- 完整回归验证的功能代码：`28eb16994d784162d0c96944cc5f9da356a3e702`；同步提交仅更新文档/治理，继续工作前核对实时 PR head。
- 主矩阵 `36391774329` 全过（每组 526 项，9 项可选测试跳过）；bt 真实依赖 `36391774331` 三项通过，风险指标/日历/优化器回归均通过。见 `governance/checkpoints/20260928_bt_replay_progress.json`。
- #15 已完成 QuantStats/Empyrical；#16 已完成 bt 固定配置账务回放。Hikyuu/Zipline 尚未运行，不要把 bt 账务一致写成完整独立市场回测验收。

## 继续顺序

1. 接通固定配置净值 → 明确入场费用口径的日收益 → 双风险指标，并覆盖全现金和日期边界。
2. Hikyuu/Zipline 的隔离合成数据初始化/bundle 与交易规则合同。
3. 授权真实数据与 provenance、停牌、公司行动、历史规则证据；之后再规划冻结 holdout 与前向观察。

## 交付记录与范围

GitHub 为代码和当前状态权威。已有 Drive checkpoint ID `1vFoLqrAZmcrbmyHbXJUbLSpFSqImMJhZ81jfon-1Wwk` 已追加 PR #15/#16 成果并回读验证，当前 revision `ANLCKQk8k7ln9Hc1fe9_DAVYAbSmCl4t5gIIC0HHNda-rH3T0WCryINeokt6DbTbnW_Lcz5Bs872ukVynkZOZWGjtz2LbDTEHE14STQ3-gY`。没有新 EXE/APK 或替换历史交付。

仅 `PUBLIC_RESEARCH_ONLY` / `SCENARIO_ONLY`。不自动打开 holdout、连接券商、下单、修改 main 或合并 PR。功能和状态同步 PR 保持 Draft，等待明确合并指示。
