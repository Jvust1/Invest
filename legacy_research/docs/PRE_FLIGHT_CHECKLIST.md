# 接手与修改前核对

1. 先读取目标工作分支的 `AGENTS.md` 与 `governance/project_state.json`。若该分支当前存在 `SECURITY_POLICY.md`，则一并读取；若当前治理明确 `security_status=NO_PROJECT_SECURITY_GATE` 且该文件已正式移除，其缺失不构成阻塞，不恢复旧安全文件，也不要求历史 Drive safety-baseline ID。
2. 确认 repo 为 `Jvust/Invest`（stable ID `1381007406`），Drive 项目目录为 `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u`；核对活动分支、真实 Git SHA、PR 与治理状态。main 未经针对具体 PR 的明确合并授权不得修改。
3. 读取 North Star、架构约束、Current State/project_state、长期计划、Decision/Evaluation Ledger、artifact manifest、pending_sync；`PRE_FLIGHT_CHECKLIST.md` 仅在仍属现行治理时执行，历史/退役门禁不得重新制造只读状态。
4. 涉及策略效果时区分合成、历史开发样本、冻结样本外数据和前向模拟，不将已见数据再称 unseen。
5. 涉及执行时核对行情单位、日历、限价、停牌、公司行动、费用及身份；缺失时保持阻断。
6. 仅在现有非默认工作分支做必要增量；测试应针对资金、时间、身份、隐私和用户流程的真实风险。
7. 对账后同步，跳过重复；不上传凭据、私密账本、环境变量、缓存或原始私人研究记录。
8. 写入后回读文件与 refs，核对 PR diff 与 CI；验证事实与未验证边界如实入账，禁止自动合并。

9. G1–G5 当前候选须同时读取 `governance/growth_delivery_result.json`；核对成品 source_commit 与 CI、Drive回读哈希，避免用旧版或metadata-only提交替代实际成品身份。
