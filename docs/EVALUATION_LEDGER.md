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

功能提交 `44e6a318d9eed11e1e849b026c5ca306599c5523` 已发布到草稿 PR #2。首次 push CI `35701489393` 的 Ubuntu / Python 3.11、3.12 均通过；两个 Windows 作业均在 `test_journal_reopens_and_database_rejects_rewrite` 的临时目录清理阶段发生 WinError 32。所有业务断言均通过，失败原因是测试直接创建的 SQLite 连接只退出事务上下文，未显式 close。

修复仅在 `tests/test_portfolio.py` 用 `contextlib.closing` 关闭该测试连接，保留原有两项数据库防改写断言。应用 `PaperLedger._connection()` 已有 `finally: db.close()`，应用逻辑不变。本地针对 portfolio 的 16 项测试再次通过。修复提交之后的四平台矩阵结果以 PR #2 的最新 head 检查为准；本记录生成时尚未拿到重跑结论。

E001 的源码 ZIP 保留为冻结检查点，不重写。其应用源码仍与当前版本一致，测试的上述关闭修复及本节记录可由 GitHub 后续提交恢复；参见 `governance/artifact_manifest.json` 的后续变更索引。

## E003 — PR #2 远端四平台矩阵复核通过（2026-09-23）

本轮重新从 GitHub 实时读取草稿 PR #2、功能分支和 Actions，不沿用聊天中的历史结论。PR #2 当前仍为 open/draft、base=`main`、head=`feat/a-share-research-v0.1-20260922`、未合并；本次复核对应应用/测试 head `f40b0285b1c2bb249464f2ec354e9eb3bb6b18df`。

GitHub Actions `Invest tests` run `35701856144` 状态为 `completed/success`。其 4 个矩阵 job 均成功：Windows / Python 3.11、Windows / Python 3.12、Ubuntu / Python 3.11、Ubuntu / Python 3.12。每个 job 都完成 `python -m unittest discover -s tests -v` 的 82 项测试，并完成 `python -m compileall -q invest`。

因此，“远端 CI 未验证”和“Windows CI 因 SQLite fixture 清理失败”均已关闭。该证据只说明当前代码在 GitHub-hosted Ubuntu/Windows Python 3.11/3.12 的单元测试与编译矩阵通过；它不等价于真实 Tushare 联调、Windows 桌面浏览器/`start.bat` 人工体验、真实市场收益、样本外结果或 forward-paper 表现。PR 合并状态也没有因 CI 成功改变。

本轮检查点记录在 `governance/checkpoints/20260923_ci_reconciliation.json`。下一验证主线转为真实供应商数据边界，以及在解释策略收益前冻结样本外与 forward-paper 协议。

## E004 — 样本外与 Forward-Paper 评价方法 v1 冻结（2026-09-23）

本轮没有使用真实 Tushare Token、真实行情收益或券商数据。由于真实供应商联调需要本地授权，而“先冻结评价协议”是可独立安全完成的下一未完成事项，本轮将 `docs/EVALUATION_PROTOCOL_V1.md` 与 `governance/evaluation_protocol_v1.json` 作为方法 v1 固定下来。

冻结状态为 `FROZEN_METHOD_V1`；首个授权真实数据绑定为 `PENDING_LICENSED_REAL_DATA`，frozen holdout 为 `NOT_OPENED`，forward-paper 为 `NOT_STARTED`。协议要求在首次读取 holdout 结果前登记数据身份、development / validation / holdout 时间边界、候选参数、成本情景、基准和首次观察状态；已经看过的数据不能因为调参或改规则重新称为 unseen。

这项记录只证明研究治理边界已建立，不证明策略有效。真实供应商权限/字段、停牌和公司行动覆盖、真实样本外表现以及后续 forward-paper 证据仍属于未验证项。机器检查点见 `governance/checkpoints/20260923_evaluation_protocol_freeze.json`。

## E005 — 预观察真实数据 Binding 校验器离线验收（2026-09-23）

目标：在没有真实供应商凭据的当前环境中，只完成**可独立验证的 credential-free 准备**，使未来首个授权数据集能够在 frozen holdout 首次观察前以机器可验证方式冻结 provenance。没有调用 Tushare、没有读取真实行情、没有创建真实 binding，也没有打开 holdout。

新增 `invest/evaluation.py` 与 `tests/test_evaluation.py`。定向执行 `python -m unittest discover -s tests -v`（仅本轮临时工作树中的新测试）共 **12 PASS**，另执行 `python -m compileall -q invest` 通过。覆盖至少包括：

- 合法 binding 的确定性 SHA-256 `binding_id` 与内容修改检测；
- development / validation / frozen_holdout 严格递进、不重叠；
- 至少三组唯一、非空成本情景；
- 授权状态、原始/规范化数据哈希与代码 SHA 格式；
- 递归拒绝 token / API key / secret / password / credential 类字段；
- `holdout_first_observed_at` 在预观察状态必须为 null；
- 未知/未覆盖市场数据边界显式阻断 `can_open_holdout`，而不是静默补安全值；
- 已知 blocker、NaN/Infinity、未知字段与 binding 事后变更均被拒绝或阻断。

随后将校验器与治理增量发布到代码 head `474959c7d789b12feecb4eb2ff9ae6c36044be95`，GitHub Actions run `35801154754` 已完成并成功。四个矩阵 job（Ubuntu/Windows × Python 3.11/3.12）的 `Standard-library tests` 与 `Compile source` 步骤全部通过。因此校验器从“仅本地定向通过”推进为“当前代码 head 远端 CI 验证通过”。

这仍不改变证据边界：真实 Tushare 权限、实际字段、停牌/公司行动覆盖、真实 OOS 与 forward-paper 全部未验证；CI 成功不能替代真实供应商证据或收益证据。

## E006 — 冻结协议历史市场环境要求与 Binding 门禁对齐（2026-09-23）

恢复最新治理后对照 `EVALUATION_PROTOCOL_V1.md` 第 4 节、长期路线图 G2 与当前 `EVALUATION_BINDING_FORMAT.md`/`invest/evaluation.py`，发现一个可自动验证的一致性缺口：冻结协议已经要求首个真实评价数据 binding 在首次 holdout 观察前登记**至少三个需要覆盖或单独标注的历史市场环境**，但此前 binding schema 和校验器没有对应字段，因此无法机器保证这项已冻结要求被执行。

当前 Drive 根目录仍未发现授权真实行情数据或真实 evaluation binding；frozen holdout 仍为 `NOT_OPENED`。因此本次修复发生在第一份真实 binding 之前，没有迁移或改写任何真实结果，也没有改变冻结方法 v1 的语义。

代码 head `7629e221619f22500dc2016f2bf698eb055f50f2` 新增必填 `historical_market_environments`：至少三项，名称唯一、日期真实、日期落在 development 起点至 frozen_holdout 终点总时间边界内、完全重复区间不能重复计数，并要求 evidence 文本。新增一个测试方法覆盖五类反例：不足三项、重复名称、越过总时间边界、起止日期反转、完全重复区间。

Credential-free 本地重建执行 `python -m unittest discover -s tests -q` 得到 **95 tests PASS**（基础 82 + evaluation 13），`python -m compileall -q invest` 通过。随后 GitHub Actions run `35809448144` 对该代码 head 完成 Ubuntu/Windows × Python 3.11/3.12 四个 job，所有 `Standard-library tests` 与 `Compile source` 步骤均为 success。

本次验证没有使用真实 Tushare Token、没有 provider call、没有真实市场数据、没有创建真实 binding、没有打开 holdout，也没有产生收益证据。该修复只关闭“冻结协议要求无法被 binding schema 执行”的治理/实现缺口；真实供应商边界与 `LICENSED_REAL_DATA_REQUIRED` 继续保持 OPEN。


## E007 — Provider evidence 单位契约 fail-closed 验收（2026-09-24）

目标：关闭真实 provider evidence 中“字段与行数看似合格，但价格/成交量/时区单位语义与当前 Tushare 适配器不一致仍可能通过”的结构性缺口。当前环境仍没有合法可用的真实供应商凭据或真实行情，因此本次只做 credential-free 契约加固，不产生任何真实市场或收益结论。

代码 head `1a19ab04bcc5d26f6e825e1d76bd83e9c4621f73` 新增严格单位契约：`currency=CNY`、`price_unit=CNY/share`、`volume_input_unit=lot`、`volume_output_unit=share`、`timezone=Asia/Shanghai`。测试新增一个方法、五个 subcase，分别证明货币、价格单位、输入成交量单位、输出成交量单位和时区任一不一致都会被拒绝；正确 fixture 保持通过。

GitHub Actions `Invest tests` run `36010703814` 已 completed/success。四个矩阵 job（Ubuntu/Windows × Python 3.11/3.12）的 `Standard-library tests` 与 `Compile source` 均成功。完整 discover 为 **115 tests PASS**，其中 evaluation 13、provider evidence 20。

证据边界不变：没有真实 provider call、没有 Token/凭据、没有真实数据、没有真实 provider evidence、没有真实 `BOUND_UNOPENED` binding、frozen holdout 仍未打开、forward-paper 仍未开始。该结果只证明当前 evidence contract 对单位语义继续 fail closed。

## E008 — Provider evidence 执行时区一致性门禁验收（2026-09-24）

目标：关闭 `executed_at` 虽然“带时区”但仍可使用任意 UTC offset 的日期语义缺口。当前 v1 evidence contract 已声明 `units.timezone=Asia/Shanghai`，而样本边界使用 `sample.end_date <= executed_at.date()`；若执行时间以 `Z`、`+09:00` 等其它 offset 表示，同一绝对瞬间可能映射到不同日历日期，从而使 provider evidence 的样本结束日期检查偏离 A 股市场日历语义。

代码 head `070ac1b536ad7b96a97b0b0b944453a6c6fbc919` 新增 fail-closed 约束：`executed_at.utcoffset()` 必须严格等于 `+08:00`。测试新增一个方法，覆盖 UTC/Z 和 `+09:00` 两个反例；原有 `+08:00` 正常 fixture 继续通过。

GitHub Actions `Invest tests` run `36017899955` 已 completed/success。四个矩阵 job（Ubuntu/Windows × Python 3.11/3.12）的 `Standard-library tests` 与 `Compile source` 均成功。完整测试集推进为 **117 tests**，其中 evaluation 13、provider evidence 22。

证据边界不变：本轮没有真实 provider call、没有 Token/凭据、没有真实数据、没有真实 provider evidence、没有真实 `BOUND_UNOPENED` binding、frozen holdout 仍未打开、forward-paper 仍未开始。该门禁只确保 evidence 的日期比较与声明的市场时区使用同一基准，不证明供应商真实性、数据完整性或策略有效性。


## E009 — Provider 授权 provenance 门禁验收（2026-09-25）

代码 head `6db24bb3cde003f937a73dc5a5eb2041181af505` 要求 `provider.license_status=authorized` 时必须同时提供小写 64 位 `license_evidence_sha256`，并新增缺失/格式错误反例。GitHub Actions run `36089180871` 已完成并成功，完整测试集为 **118 tests**，其中 provider evidence 23 个测试方法。

该哈希只冻结许可证据 provenance 身份，不独立证明授权真实性或适用范围。本轮没有真实 provider call、没有 Token、没有真实市场数据、没有真实 binding，也没有打开 frozen holdout。


## E010 — Provider evidence → evaluation binding provenance bridge 验收（2026-09-25）

目标：关闭 provider evidence 与首个真实 `BOUND_UNOPENED` evaluation binding 之间仍需人工对账的 provenance 缺口。此前 provider evidence 已分别冻结 license/data/code/boundary 证据身份，但 binding 可以独立填写自己的 dataset 与 boundary 文本；在首个真实 binding 尚未出现、frozen holdout 尚未打开时，适合先把两层门禁机器化连接。

代码 head `c6ada411910d0e904fbaf1fbcec0ef399a1a9ea7` 新增：binding 必须包含 provider `evidence_id`、`license_evidence_sha256`、`raw_sha256`、`normalized_dataset_id`、`code_sha`；其中 raw/normalized/code 必须与 binding dataset 同名身份完全一致。binding 的七类 market-data boundary 若标记 `verified`，还必须继续携带有效 supporting-evidence SHA-256。新增 2 个 evaluation 测试方法覆盖缺失/畸形 provider evidence ID、数据/代码身份不一致，以及 verified boundary 缺失/畸形证据 hash；`unknown` boundary 可诚实省略 hash，但继续阻断 opening。

GitHub Actions `Invest tests` run `36093418179` 已 completed/success；Ubuntu/Windows × Python 3.11/3.12 四个矩阵 job 的 `Standard-library tests` 与 `Compile source` 全部成功，日志确认 **Ran 120 tests**（基础 82 + evaluation 15 + provider evidence 23）。

本次只加固结构和 provenance：没有 provider call、没有 Token/凭据、没有真实市场数据、没有真实 provider evidence、没有真实 binding、没有观察 frozen holdout，也没有收益证据。哈希与 identity bridge 仍不是外部真实性证明。

## E011 — scikit-learn 滚动验证离线样本

2026-09-30：11 个新定向测试通过；与 PR #48 1b2d415b 的临时组合运行
569 unittest cases，13 个可选依赖 skips，0 failures/errors。真实 loopback HTTP
验证创建、保存、导出、幂等重试及错误锁恢复；未来价格扰动不能改变早先训练结果。
完整预算合成探针：2500 个预热后交易日、3 候选、5 折，60 次引擎调用，15 项
评价及独立回放全部通过；JSON 7,048,280 bytes。JS 语法通过；云浏览器 loopback
访问被阻止，视觉验收未执行。上述为本地证据，远端 exact-head CI 单独核验。
没有真实 provider call、私有持仓、真实交易、收益有效性或 frozen holdout 观察。

补充完整 pytest：575 passed / 13 skipped / 365 passing subtests，1 个既有 china_market_data 目录数量断言失败；已在未修改 PR #48 复现，不改弱断言。

## 2026-09-30 — 六个实际 SDK 共存与已安装 wheel 证据

完整候选源代码在 Linux/Python 3.12 下运行：863 passed、13 explicit optional skips、454 passing subtests、0 failures；8 个前端状态测试通过，pip check 无冲突。安装实际 Qlib0.9.7、MLflow3.16.1、Matplotlib3.10.8、DuckDB1.5.6、Optuna5.0.0、scikit-learn1.9.1。

源码目录外的 Python -I 从刚构建并独立安装的 wheel 导入全部生产代码，实际完成120行合成 Qlib 数据→持久化 DuckDB→12次 Optuna 搜索→84/36训练/后续评价；另完成9项滚动现金研究→保存→同一 MLflow run 复用→身份 PNG→备份恢复→相同 PNG 与新归档重建。原生价格未送入现金撮合，未打开 holdout。

独立审查覆盖原生回放身份桥、安装隔离、归档 UI 请求中断/重试/身份错配和 Python3.10 SQLite 兼容分支。Python3.10 实际运行、Windows/Linux 全组合以新候选 exact-head CI 为准；旧 Windows 归档超时保留为历史风险，诊断 profiler 不被当成已证实的修复。浏览器布局未验收。详见本轮 checkpoint 与融合说明。
