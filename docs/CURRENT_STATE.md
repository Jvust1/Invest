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
| Provider evidence 最新已验证代码/文档 head | `4cbb66fb1c021d998368ee75f468e5be3e498f95` |
| 最新 Provider evidence CI | run `35988041656` 成功：Ubuntu/Windows × Python 3.11/3.12 四组合 standard-library tests 与源码编译全部通过 |

安全 bootstrap 与 Drive 项目登记已完成。功能 PR 不自动合并，也不直接写 main。最新 provider-evidence 门禁新增“成功接口不得为空”的 fail-closed 约束并完成远端矩阵验证；后续治理提交本身仍须以实时 PR/head/checks 为准。

另有未合并的并行文档 PR #1：`docs/long-term-roadmap-20260922`，仅修改 README 与 `docs/LONG_TERM_ROADMAP.md`。本功能线不修改该分支；未来处理合并顺序时需保留应用 README 使用说明与长期路线图入口。

## 已实现

- Python 3.11+ 标准库本机中文网页，默认 `127.0.0.1:8765`，无需 Node 构建或模型 API Key。
- CSV 行情与独立交易日历导入、来源及未复权/股单位声明、数据指纹和逐字段审计；内置 140 个合成日期 × 2 个代码的确定性示例。
- 算术研究摘要、日频均线策略与同区间买入持有基准；明确固定费用情景、信号与成交日期、拒单原因和最终持仓估值。
- 人民币现金历史模拟账本、T+1、整手买入、追加交易记录、持仓估值与研究笔记；数据及结果本地持久化，JSON 导出不包含私人账户和笔记。
- Tushare 四接口研究导入适配器；凭据只从服务进程环境读取。该路径不能证明停牌和公司行动完整，继续阻断回测与账本执行。
- 桌面与 390px 窄屏界面、键盘操作、曲线空数据与边界值处理。
- `invest/evaluation.py` 提供离线、fail-closed 的预观察数据 binding 校验器：严格冻结授权状态、数据/代码身份、候选、三段时间窗、成本情景、基准、PIT/证券池证据和市场数据边界；递归拒绝凭据字段，未知边界保持显式 blocker，绝不把“格式通过”解释为真实数据完整或收益有效。
- 已补齐冻结协议 v1 原本明确要求但旧 binding 格式遗漏的“至少三个历史市场环境”机器门禁。每个环境必须冻结名称、日期区间与证据；少于三个、重复名称/完全重复区间、日期越过总评价边界或日期反转都会 fail closed。
- `invest/provider_validation.py` 与 [PROVIDER_VALIDATION_EVIDENCE_FORMAT.md](PROVIDER_VALIDATION_EVIDENCE_FORMAT.md) 把真实供应商验证 runbook 的脱敏结果变成机器可检查记录；递归拒绝 Token/secret/password/API key/cookie 等凭据字段，允许真实失败与 `unknown` / `not_covered` 被诚实保存，但只有真实数据、全部接口成功、七类市场边界全 verified、无 blocker 且 holdout 未观察时才给出 provider-side readiness。这个 readiness 仍不能替代 `BOUND_UNOPENED` evaluation binding。
- 2026-09-24 新增 provider-evidence 对抗门禁：任何 `status=success` 的接口必须同时包含至少一个非空字段且 `row_count > 0`；空 schema 或 0 行响应不能再作为“成功”参与 provider-side readiness。真实失败请求仍可保留空字段与 0 行并保持 fail closed。

执行范围限沪深主板格式代码、日频、现金、仅做多和单股票策略回测。代码格式通过不等于上市状态、交易资格或风险警示历史经过验证。缺日历、未知关键状态、公司行动或复权因子变化均不能被静默绕过。具体契约见 [DATA_FORMAT.md](DATA_FORMAT.md) 与 [ARCHITECTURE_INVARIANTS.md](ARCHITECTURE_INVARIANTS.md)。

## 验证状态

| 验证层 | 结果 |
| --- | --- |
| 基础应用 unittest | 82 PASS：data 35、engine 20、portfolio 16、server 11（历史已验证应用/测试 head） |
| 当前完整测试集 | **110 tests**：基础 82 + evaluation 13 + provider evidence 15；最新 GitHub Actions 全套 discover 通过 |
| 独立审查 | 8 组检查通过 |
| UI 代理 Playwright | 使用本机真实应用 API 的全流程通过；含研究、回测、账本、笔记、导入、导出、刷新、窄屏与键盘 |
| 曲线专用 fixtures | `empty`、`singlezero`、`constantmissingbenchmark` 共 3 组通过 |
| 主执行者独立 Playwright | 10 条检查全部通过，无 JavaScript 异常或 console errors |
| 目视检查 | 桌面与 390px 截图已检查 |
| 历史应用 GitHub Actions | **PASS**：run `35701856144`，Ubuntu/Windows × Python 3.11/3.12 四组合均完成基础 82 项单测与源码编译 |
| Evaluation binding validator | **13 个测试方法**；历史市场环境不足、重复名称/区间、越界和日期反转等反例 fail closed |
| Provider evidence validator | **15 个测试方法**；覆盖未知边界、显式 blocker、真实失败请求、授权、holdout 未观察、凭据禁止、重复接口、样本窗、canonical evidence ID，以及“成功但字段为空/0 行”反例 |
| 最新 Provider evidence GitHub Actions | **PASS**：head `4cbb66fb1c021d998368ee75f468e5be3e498f95`，run `35988041656`；Ubuntu/Windows × Python 3.11/3.12 四个 job 的 standard-library tests 与 compile source 均通过 |

“真实应用 API”指本机 Invest HTTP 服务，不指真实行情供应商或券商。当前 provider evidence 测试只验证证据格式与 fail-closed 语义，**本轮没有真实 provider call、没有真实数据、没有凭据、没有收益证据**。远端 Windows runner 单测/编译通过也不等同于 Windows 桌面浏览器和 `start.bat` 人工体验验收。证据索引见 [EVALUATION_LEDGER.md](EVALUATION_LEDGER.md) 与 `governance/checkpoints/`。

## 尚未完成的验证与能力

尚未使用真实 Tushare Token 联调，因此权限、实际返回字段、停牌缺行和公司行动覆盖仍未验收；Windows 桌面浏览器与 `start.bat` 人工体验也未完成。没有真实行情收益、冻结样本外表现或前向模拟证据。

企业行动现金流、送转/配股、红利税、完整风险警示历史、历史费率重建、盘口与部分成交、全市场存活偏差处理、PIT 基本面、ETF/其他板块和券商连接均不在当前实现范围。没有 AI 预测、荐股概率、真实账户读取或自动下单。

## 评价协议、provider evidence 与 binding 状态

样本外与 forward-paper 的**方法协议 v1 已冻结**，见 [EVALUATION_PROTOCOL_V1.md](EVALUATION_PROTOCOL_V1.md) 和 `governance/evaluation_protocol_v1.json`。当前状态是：

- 方法：`FROZEN_METHOD_V1`
- 真实供应商执行手册：`RUNBOOK_READY`
- Provider evidence 格式/校验器：`FORMAT_READY / REMOTE_CI_VALIDATED / EMPTY_SUCCESS_FAIL_CLOSED`
- 首个真实 provider evidence：`PENDING_LICENSED_REAL_DATA`
- 首个授权真实数据 binding：`PENDING_LICENSED_REAL_DATA`
- Binding 格式/校验器：`FORMAT_READY / REMOTE_CI_VALIDATED`
- 历史市场环境门禁：`REQUIRED / MINIMUM_3 / REMOTE_CI_VALIDATED`
- Frozen holdout：`NOT_OPENED`
- Forward-paper：`NOT_STARTED`

Provider evidence 校验器允许把真实失败与未知市场边界如实登记，但 fail closed；成功接口现在还必须有非空字段和正行数。即便所有 provider-side 条件都闭环，也只能说明供应商证据这一侧无已知 blocker。真实 `BOUND_UNOPENED` binding 仍须在任何 holdout 观察前独立冻结并通过 `invest/evaluation.py`，不能把 provider evidence 格式通过解释为 holdout 已获授权，更不能解释为策略有效。

## Drive 与真实数据门禁

2026-09-24 再次读取 Invest Drive 项目目录，仍只发现既有 `Invest_v0.1.0_source_checkpoint_20260922.zip` 与 `05_Reference_Materials`，没有新的已授权真实行情数据集或真实 evaluation binding。既有 source checkpoint 保持冻结，不因 GitHub 可恢复的代码/治理增量重写；本轮没有 provider call、没有读取或保存 Token、没有打开 frozen holdout，也没有为制造进度创建重复 Drive ZIP。

## 下一步

1. 在本地合法授权可用时，按 [REAL_DATA_PROVIDER_VALIDATION_RUNBOOK.md](REAL_DATA_PROVIDER_VALIDATION_RUNBOOK.md) 执行最小真实供应商验证，把脱敏结果保存为 [PROVIDER_VALIDATION_EVIDENCE_FORMAT.md](PROVIDER_VALIDATION_EVIDENCE_FORMAT.md) 记录，并先通过 `invest/provider_validation.py`；真实失败、空成功响应、unknown/not_covered 都必须 fail closed，不伪装成成功。
2. 只有 provider evidence 这一侧无已知 blocker 后，才在**读取 holdout 结果之前**按冻结 v1 协议创建首个 `BOUND_UNOPENED` binding，固定 development / validation / holdout、至少三个历史市场环境、候选、参数、成本情景、基准、证券池/PIT 和数据身份，并要求 `invest/evaluation.py` 校验通过。
3. 只有全部 opening blockers 关闭后才首次观察 frozen holdout；之后开始 append-only forward-paper，不回填事后信号，也不把格式/CI 通过解释为收益有效。
4. 合法真实数据仍不可用时，只推进与真实数据门禁直接相关的 credential-free 对抗测试、治理或研究准备，不用 mock/合成数据冒充 provider 证据。

最新 provider-evidence 门禁代码/文档 head `4cbb66fb1c021d998368ee75f468e5be3e498f95` 已完成四矩阵 GitHub Actions 验证。对应决策记录为 `governance/decisions/D013_provider_validation_nonempty_success_gate.json`，checkpoint 为 `governance/checkpoints/20260924_provider_validation_nonempty_success_gate.json`。PR #2 继续保持 Draft，合并仍需针对该具体 PR 的明确授权。
