# 接手说明

更新时间：2026-09-25。本文按 GitHub/Drive 实时状态维护；动态分支、PR 与 CI 状态接手时必须再次读取，不依赖聊天历史。

## 先恢复权威状态

1. 读取 `AGENTS.md`、目标分支 `SECURITY_POLICY.md`、Drive 根目录 `全项目` 入口及动态发现的全部 `全项目_` 基线，再按 `PRE_FLIGHT_CHECKLIST.md` 恢复项目。
2. GitHub `Jvust2/Invest` 是代码、治理、当前状态与下一步权威；Drive 项目目录 `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u` 保存原始资料和长期 artifact。
3. 当前功能线为 `feat/a-share-research-v0.1-20260922`，Draft PR #2 → `main`，保持未合并；任何合并都需要针对 PR #2 的明确授权，禁止直接写 main。
4. 并行长期路线图在 PR #1 / `docs/long-term-roadmap-20260922`，继续独立保留。
5. 接手后读取 North Star、Current State、Architecture Invariants、Decision/Evaluation Ledgers、`governance/project_state.json`、artifact manifest 与 pending_sync。
6. 真实数据主线另读取真实供应商 runbook、provider evidence 格式与 `governance/decisions/D011`–`D020`；这些只定义真实联调前后的证据合同，不代表真实联调已经完成。

## 当前已验证的软件状态

- v0.1 已实现标准库本机中文网页、CSV/交易日历审计、有限日频均线回测、人民币模拟账本和 Tushare 四接口研究导入边界。
- 样本外与 forward-paper 方法协议 v1 已冻结；binding 校验器已远端矩阵验证。
- Provider evidence 校验器现在有 23 个测试方法；完整测试集为 118。最新已验证代码/文档 head `6db24bb3cde003f937a73dc5a5eb2041181af505`，Actions run `36089180871` 成功，Ubuntu/Windows × Python 3.11/3.12 四个 job 的 tests 与 compile 均成功。
- Provider evidence 当前 fail closed 于：失败接口、成功接口空字段/0 行、成功核心接口缺当前适配器必需字段、未知/未覆盖市场边界、显式 blocker、凭据字段、超出当前沪深主板格式范围的样本代码、`sample.end_date` 晚于 `executed_at` 日期、缺少四核心接口、单位契约不匹配、`executed_at` 不是 `Asia/Shanghai` 对应的 `+08:00` offset，任何 `status=verified` 的 market-data boundary 缺少有效 supporting-evidence SHA-256，以及授权状态缺少有效 `license_evidence_sha256`。
- `unknown` / `not_covered` boundary 仍可不带 evidence hash 诚实保存，但 provider-side readiness 保持关闭；已提供的 hash 必须是有效 SHA-256。
- 四核心接口即使全部成功也不能替代七类 market-data boundary 的独立真实证据；supporting-evidence hash 只是 provenance commitment，不是真实性证明；执行时间 offset 门禁也只固定日期基准，不是真实数据证明。
- 没有真实 provider call、没有读取凭据、没有真实行情、没有真实收益证据。
- 首个真实 provider evidence 与真实 `BOUND_UNOPENED` binding 均仍为 `PENDING_LICENSED_REAL_DATA`；frozen holdout=`NOT_OPENED`，forward-paper=`NOT_STARTED`。

## Drive 与恢复证据

Drive 项目目录已经重新回读；没有发现授权真实行情数据集或真实 evaluation binding。源码检查点 `Invest_v0.1.0_source_checkpoint_20260922.zip` 的权威身份仍由 `governance/artifact_manifest.json` 记录为 Drive ID `1Iscm0akdNG5s0WNJfc83-T_eh88xIz1F`；它是冻结证据，不因后续 GitHub 可恢复增量重写。

本轮新增内容均为 GitHub 可恢复的代码、测试、文档、决策和 checkpoint，没有新的大型或不可替代二进制 artifact；Drive 不创建重复 ZIP。

## 当前唯一主线与阻塞边界

1. 仅在本地合法授权可用时执行真实供应商验证；`executed_at` 必须规范化为 `+08:00`，四个当前核心接口必须全部实际尝试并登记，成功接口字段集合和单位契约必须覆盖当前适配器所需语义。
2. 所有七类 market-data boundary 仍须真实证据；若标记 verified，必须绑定 supporting-evidence SHA-256。哈希本身不能替代对证据内容和许可的审查。
3. provider evidence 无已知 blocker 后，才能在任何 frozen holdout 结果被读取之前建立首个 `BOUND_UNOPENED` binding，并运行 `invest/evaluation.py`。
4. 只有 opening blockers 全部闭环后才首次观察 holdout；之后 append-only forward-paper，不回填事后信号。
5. 合法真实数据仍不可用时，只推进与上述主线直接相关、可独立验证且不制造伪证据的治理、对抗测试或研究准备。

当前最新检查点为 `governance/checkpoints/20260925_provider_validation_license_provenance_gate.json`，对应决策为 `governance/decisions/D020_provider_validation_license_provenance_gate.json`。真实供应商 runbook 的许可证据哈希文字说明仍有一个非阻塞同步项；机器校验器与 evidence format 已作为当前准确契约。
