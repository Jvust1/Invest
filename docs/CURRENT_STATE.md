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
| 远端 CI | GitHub Actions run `35701856144` 成功：Ubuntu/Windows × Python 3.11/3.12 四组合全部通过 |

安全 bootstrap 与 Drive 项目登记已完成。功能 PR 不自动合并，也不直接写 main。远端 CI 已从“未知”推进为“已验证成功”，但后续治理提交本身仍须以实时 PR/head/checks 为准。

另有未合并的并行文档 PR #1：`docs/long-term-roadmap-20260922`，仅修改 README 与 `docs/LONG_TERM_ROADMAP.md`。本功能线不修改该分支；未来处理合并顺序时需保留应用 README 使用说明与长期路线图入口。

## 已实现

- Python 3.11+ 标准库本机中文网页，默认 `127.0.0.1:8765`，无需 Node 构建或模型 API Key。
- CSV 行情与独立交易日历导入、来源及未复权/股单位声明、数据指纹和逐字段审计；内置 140 个合成日期 × 2 个代码的确定性示例。
- 算术研究摘要、日频均线策略与同区间买入持有基准；明确固定费用情景、信号与成交日期、拒单原因和最终持仓估值。
- 人民币现金历史模拟账本、T+1、整手买入、追加交易记录、持仓估值与研究笔记；数据及结果本地持久化，JSON 导出不包含私人账户和笔记。
- Tushare 四接口研究导入适配器；凭据只从服务进程环境读取。该路径不能证明停牌和公司行动完整，继续阻断回测与账本执行。
- 桌面与 390px 窄屏界面、键盘操作、曲线空数据与边界值处理。

执行范围限沪深主板格式代码、日频、现金、仅做多和单股票策略回测。代码格式通过不等于上市状态、交易资格或风险警示历史经过验证。缺日历、未知关键状态、公司行动或复权因子变化均不能被静默绕过。具体契约见 [DATA_FORMAT.md](DATA_FORMAT.md) 与 [ARCHITECTURE_INVARIANTS.md](ARCHITECTURE_INVARIANTS.md)。

## 验证状态

| 验证层 | 结果 |
| --- | --- |
| 标准库 unittest | 82 PASS：data 35、engine 20、portfolio 16、server 11 |
| 独立审查 | 8 组检查通过 |
| UI 代理 Playwright | 使用本机真实应用 API 的全流程通过；含研究、回测、账本、笔记、导入、导出、刷新、窄屏与键盘 |
| 曲线专用 fixtures | `empty`、`singlezero`、`constantmissingbenchmark` 共 3 组通过 |
| 主执行者独立 Playwright | 10 条检查全部通过，无 JavaScript 异常或 console errors |
| 目视检查 | 桌面与 390px 截图已检查 |
| GitHub Actions | **PASS**：run `35701856144`，Ubuntu/Windows × Python 3.11/3.12 四组合均完成 82 项单测与源码编译 |

“真实应用 API”指本机 Invest HTTP 服务，不指真实行情供应商或券商。验证使用合成数据与测试构造输入，不支持任何收益能力结论。远端 Windows runner 的单测/编译通过也不等同于 Windows 桌面浏览器和 `start.bat` 人工体验验收。证据索引见 [EVALUATION_LEDGER.md](EVALUATION_LEDGER.md) 与 `governance/checkpoints/20260923_ci_reconciliation.json`。

## 尚未完成的验证与能力

尚未使用真实 Tushare Token 联调，因此权限、实际返回字段、停牌缺行和公司行动覆盖仍未验收；Windows 桌面浏览器与 `start.bat` 人工体验也未完成。没有真实行情收益、冻结样本外表现或前向模拟证据。

企业行动现金流、送转/配股、红利税、完整风险警示历史、历史费率重建、盘口与部分成交、全市场存活偏差处理、PIT 基本面、ETF/其他板块和券商连接均不在当前实现范围。没有 AI 预测、荐股概率、真实账户读取或自动下单。

## 下一步

1. 在本地授权可用时，完成真实 Tushare 供应商验证，并显式核对权限、单位、交易日历、停牌缺行及企业行动边界；未知状态继续阻断执行，Token 不进入仓库、聊天或共享 artifact。
2. 在解释任何策略收益前，定义并冻结样本外与 forward-paper 评价协议，明确开发样本、首次观察留出集、成本情景、基准、存活偏差与后续前向记录方式。

当前不需要重复检查已成功的远端 CI，也不得把 CI 成功推导为收益有效、真实供应商完整或 PR 已获合并授权。
