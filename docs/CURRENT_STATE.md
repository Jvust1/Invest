# 当前状态

更新时间：2026-09-23。本文记录 v0.1 当前功能分支的真实远端状态；分支、PR 与 CI 的实时事实仍以 GitHub 为准。

## 代码与发布位置

| 项目 | 当前记录 |
| --- | --- |
| 仓库 | `Jvust2/Invest`，stable ID `1381007406` |
| 实现开始前 main | `71b32347fd954b7952f748b852503779851dbf1a` |
| 已完成的安全治理 bootstrap | `172803ad30cd2065719944f1fab26a952c42be54` |
| 功能分支 | `feat/a-share-research-v0.1-20260922` |
| 功能 PR | Draft PR #2 → `main`；未合并 |
| 已验证应用/测试 head | `f40b0285b1c2bb249464f2ec354e9eb3bb6b18df` |
| 当前评价门禁代码 head | `7629e221619f22500dc2016f2bf698eb055f50f2` |
| 远端 CI | 最新评价门禁 run `35809448144` 成功：Ubuntu/Windows × Python 3.11/3.12 四组合的 standard-library tests 与源码编译全部通过 |

安全 bootstrap 与 Drive 项目登记已完成。功能 PR 不自动合并，也不直接写 main。远端 CI 已验证当前评价门禁代码，但后续代码/治理提交本身仍须以实时 PR/head/checks 为准。

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

执行范围限沪深主板格式代码、日频、现金、仅做多和单股票策略回测。代码格式通过不等于上市状态、交易资格或风险警示历史经过验证。缺日历、未知关键状态、公司行动或复权因子变化均不能被静默绕过。具体契约见 [DATA_FORMAT.md](DATA_FORMAT.md) 与 [ARCHITECTURE_INVARIANTS.md](ARCHITECTURE_INVARIANTS.md)。

## 验证状态

| 验证层 | 结果 |
| --- | --- |
| 基础应用 unittest | 82 PASS：data 35、engine 20、portfolio 16、server 11（历史已验证应用/测试 head） |
| 当前完整测试集 | **95 tests**：基础 82 + evaluation 13；本轮 credential-free 本地重建执行 `python -m unittest discover -s tests -q` 通过 |
| 独立审查 | 8 组检查通过 |
| UI 代理 Playwright | 使用本机真实应用 API 的全流程通过；含研究、回测、账本、笔记、导入、导出、刷新、窄屏与键盘 |
| 曲线专用 fixtures | `empty`、`singlezero`、`constantmissingbenchmark` 共 3 组通过 |
| 主执行者独立 Playwright | 10 条检查全部通过，无 JavaScript 异常或 console errors |
| 目视检查 | 桌面与 390px 截图已检查 |
| 历史应用 GitHub Actions | **PASS**：run `35701856144`，Ubuntu/Windows × Python 3.11/3.12 四组合均完成基础 82 项单测与源码编译 |
| Evaluation binding validator | **13 个测试方法**；新增历史市场环境不足、重复名称/区间、越界和日期反转反例；源码编译通过 |
| 最新 Validator GitHub Actions | **PASS**：代码 head `7629e221619f22500dc2016f2bf698eb055f50f2`，run `35809448144`；Ubuntu/Windows × Python 3.11/3.12 四个 job 的 standard-library tests 与 compile source 均通过 |

“真实应用 API”指本机 Invest HTTP 服务，不指真实行情供应商或券商。验证使用合成数据与测试构造输入，不支持任何收益能力结论。远端 Windows runner 的单测/编译通过也不等同于 Windows 桌面浏览器和 `start.bat` 人工体验验收。证据索引见 [EVALUATION_LEDGER.md](EVALUATION_LEDGER.md) 与 `governance/checkpoints/`。

## 尚未完成的验证与能力

尚未使用真实 Tushare Token 联调，因此权限、实际返回字段、停牌缺行和公司行动覆盖仍未验收；Windows 桌面浏览器与 `start.bat` 人工体验也未完成。没有真实行情收益、冻结样本外表现或前向模拟证据。

企业行动现金流、送转/配股、红利税、完整风险警示历史、历史费率重建、盘口与部分成交、全市场存活偏差处理、PIT 基本面、ETF/其他板块和券商连接均不在当前实现范围。没有 AI 预测、荐股概率、真实账户读取或自动下单。

## 评价协议与 binding 状态

样本外与 forward-paper 的**方法协议 v1 已冻结**，见 [EVALUATION_PROTOCOL_V1.md](EVALUATION_PROTOCOL_V1.md) 和 `governance/evaluation_protocol_v1.json`。当前状态是：

- 方法：`FROZEN_METHOD_V1`
- 首个授权真实数据绑定：`PENDING_LICENSED_REAL_DATA`
- Binding 格式/校验器：`FORMAT_READY / REMOTE_CI_VALIDATED`
- 历史市场环境门禁：`REQUIRED / MINIMUM_3 / REMOTE_CI_VALIDATED`
- Frozen holdout：`NOT_OPENED`
- Forward-paper：`NOT_STARTED`

冻结协议 v1 第 4 节已经要求首个真实 binding 在 holdout 首次观察前固定“至少 3 个需要覆盖或单独标注的历史市场环境”。此前格式文档和校验器没有机器字段承载这项要求；由于当前仍 **没有任何真实 binding、没有打开 holdout**，本轮在首次真实 binding 出现前完成了一致性修复，而不是修改已观察结果或改变冻结方法。格式见 [EVALUATION_BINDING_FORMAT.md](EVALUATION_BINDING_FORMAT.md)。

校验器允许把未知市场数据边界如实记录为 `unknown` / `not_covered`，但会令 `can_open_holdout=false`；只有授权、身份、时间窗口、至少三个历史市场环境、候选、成本、基准和要求的数据边界均闭环且没有其它 blocker 时，才可能返回 true。这仍然只关闭治理与 provenance 缺口，不产生任何真实收益证据。真实供应商验证不能由 mock、合成数据或格式校验替代。

## Drive 与真实数据门禁

本轮重新读取 Invest Drive 项目根目录，仍只确认到 `Invest_v0.1.0_source_checkpoint_20260922.zip` 与 `05_Reference_Materials/`；没有发现新的已授权真实行情数据集或真实 evaluation binding。因此没有 provider call、没有读取或保存 Token，也没有为了制造进度打开 frozen holdout。已有源码 ZIP 保持冻结，不因 GitHub 增量重写；本轮代码/治理增量可由 GitHub 历史恢复，不需要制造重复 Drive 归档。

## 下一步

1. 在本地授权可用时，完成真实 Tushare 供应商验证，并显式核对权限、单位、交易日历、停牌缺行及企业行动边界；未知状态继续阻断执行，Token 不进入仓库、聊天或共享 artifact。
2. 首个授权真实数据集可用后，在读取 holdout 结果前按已冻结 v1 协议创建 `BOUND_UNOPENED` binding，固定 development / validation / holdout 区间、**至少三个历史市场环境**、候选、参数、成本情景、基准、证券池/PIT 证据和数据身份，并要求 `invest/evaluation.py` 校验通过；若 `can_open_holdout=false`，不得打开 holdout。
3. 只有完成冻结候选、合法数据 binding 并关闭 opening blockers 后才开始 append-only forward-paper；不得回填事后信号，也不得把协议冻结或 binding 格式通过解释为策略有效。
4. 合法真实数据仍不可用时，只推进与这条主线直接相关的 credential-free 对抗测试、治理或研究准备，不用 mock/合成数据冒充 provider 证据。

当前评价门禁代码 head `7629e221619f22500dc2016f2bf698eb055f50f2` 已完成四平台 GitHub Actions 验证。后续若继续写入新代码，仍应以新的 live head/checks 为准。PR #2 继续保持 Draft，合并仍需针对该具体 PR 的明确授权。
