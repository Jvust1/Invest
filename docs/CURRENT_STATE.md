# 当前状态

更新时间：2026-09-22。本文是 v0.1 实现的**提交前本地工作树快照**，不表示功能分支、草稿 PR 或 CI 已发布、运行或通过。最终提交、分支和 PR 状态以 GitHub 实时记录为准。

## 代码与发布位置

| 项目 | 本次记录 |
| --- | --- |
| 仓库 | `Jvust2/Invest`，stable ID `1381007406` |
| 实现开始前 main | `71b32347fd954b7952f748b852503779851dbf1a` |
| 已完成的安全治理 bootstrap | `172803ad30cd2065719944f1fab26a952c42be54` |
| 计划功能分支 | `feat/a-share-research-v0.1-20260922` |
| 计划审查方式 | 单个草稿 PR，目标 `main`；本快照时尚未发布 |
| CI | 发布前状态未知；本地通过不等于 Actions 通过 |

安全 bootstrap 与 Drive 项目登记已完成。本轮功能发布由主执行者统一进行；不自动合并，也不在状态文档中预填未产生的功能提交 SHA 或 PR 编号。

另有未合并的并行文档 [PR #1](https://github.com/Jvust2/Invest/pull/1)：`docs/long-term-roadmap-20260922`，head `4fc6e668cd60f544809a0a204ad688c2edf37961`，base 为 `security-bootstrap`，仅修改 README 与 `docs/LONG_TERM_ROADMAP.md`。本轮不修改该分支或 PR；后续处理合并顺序时需保留双方 README 入口。

## 已实现

- Python 3.11+ 标准库本机中文网页，默认 `127.0.0.1:8765`，无需 Node 构建或模型 API Key。
- CSV 行情与独立交易日历导入、来源及未复权/股单位声明、数据指纹和逐字段审计；内置 140 个合成日期 × 2 个代码的确定性示例。
- 算术研究摘要、日频均线策略与同区间买入持有基准；明确固定费用情景、信号与成交日期、拒单原因和最终持仓估值。
- 人民币现金历史模拟账本、T+1、整手买入、追加交易记录、持仓估值与研究笔记；数据及结果本地持久化，JSON 导出不包含私人账户和笔记。
- Tushare 四接口研究导入适配器；凭据只从服务进程环境读取。该路径不能证明停牌和公司行动完整，继续阻断回测与账本执行。
- 桌面与 390px 窄屏界面、键盘操作、曲线空数据与边界值处理。

执行范围限沪深主板格式代码、日频、现金、仅做多和单股票策略回测。代码格式通过不等于上市状态、交易资格或风险警示历史经过验证。缺日历、未知关键状态、公司行动或复权因子变化均不能被静默绕过。具体契约见 [DATA_FORMAT.md](DATA_FORMAT.md) 与 [ARCHITECTURE_INVARIANTS.md](ARCHITECTURE_INVARIANTS.md)。

## 本地验证状态

| 验证层 | 结果 |
| --- | --- |
| 标准库 unittest | 82 PASS：data 35、engine 20、portfolio 16、server 11 |
| 独立审查 | 8 组检查通过 |
| UI 代理 Playwright | 使用本机真实应用 API 的全流程通过；含研究、回测、账本、笔记、导入、导出、刷新、窄屏与键盘 |
| 曲线专用 fixtures | `empty`、`singlezero`、`constantmissingbenchmark` 共 3 组通过 |
| 主执行者独立 Playwright | 10 条检查全部通过，无 JavaScript 异常或 console errors |
| 目视检查 | 桌面与 390px 截图已检查 |

“真实应用 API”指本机 Invest HTTP 服务，不指真实行情供应商或券商。验证使用合成数据与测试构造输入，不支持任何收益能力结论。证据索引、覆盖细节和复跑条件见 [EVALUATION_LEDGER.md](EVALUATION_LEDGER.md)。

## 尚未完成的验证与能力

未使用真实 Tushare Token 联调；未在 Windows 运行，也未验证 GitHub Actions；没有真实行情收益、样本外表现或前向模拟证据。`start.bat` 存在不代表 Windows 已验收。

企业行动现金流、送转/配股、红利税、完整风险警示历史、历史费率重建、盘口与部分成交、全市场存活偏差处理、PIT 基本面、ETF/其他板块和券商连接均不在当前实现范围。没有 AI 预测、荐股概率、真实账户读取或自动下单。

下一位接手者先按 [HANDOFF.md](HANDOFF.md) 恢复真实分支、证据与未完成事项，再决定下一阶段工作。
