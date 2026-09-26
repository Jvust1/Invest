# 当前状态

更新时间：2026-09-26。本文记录 v0.1 当前功能分支的真实远端状态；分支、PR 与 CI 的实时事实仍以 GitHub 为准。

## 代码与发布位置

| 项目 | 当前记录 |
| --- | --- |
| 仓库 | `Jvust2/Invest`，stable ID `1381007406` |
| 实现开始前 main | `71b32347fd954b7952f748b852503779851dbf1a` |
| 已完成的安全治理 bootstrap | `172803ad30cd2065719944f1fab26a952c42be54` |
| 功能分支 | `feat/a-share-research-v0.1-20260922` |
| 功能 PR | Draft PR #2 → `main`；未合并 |
| 最新已验证代码 head | `af60cf663ad2bb5aa237d82171969832f399588b` |
| 最新 GitHub Actions CI | run `36170981233` 成功：Ubuntu/Windows × Python 3.11/3.12 四组合 standard-library tests 与源码编译全部通过 |

历史安全 bootstrap 与 Drive 项目登记已完成；当前权威治理为 `security_status=NO_PROJECT_SECURITY_GATE`，目标分支已正式移除 `SECURITY_POLICY.md`，其缺失不构成阻塞，也不得恢复旧安全基线。功能 PR 不自动合并，也不直接写 main。

Provider-evidence 门禁当前同时要求：成功接口具有非空 schema 与正行数；样本证券代码落在 Invest v1 支持的沪深主板格式范围；样本结束日期不得晚于证据执行日期；`executed_at` 必须使用与 `Asia/Shanghai` 市场时间契约一致的 `+08:00` UTC offset；`daily`、`adj_factor`、`stk_limit`、`trade_cal` 四个当前核心接口全部存在；标记成功的核心接口必须覆盖当前适配器实际要求的字段集合；证据单位必须严格匹配当前 Tushare 适配器语义：`CNY`、`CNY/share`、输入 `lot`、输出 `share`、`Asia/Shanghai`；并且七类 market-data boundary 中任何标记 `verified` 的项，都必须绑定一个小写 64 位 supporting-evidence SHA-256。缺核心接口、缺适配器必需字段、单位契约不一致、执行时间 offset 与市场时间不一致，把 boundary 仅用自由文本升级为 verified，或授权状态缺少有效 `license_evidence_sha256` 时都保持 fail closed。

另有未合并的并行文档 PR #1：`docs/long-term-roadmap-20260922`，仅修改 README 与 `docs/LONG_TERM_ROADMAP.md`。本功能线不修改该分支；未来处理合并顺序时需保留应用 README 使用说明与长期路线图入口。

## 已实现

- Python 3.11+ 标准库本机中文网页，默认 `127.0.0.1:8765`，无需 Node 构建或模型 API Key。
- CSV 行情与独立交易日历导入、来源及未复权/股单位声明、数据指纹和逐字段审计；内置 140 个合成日期 × 2 个代码的确定性示例。
- 算术研究摘要、日频均线策略与同区间买入持有基准；明确固定费用情景、信号与成交日期、拒单原因和最终持仓估值。
- 人民币现金历史模拟账本、T+1、整手买入、追加交易记录、持仓估值与研究笔记；数据及结果本地持久化，JSON 导出不包含私人账户和笔记。
- Tushare 四接口研究导入适配器；凭据只从服务进程环境读取。该路径不能证明停牌和公司行动完整，继续阻断回测与账本执行。
- 桌面与 390px 窄屏界面、键盘操作、曲线空数据与边界值处理。
- `invest/evaluation.py` 提供离线、fail-closed 的预观察数据 binding 校验器：严格冻结授权状态、数据/代码身份、候选、三段时间窗、成本情景、基准、PIT/证券池证据和市场数据边界；递归拒绝凭据字段，未知边界保持显式 blocker。
- 冻结协议 v1 要求至少三个历史市场环境，binding 校验器已机器化门禁。
- `invest/provider_validation.py` 与证据格式把真实供应商验证 runbook 的脱敏结果变成机器可检查记录；递归拒绝凭据字段，允许真实失败与 `unknown` / `not_covered` 被诚实保存。
- Provider evidence 已依次加固：成功接口非空字段/正行数；样本主板范围和执行时间；四核心接口完整性；核心接口适配器必需字段；严格单位契约；verified market-data boundary supporting-evidence SHA-256 provenance commitment；以及 `executed_at` 必须与 `Asia/Shanghai` 的 `+08:00` 日期语义一致。
- `BOUND_UNOPENED` evaluation binding 现在必须引用 provider evidence 的 `evidence_id` 与 `license_evidence_sha256`，并要求 provider evidence 的 raw/normalized/code 身份与 binding dataset 一致；binding 中任何 `verified` market-data boundary 也必须带 supporting-evidence SHA-256。

执行范围限沪深主板格式代码、日频、现金、仅做多和单股票策略回测。代码格式通过不等于上市状态、交易资格或风险警示历史经过验证。缺日历、未知关键状态、公司行动或复权因子变化均不能被静默绕过。

## 验证状态

| 验证层 | 结果 |
| --- | --- |
| 基础应用 unittest | 82 PASS |
| 当前完整测试集 | **130 tests**；opening continuity 模块 6 个测试方法；GitHub Actions 全套 discover 通过 |
| 独立审查 | 8 组检查通过 |
| UI 代理 Playwright | 使用本机真实应用 API 的全流程通过 |
| 曲线专用 fixtures | 3 组通过 |
| 主执行者独立 Playwright | 10 条检查全部通过，无 JavaScript 异常或 console errors |
| Evaluation binding validator | **15 个测试方法**；历史市场环境、provider evidence 身份桥、verified boundary supporting-evidence hash 等反例 fail closed |
| Provider evidence validator | **23 个测试方法**；新增 `executed_at` 非 `+08:00` 的 UTC/Z 与 `+09:00` 两类反例，避免样本结束日期与市场日期语义错位 |
| 最新 GitHub Actions | **PASS**：head `af60cf663ad2bb5aa237d82171969832f399588b`，run `36170981233`；Ubuntu/Windows × Python 3.11/3.12 四个 job 的 tests 与 compile source 全部通过，完整测试集 **130 tests** |

当前 provider evidence 测试只验证证据格式与 fail-closed 语义，**没有真实 provider call、没有真实数据、没有凭据、没有收益证据**。supporting-evidence SHA-256 只冻结 provenance identity，不证明 artifact 内容、许可或 boundary 判断真实正确。远端 Windows runner 单测/编译通过也不等同于 Windows 桌面浏览器和 `start.bat` 人工体验验收。

## 评价协议、provider evidence 与 binding 状态

- 方法：`FROZEN_METHOD_V1`
- 真实供应商执行手册：`RUNBOOK_READY`
- Provider evidence：`FORMAT_READY / REMOTE_CI_VALIDATED / LICENSE_PROVENANCE_AND_EXISTING_GATES_FAIL_CLOSED`
- 首个真实 provider evidence：`PENDING_LICENSED_REAL_DATA`
- 首个授权真实数据 binding：`PENDING_LICENSED_REAL_DATA`
- Frozen holdout：`NOT_OPENED`
- Forward-paper：`NOT_STARTED`

即便四个核心接口全部记录且成功，也不能把四接口本身解释为停牌、公司行动、风险警示历史、存活偏差或 PIT 全部覆盖；七类 boundary 仍须逐项有真实证据。verified boundary 的哈希只保证声明绑定到稳定 evidence identity，不保证证据本身足够。执行时间 offset 门禁只保证日期比较处于同一市场时间语义，也不证明数据真实或完整。即便 provider-side 条件全部闭环，也只说明供应商证据这一侧没有已知 blocker；真实 `BOUND_UNOPENED` binding 还必须在任何 holdout 观察前冻结并通过 `invest/evaluation.py`，且其 provider evidence 身份桥和 verified-boundary hash 必须与冻结证据一致。

## Drive 与真实数据门禁

2026-09-25 再次读取 Invest Drive 项目目录，没有发现新的已授权真实行情数据集或真实 evaluation binding。既有 source checkpoint `Invest_v0.1.0_source_checkpoint_20260922.zip` 保持冻结，不因 GitHub 可恢复的代码/治理增量重写；本轮没有 provider call、没有读取或保存 Token、没有打开 frozen holdout，也没有制造重复 Drive ZIP。

## 下一步

1. 在本地合法授权可用时，按 `docs/REAL_DATA_PROVIDER_VALIDATION_RUNBOOK.md` 执行最小真实供应商验证；`executed_at` 规范化为 `+08:00`，四个核心接口均须实际尝试，成功项字段集合与单位契约必须覆盖当前适配器需求，任何 verified boundary 必须冻结 supporting-evidence SHA-256，并提供有效 `provider.license_evidence_sha256`。
2. 只有 provider evidence 这一侧无已知 blocker 后，才在读取 holdout 结果之前按冻结 v1 协议创建首个 `BOUND_UNOPENED` binding；binding 必须引用其 `evidence_id` / `license_evidence_sha256`，并保持 raw/normalized/code 身份一致，所有 verified boundary 继续绑定 supporting-evidence SHA-256。
3. 只有全部 opening blockers 关闭后才首次观察 frozen holdout；之后开始 append-only forward-paper。
4. 合法真实数据仍不可用时，只推进与真实数据门禁直接相关的 credential-free 对抗测试、治理或研究准备，不用 mock/合成数据冒充 provider 证据。

opening continuity 的最新技术决策为 `governance/decisions/D023_provider_binding_pair_continuity_gate.json`，对应验证记录为 `governance/evaluations/E011_provider_binding_pair_continuity_gate.json`。当前治理检查点为 `governance/checkpoints/20260926_governance_text_alignment_closed.json`；Pre-flight/Handoff/README 中遗留的历史安全门禁文字已对齐现行 `NO_PROJECT_SECURITY_GATE` 状态。PR #2 继续保持 Draft，合并仍需针对该具体 PR 的明确授权。


## 2026-09-25 Provider 授权 provenance 门禁

Provider evidence 的 `license_status=authorized` 现在必须同时绑定一个小写 64 位 `license_evidence_sha256`。该哈希用于固定本地许可证据的 provenance 身份，不独立证明授权真实性或适用范围。缺失或格式错误会使整条 evidence 结构校验失败。

代码 head `6db24bb3cde003f937a73dc5a5eb2041181af505` 的 GitHub Actions run `36089180871` 已完成并成功；Ubuntu/Windows × Python 3.11/3.12 四个矩阵作业的完整测试与源码编译均通过。完整测试集为 **118 tests**，其中 provider evidence 测试方法为 **23**。本轮没有真实 provider call、没有真实市场数据、没有真实 provider evidence、没有真实 `BOUND_UNOPENED` binding，也没有打开 frozen holdout。


## 2026-09-25 Provider evidence → binding provenance bridge

代码 head `c6ada411910d0e904fbaf1fbcec0ef399a1a9ea7` 将真实 provider evidence 与首个 `BOUND_UNOPENED` evaluation binding 的 provenance 机器化绑定：binding 必须保存 provider `evidence_id` / `license_evidence_sha256`，provider raw/normalized/code 身份必须与 binding dataset 一致；任何 binding boundary 标记 `verified` 时都必须有 supporting-evidence SHA-256。

GitHub Actions run `36093418179` 已 completed/success；Ubuntu/Windows × Python 3.11/3.12 四个矩阵作业的 tests 与源码编译均成功，Ubuntu/Python 3.12 日志确认 **Ran 120 tests**。本轮仍没有真实 provider call、没有凭据、没有真实行情、没有真实 provider evidence、没有真实 binding，也没有打开 frozen holdout。

## 2026-09-26 — AKShare research connector

- Added optional `akshare==1.18.97` integration for real unadjusted A-share daily bars.
- New local endpoint: `POST /api/datasets/akshare`.
- New web form under Data Management; no API token is required.
- Adapter converts AKShare volume from hands to shares and cross-checks the independent trade calendar when available.
- Missing suspension/corporate-action/price-limit/adjustment/PIT evidence remains unknown and continues to block simulated execution.
- Unit tests use injected fake provider frames; no live provider request or real market result is claimed by this repository update.
- Tushare provider-validation flow remains available for users with authorized credentials.
