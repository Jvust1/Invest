# 当前状态

更新时间：2026-09-24。本文记录 v0.1 当前功能分支的真实远端状态；分支、PR 与 CI 的实时事实仍以 GitHub 为准。

## 代码与发布位置

| 项目 | 当前记录 |
| --- | --- |
| 仓库 | `Jvust2/Invest`，stable ID `1381007406` |
| 实现开始前 main | `71b32347fd954b7952f748b852503779851dbf1a` |
| 已完成的安全治理 bootstrap | `172803ad30cd2065719944f1fab26a952c42be54` |
| 功能分支 | `feat/a-share-research-v0.1-20260922` |
| 功能 PR | Draft PR #2 → `main`；未合并 |
| 已验证应用/测试 head | `f40b0285b1c2bb249464f2ec354e9eb3bb6b18df` |
| Evaluation binding 门禁代码 head | `7629e221619f22500dc2016f2bf698eb055f50f2` |
| Provider evidence 最新已验证代码/文档 head | `9d0e66fef88e6b1dc00effa8358c9c4c9225d6af` |
| 最新 Provider evidence CI | run `36007383127` 成功：Ubuntu/Windows × Python 3.11/3.12 四组合 standard-library tests 与源码编译全部通过 |

安全 bootstrap 与 Drive 项目登记已完成。功能 PR 不自动合并，也不直接写 main。Provider-evidence 门禁当前同时要求：成功接口具有非空 schema 与正行数；样本证券代码落在 Invest v1 支持的沪深主板格式范围；样本结束日期不得晚于证据执行日期；`daily`、`adj_factor`、`stk_limit`、`trade_cal` 四个当前核心接口全部存在；并且标记成功的核心接口必须覆盖当前适配器实际要求的字段集合。缺核心接口或缺适配器必需字段时都保持 fail closed。

另有未合并的并行文档 PR #1：`docs/long-term-roadmap-20260922`，仅修改 README 与 `docs/LONG_TERM_ROADMAP.md`。本功能线不修改该分支；未来处理合并顺序时需保留应用 README 使用说明与长期路线图入口。

## 已实现

- Python 3.11+ 标准库本机中文网页，默认 `127.0.0.1:8765`，无需 Node 构建或模型 API Key。
- CSV 行情与独立交易日历导入、来源及未复权/股单位声明、数据指纹和逐字段审计；内置 140 个合成日期 × 2 个代码的确定性示例。
- 算术研究摘要、日频均线策略与同区间买入持有基准；明确固定费用情景、信号与成交日期、拒单原因和最终持仓估值。
- 人民币现金历史模拟账本、T+1、整手买入、追加交易记录、持仓估值与研究笔记；数据及结果本地持久化，JSON 导出不包含私人账户和笔记。
- Tushare 四接口研究导入适配器；凭据只从服务进程环境读取。该路径不能证明停牌和公司行动完整，继续阻断回测与账本执行。
- 桌面与 390px 窄屏界面、键盘操作、曲线空数据与边界值处理。
- `invest/evaluation.py` 提供离线、fail-closed 的预观察数据 binding 校验器：严格冻结授权状态、数据/代码身份、候选、三段时间窗、成本情景、基准、PIT/证券池证据和市场数据边界；递归拒绝凭据字段，未知边界保持显式 blocker，绝不把“格式通过”解释为真实数据完整或收益有效。
- 已补齐冻结协议 v1 原本明确要求但旧 binding 格式遗漏的“至少三个历史市场环境”机器门禁。
- `invest/provider_validation.py` 与证据格式把真实供应商验证 runbook 的脱敏结果变成机器可检查记录；递归拒绝凭据字段，允许真实失败与 `unknown` / `not_covered` 被诚实保存。
- Provider evidence 第一轮加固：`status=success` 必须同时有非空字段且 `row_count > 0`。
- 第二轮加固：样本代码必须属于当前 v1 沪深主板格式，`sample.end_date` 不得晚于 `executed_at` 所在日期。
- 第三轮加固：当前四个核心接口 `daily`、`adj_factor`、`stk_limit`、`trade_cal` 必须全部明确出现；部分真实尝试仍可保存，但缺失任何核心接口都会阻断 provider-side readiness。
- 第四轮加固：成功的核心接口必须至少包含当前 `invest/data.py` 适配器真实请求所需字段；`daily` 要求 `ts_code/trade_date/OHLC/vol`，`adj_factor` 要求 `ts_code/trade_date/adj_factor`，`stk_limit` 要求 `ts_code/trade_date/up_limit/down_limit`，`trade_cal` 要求 `exchange/cal_date/is_open`。额外字段允许，但缺任何必需字段都会拒绝整条成功证据；真实失败接口仍可保存空或部分字段。

执行范围限沪深主板格式代码、日频、现金、仅做多和单股票策略回测。代码格式通过不等于上市状态、交易资格或风险警示历史经过验证。缺日历、未知关键状态、公司行动或复权因子变化均不能被静默绕过。

## 验证状态

| 验证层 | 结果 |
| --- | --- |
| 基础应用 unittest | 82 PASS |
| 当前完整测试集 | **114 tests**：基础 82 + evaluation 13 + provider evidence 19；最新 GitHub Actions 全套 discover 通过 |
| 独立审查 | 8 组检查通过 |
| UI 代理 Playwright | 使用本机真实应用 API 的全流程通过 |
| 曲线专用 fixtures | 3 组通过 |
| 主执行者独立 Playwright | 10 条检查全部通过，无 JavaScript 异常或 console errors |
| Evaluation binding validator | 13 个测试方法；历史市场环境等反例 fail closed |
| Provider evidence validator | **19 个测试方法**；新增“成功核心接口缺少任一当前适配器必需字段时拒绝证据”的四接口子案例 |
| 最新 Provider evidence GitHub Actions | **PASS**：head `9d0e66fef88e6b1dc00effa8358c9c4c9225d6af`，run `36007383127`；Ubuntu/Windows × Python 3.11/3.12 四个 job 的 tests 与 compile source 全部通过 |

当前 provider evidence 测试只验证证据格式与 fail-closed 语义，**没有真实 provider call、没有真实数据、没有凭据、没有收益证据**。远端 Windows runner 单测/编译通过也不等同于 Windows 桌面浏览器和 `start.bat` 人工体验验收。

## 评价协议、provider evidence 与 binding 状态

- 方法：`FROZEN_METHOD_V1`
- 真实供应商执行手册：`RUNBOOK_READY`
- Provider evidence：`FORMAT_READY / REMOTE_CI_VALIDATED / REQUIRED_CORE_SCHEMAS_FAIL_CLOSED`
- 首个真实 provider evidence：`PENDING_LICENSED_REAL_DATA`
- 首个授权真实数据 binding：`PENDING_LICENSED_REAL_DATA`
- Frozen holdout：`NOT_OPENED`
- Forward-paper：`NOT_STARTED`

即便四个核心接口全部记录且成功，也不能把四接口本身解释为停牌、公司行动、风险警示历史、存活偏差或 PIT 全部覆盖；七类 boundary 仍须逐项有真实证据。即便 provider-side 条件全部闭环，也只说明供应商证据这一侧没有已知 blocker，真实 `BOUND_UNOPENED` binding 仍必须在任何 holdout 观察前独立冻结并通过 `invest/evaluation.py`。

## Drive 与真实数据门禁

2026-09-24 再次读取 Invest Drive 项目目录，仍未发现新的已授权真实行情数据集或真实 evaluation binding。既有 source checkpoint `Invest_v0.1.0_source_checkpoint_20260922.zip` 保持冻结，不因 GitHub 可恢复的代码/治理增量重写；本轮没有 provider call、没有读取或保存 Token、没有打开 frozen holdout，也没有制造重复 Drive ZIP。

## 下一步

1. 在本地合法授权可用时，按 `docs/REAL_DATA_PROVIDER_VALIDATION_RUNBOOK.md` 执行最小真实供应商验证；四个核心接口均须实际尝试，成功项的字段集合必须覆盖当前适配器需求，失败/缺失/缺字段不得解释为成功。
2. 只有 provider evidence 这一侧无已知 blocker 后，才在读取 holdout 结果之前按冻结 v1 协议创建首个 `BOUND_UNOPENED` binding。
3. 只有全部 opening blockers 关闭后才首次观察 frozen holdout；之后开始 append-only forward-paper。
4. 合法真实数据仍不可用时，只推进与真实数据门禁直接相关的 credential-free 对抗测试、治理或研究准备，不用 mock/合成数据冒充 provider 证据。

最新决策为 `governance/decisions/D016_provider_validation_required_fields_gate.json`，检查点为 `governance/checkpoints/20260924_provider_validation_required_fields_gate.json`。PR #2 继续保持 Draft，合并仍需针对该具体 PR 的明确授权。
