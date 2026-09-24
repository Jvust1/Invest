# 决策记录

## D001 — 从数模研究流程派生人民币投资项目

用户确认将数模能力转入 Invest，并明确只有人民币。保留原数模仓库，Invest 独立发展。复用审计、来源、研究卡片、反方检查和简单基准的模式，独立实现证券执行规则；不直接迁入竞赛路由器或模型置信分。

## D002 — 先做标准库本地网页

Python 3.11+ 标准库后端与无构建步骤的 HTML/CSS/JS 前端，降低初次运行和维护依赖。默认本机访问使 Token、持仓和笔记不因启动服务而暴露。响应式网页不等于已完成 Android App 或联网部署。

## D003 — 明确范围的小型回测模型

首版主板、单股票、现金、仅做多、日频均线策略；买入持有作为同成本、同评价区间基准。已对标 Backtesting.py 和 Qlib 的公开 README/许可及官方 API；保留后续适配方向，目前不引入其运行依赖或拷贝源码。比较细节见 REFERENCES_AND_RULES.md。

## D004 — 数据不完整时阻断执行

CSV 可用于研究查看，但未知公司行动、停牌、每日限价、因子或不完整日历阻止执行。首个 Tushare 适配器只读取四类官方数据，没有足够证据宣称企业行动完整，因此诚实地限制为研究导入。真实 API 验证和企业行动接入是下一阶段事项。

## D005 — 固定费用情景与严格身份

手续费、最低佣金、卖出印花税、双边费率、滑点必须保存并经用户确认；不将常量情景标为真实历史税费重建。初始资金 100000 元只是模拟默认值，不是用户资产事实。

独立审查发现仅信任外部 dataset.id 会破坏结果溯源，已改为所有核心入口重算指纹；合法修改数据须生成新身份。下溢数值、分以下价格也在导入阶段拒绝。

## D006 — 远端 CI 通过只关闭软件矩阵门，不解锁收益或真实数据结论

2026-09-23 对草稿 PR #2 的实时检查确认：应用/测试 head `f40b0285b1c2bb249464f2ec354e9eb3bb6b18df` 的 GitHub Actions 在 Ubuntu/Windows × Python 3.11/3.12 四个矩阵作业全部成功，82 项单测与源码编译均通过。该结果把“远端 CI 未验证”从当前阻塞中移除，但不等价于真实 Tushare 权限/返回验收、Windows 桌面浏览器与 `start.bat` 人工体验、样本外收益或前向模拟验证。

因此后续普通推进顺序改为：在本地授权可用时完成真实供应商验证；并在解释任何策略收益前先定义并冻结样本外与 forward-paper 评价协议。PR #2 继续保持可审查、未合并状态，合并仍需要对该具体 PR 的明确授权。

## D007 — 在真实收益解释前冻结样本外与 Forward-Paper 方法 v1

2026-09-23 按长期成长路线的 G2 入口要求，将样本外与 forward-paper 评价方法先于任何真实收益读取冻结。协议 v1 明确 development / validation / frozen holdout / forward-paper 四阶段边界、搜索预算、三类成本情景要求、PIT/存活偏差与可交易性检查、首次观察语义和版本变更规则。

当前只冻结方法，没有绑定真实授权数据，也没有打开 holdout 或产生 forward-paper 结果。具体日期、数据身份、证券池和成本数值必须在首个 `evaluation_run`/binding 中于读取 holdout 之前登记；若看过结果后修改规则，必须创建新协议版本或新未见数据身份，不能把已见数据重新称为 unseen。

## D008 — 先实现 fail-closed 数据 binding 执行门，不伪造真实供应商验证

2026-09-23 当前自动执行环境没有可合法读取的本地 Tushare 授权凭据或授权真实数据快照。凭据不应进入聊天、GitHub 或共享 Drive，因此本轮不尝试伪造联网验收，也不把 mock/合成数据当成真实供应商证据。

为使下一次真正取得授权数据时能够在首次 holdout 观察**之前**冻结 provenance，本轮新增 `invest/evaluation.py` 与 `docs/EVALUATION_BINDING_FORMAT.md`。校验器要求授权状态、原始与规范化数据身份、代码 SHA、证券池/PIT 证据、候选参数哈希、development/validation/holdout 非重叠窗口、至少三组成本情景、基准以及七类市场数据边界全部显式记录；递归拒绝 token/secret/password/credential/API key 等字段。

未知或未覆盖的市场边界可以如实登记，但会使 `can_open_holdout=false`；已有 blocker 也会阻止打开 holdout。该门只证明 binding 结构与冻结语义合规，不能证明数据完整或策略有效。首个真实 binding 仍必须等合法授权数据实际可用后创建。

## D009 — 真实数据门禁按实时 Drive 证据保持阻断，先修复接力状态而不制造伪进展

2026-09-23 重新对账 Invest Drive 项目根目录后，只确认到既有冻结源码检查点 `Invest_v0.1.0_source_checkpoint_20260922.zip` 与 `05_Reference_Materials/`，没有发现新的已授权真实行情数据集、真实 evaluation binding 或可替代本地 Tushare 授权联调的 artifact。GitHub Draft PR #2 仍未合并。

因此真实供应商验证继续作为外部授权门禁：不上传、不索取、不回显 Token；不把 mock、合成数据、旧源码 ZIP 或 binding 格式校验当成真实供应商证据；也不为了让自动化“有进度”而打开 frozen holdout。当前可安全执行的治理修复是把机器状态保持对齐，并明确下一步仍是“授权真实数据 → `BOUND_UNOPENED` binding → gate 通过后才首次观察 holdout → append-only forward-paper”。

## D010 — 在首个真实 binding 前补齐冻结协议已有的“三个历史市场环境”机器门禁

2026-09-23 对照已冻结的 `EVALUATION_PROTOCOL_V1.md` 与长期路线图 G2 后发现：协议 v1 已明确要求首个真实评价 binding 在首次 holdout 观察前登记“至少 3 个需要覆盖或单独标注的历史市场环境”，但此前 `EVALUATION_BINDING_FORMAT.md` 与 `invest/evaluation.py` 没有对应机器字段。当前没有任何真实 binding、没有真实供应商数据、没有打开 frozen holdout，因此在第一次真实证据产生之前修复该实现缺口，不会迁移、覆盖或事后改写冻结结果。

本轮保持方法协议 v1 本身不变，只让 binding 实现与已经冻结的方法一致：新增必填 `historical_market_environments`，至少 3 项；名称不得重复，日期必须真实且落在 development 起点至 frozen_holdout 终点总边界内，完全相同日期区间不能用不同名称重复计数，并要求保存环境标注 evidence。

## D017 — Provider evidence 单位必须与当前 Tushare 适配器契约一致

2026-09-24 在恢复真实数据门禁后发现：provider evidence 已能严格检查核心接口、字段、样本范围和执行时间，但除 `currency=CNY` 外，`price_unit`、成交量输入/输出单位与时区此前只要求非空。这样一条“字段齐全、行数正常、但单位解释错误”的脱敏证据仍可能通过 provider-side readiness，和 `invest/data.py` 当前明确的 Tushare 手→股转换及 A 股日期语义不一致。

因此 v1 证据契约新增 fail-closed 单位门禁：`currency=CNY`、`price_unit=CNY/share`、`volume_input_unit=lot`、`volume_output_unit=share`、`timezone=Asia/Shanghai` 必须逐项严格匹配；`conversion_notes` 继续要求非空。未来若接入单位语义不同的供应商，应升级或扩展证据契约，而不是静默复用当前 v1。

代码 head `1a19ab04bcc5d26f6e825e1d76bd83e9c4621f73` 的 GitHub Actions run `36010703814` 已在 Ubuntu/Windows × Python 3.11/3.12 四个矩阵 job 全部通过完整测试与源码编译。完整测试集为 115，provider evidence 测试方法为 20。本变更没有 provider call、没有读取凭据、没有真实行情、没有创建真实 binding，也没有观察 frozen holdout。

## D018 — Verified market-data boundary 必须绑定稳定 supporting-evidence SHA-256

2026-09-24 继续审查 provider-side readiness 时发现：七类 market-data boundary 虽然必须逐项写 `verified / unknown / not_covered` 和文本证据摘要，但此前 `verified` 只依赖自由文本即可参与 readiness。这样无法机器区分“有稳定 supporting artifact 的已验证声明”和“只有文字断言的已验证声明”，与项目“数据有来源、缺失显式阻断”的 North Star 不一致。

因此 v1 evidence contract 新增 provenance commitment：每个 `status=verified` 的 boundary 必须同时提供 `evidence_sha256`，且必须是小写 64 位 SHA-256；授权原始 supporting artifact 可继续只留在本地。`unknown` / `not_covered` 可以不提供 hash，以便诚实保存未闭环状态；若提供 hash 则也必须合法。哈希只冻结证据身份，不证明 artifact 的内容真实性、许可充分性或 boundary 判断正确，因此真实 binding 与人工/独立证据审查仍不可绕过。

代码 head `5f1c3be266227d7403ef0ff10b61be4742471c5c` 的 GitHub Actions run `36013947202` 已在 Ubuntu/Windows × Python 3.11/3.12 四矩阵通过测试与源码编译。完整测试集为 116，provider evidence 测试方法为 21。本变更没有 provider call、没有读取凭据、没有真实行情、没有创建真实 binding，也没有观察 frozen holdout。

## D019 — Provider evidence 执行时间必须与 A 股市场时区保持同一日期语义

2026-09-24 继续做 credential-free 对抗检查时发现：`executed_at` 此前只要求“带时区”，而 `units.timezone` 又独立要求 `Asia/Shanghai`。`sample.end_date` 是直接与 `executed_at.date()` 比较；若允许 `Z`、`+09:00` 或其它任意 offset，同一个绝对瞬间可能落到不同日历日期，造成 evidence 中“样本是否晚于实际执行日期”的判定与 A 股市场日期语义错位。

因此 v1 evidence contract 把执行时间也绑定到当前市场时区语义：`executed_at` 必须使用 `Asia/Shanghai` 对应的 `+08:00` UTC offset。等价瞬间如以其它 offset 表示也需要先规范化为 `+08:00` 再写入证据；否则整条 evidence 结构校验失败。该要求不声称时区 offset 能证明供应商请求真实性，只是保证时间边界的机器比较使用单一、明确的市场日期基准。

代码 head `070ac1b536ad7b96a97b0b0b944453a6c6fbc919` 的 GitHub Actions run `36017899955` 已在 Ubuntu/Windows × Python 3.11/3.12 四矩阵通过测试与源码编译。完整测试集为 117，provider evidence 测试方法为 22；新增测试覆盖 `Z` 与 `+09:00` 两种错误 offset。本变更没有 provider call、没有读取凭据、没有真实行情、没有创建真实 binding，也没有观察 frozen holdout。
