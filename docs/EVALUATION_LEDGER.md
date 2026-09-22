# 验证记录

## E001 — v0.1 本地集成验收（2026-09-22）

对象：本轮待提交的本地工作树。功能提交 SHA 与草稿 PR 尚未产生，不将已完成的安全 bootstrap SHA 当成功能验证 SHA。最终关联提交以 GitHub 发布后的记录为准。

目的：验证输入、执行约束、资金账本、应用安全与主要用户流程是否按已声明的有限模型工作。输入为合成演示数据、测试 fixtures 与构造反例；没有真实行情收益评价。

### 自动化与独立检查

| 检查 | 本轮结果 | 解释边界 |
| --- | --- | --- |
| `tests/test_data.py` | 35 PASS | 数据解析、审计、身份与供应商适配的测试输入；不代表真实账号接口验收 |
| `tests/test_engine.py` | 20 PASS | 研究及有限执行模型；不代表交易所全规则复现 |
| `tests/test_portfolio.py` | 16 PASS | 历史模拟账本、资金与持仓约束；不涉及真实账户 |
| `tests/test_server.py` | 11 PASS | 本机 HTTP 与持久化/安全边界；不等于公网部署安全评估 |
| unittest 合计 | **82 PASS** | 35 + 20 + 16 + 11；本轮最终命令为 `python -m unittest discover -s tests -q` |
| 独立审查 | **8 组通过** | 独立审查脚本见下方证据索引；组数不与 unittest 数量合并 |
| 主执行者独立 Playwright | **10 条通过** | 无 JavaScript 异常或 console errors；不与 UI 代理检查重复计数 |

8 组独立审查覆盖：分位精确资金与 T+1、重新计算数据指纹、未来价格不改写过去结果、日历缺口与公司行动阻断、持仓历史修改拒绝及缺失估值为空、HTTP CSRF/Origin/JSON/有限值检查、前收盘信号与下一交易日成交、未知状态阻断。最近一次输出为 8 项通过，耗时 0.550 秒。

### UI 代理全流程

Playwright 对本机实际应用 HTTP API 的流程检查通过，覆盖：

- 加载合成数据、查看研究摘要、运行回测和显示曲线。
- 创建模拟账户、买入、当日卖出触发 T+1 拒绝、次日卖出。
- 拒绝含 HTML 的笔记，保存安全文本笔记。
- 同时导入 CSV 行情与独立日历，导出 JSON，刷新后恢复相应持久化状态。
- 390px 下四个 tab 的操作与键盘路径。

曲线另以 `empty`、`singlezero`、`constantmissingbenchmark` 三组 fixtures 检查通过，覆盖无数据、单点零值、常量序列与缺失基准的展示边界。主执行者另行目视检查了桌面和 390px 截图。

“实际应用 API”仅指正在运行的本机 Invest 服务；上述过程没有调用真实行情供应商或券商，也没有验证真实成交或盈利能力。

### 证据位置

本地已保存以下仓库相对路径；发布交接时应核对提交包含这些文件且内容对应本轮检查：

| 路径 | 用途 |
| --- | --- |
| `validation/20260922/README.md` | 验证材料说明与复查入口 |
| `validation/20260922/unittest.txt` | 82 项单测的命令输出 |
| `validation/20260922/independent-review.py` | 8 组独立审查的可复查检查逻辑 |
| `validation/20260922/independent-review.txt` | 8 组独立审查通过的命令输出 |
| `validation/20260922/browser-check.cjs` | 主执行者 10 条 Playwright 检查源码 |
| `validation/20260922/browser-results.json` | 主执行者浏览器检查结果 |

截图保存在 Drive 源码检查点 zip 内的 `review/` 路径。检查点身份以项目 artifact manifest 和 Drive 实际记录为准；本文不虚构文件 ID、下载地址或已上传状态。UI 代理流程和曲线 fixtures 的通过结论属于本轮代理验收记录，不将上述主执行者 10 条脚本描述为它们的完整复跑脚本。

### 未验证与发布状态

- 未用真实 Tushare Token 验证权限、额度或真实返回数据；供应商路径仍为研究导入。
- 未在 Windows 运行；`start.bat` 仅为提供的启动入口。
- 功能分支/草稿 PR 在本文快照时尚未发布；GitHub Actions 状态未知。
- 没有真实行情收益、冻结样本外效果、前向模拟、券商执行或实盘验证。
- 合成数据不包含真实交易所节假日和完整市场历史；测试通过不能推导出规则覆盖完整、策略有效或投资回报承诺。

任何后续修复、接口联调或真实样本评价应追加独立记录，注明真实代码身份、数据来源及指纹、环境、参数、结果和失败/未覆盖项，不覆盖本次验证边界。模型及官方规则引用见 [REFERENCES_AND_RULES.md](REFERENCES_AND_RULES.md)，当前交接状态见 [CURRENT_STATE.md](CURRENT_STATE.md)。


## E002 — 首次远端 CI 与 Windows 测试清理修复

功能提交 `44e6a318d9eed11e1e849b026c5ca306599c5523` 已发布到 [草稿 PR #2](https://github.com/Jvust2/Invest/pull/2)。[首次 push CI](https://github.com/Jvust2/Invest/actions/runs/35701489393) 的 Ubuntu / Python 3.11、3.12 均通过；两个 Windows 作业均在 `test_journal_reopens_and_database_rejects_rewrite` 的临时目录清理阶段发生 WinError 32。所有业务断言均通过，失败原因是测试直接创建的 SQLite 连接只退出事务上下文，未显式 close。

修复仅在 `tests/test_portfolio.py` 用 `contextlib.closing` 关闭该测试连接，保留原有两项数据库防改写断言。应用 `PaperLedger._connection()` 已有 `finally: db.close()`，应用逻辑不变。本地针对 portfolio 的 16 项测试再次通过。修复提交之后的四平台矩阵结果以 PR #2 的最新 head 检查为准；本记录生成时尚未拿到重跑结论。

E001 的源码 ZIP 保留为冻结检查点，不重写。其应用源码仍与当前版本一致，测试的上述关闭修复及本节记录可由 GitHub 后续提交恢复；参见 `governance/artifact_manifest.json` 的后续变更索引。
