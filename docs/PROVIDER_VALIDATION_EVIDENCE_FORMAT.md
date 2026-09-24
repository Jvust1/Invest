# 授权真实行情供应商验证证据格式 v1

状态：**FORMAT_READY / CREDENTIAL_FREE / NO_REAL_PROVIDER_RESULT IMPLIED**

本格式把 `REAL_DATA_PROVIDER_VALIDATION_RUNBOOK.md` 中的脱敏供应商验证记录变成机器可检查的 JSON 契约。它只规范“真实供应商调用完成后应怎样保存脱敏证据”，**不会发起供应商请求，不读取凭据，不证明真实数据完整，也不替代 `BOUND_UNOPENED` evaluation binding。**

实现：`invest/provider_validation.py::validate_provider_validation_evidence`。

## 顶层字段

记录必须包含：`schema_version=1`、`status=PROVIDER_VALIDATION_EVIDENCE`、带时区 `executed_at`、40 位 `code_sha`、`provider`、`sample`、`interfaces`、`dataset_identity`、`units`、七类 `market_data_boundaries`、`known_blockers`、`provider_call_performed`、`real_data_used`、`credentials_saved=false`、`holdout_observed=false`。可选 `evidence_id` 是去除自身后规范化 JSON 的 SHA-256；填写时必须与重算结果一致。

`executed_at` 不仅必须带时区，还必须使用当前 v1 市场时间契约 `Asia/Shanghai` 对应的 `+08:00` UTC offset。等价瞬间若以 `Z`、`+09:00` 或其它 offset 表示也会被拒绝；真实执行记录应在生成脱敏证据时规范化为 `+08:00`。这样 `sample.end_date <= executed_at.date()` 的日期边界始终按与 A 股证据契约一致的市场日历语义解释，避免同一瞬间因任意 offset 造成日期漂移。

## 供应商与授权

`provider` 必须且只能包含 `name`、`source_kind`、`license_status`、`evidence_summary`；`license_status` 必须严格为 `authorized`。真实供应商验证记录必须明确 `provider_call_performed=true`。mock、synthetic、旧 ZIP 或离线格式测试不能冒充真实供应商联调。

## 最小验证样本

`sample` 包含 `security_code`、`start_date`、`end_date`、`purpose`。`security_code` 必须通过当前 Invest v1 与 `invest/data.py` 共用的沪深主板代码格式门禁；科创板、创业板、ETF、境外或其它未纳入当前范围的代码不能作为本格式的有效首轮样本。日期必须存在且有序；首轮最小样本最长 366 个自然日。`sample.end_date` 还不得晚于证据自身以 `+08:00` 表示的 `executed_at` 所在日期，避免尚未发生的数据区间被写成已经完成的真实供应商验证证据。

## 接口尝试

`interfaces` 至少一项，每项包含 `name`、`status`、`fields`、`row_count`、`evidence`。`status` 只能为 `success` / `failed`；接口名和字段名不得重复，行数必须为非负整数。标记为 `success` 的接口必须同时具有至少一个非空字段名，并且 `row_count > 0`；空 schema 或 0 行结果不得作为成功证据进入 provider-side opening readiness。真实失败请求可以使用空字段与 0 行，但必须保留为 `failed`，不得替换成伪造成功；任一接口失败都会让 provider-side opening readiness 保持 fail-closed。

当前 Invest v1 的核心供应商调用边界固定为 `daily`、`adj_factor`、`stk_limit`、`trade_cal` 四项。真实记录可以保存部分执行结果或真实失败，但只有四项全部明确出现在 `interfaces` 中且均成功时，接口覆盖这一侧才允许参与 provider-side opening readiness；缺少任何一项都会返回 `required_core_interfaces_present=false` 和对应 `missing_core_interfaces`，保持 fail-closed。额外接口可以作为补充证据，但不能替代这四项核心接口。

此外，核心接口被标记为 `success` 时，`fields` 必须至少覆盖当前 `invest/data.py` 适配器实际要求的字段集合：`daily` 需要 `ts_code, trade_date, open, high, low, close, vol`；`adj_factor` 需要 `ts_code, trade_date, adj_factor`；`stk_limit` 需要 `ts_code, trade_date, up_limit, down_limit`；`trade_cal` 需要 `exchange, cal_date, is_open`。允许额外字段，但缺少任何适配器必需字段时整条证据结构校验失败，不能仅凭“接口名存在 + 非空字段 + 正行数”声称成功。真实失败接口仍可保留空或部分字段，并继续 fail closed。

## 数据身份与单位

`dataset_identity` 包含 `raw_artifact_identity`、`raw_sha256`、`normalized_dataset_id`。两个哈希均为小写 64 位 SHA-256。授权原始数据本体可以只留在本地；共享治理证据只保存不可恢复凭据的身份、哈希与脱敏摘要。

`units` 包含 `currency`、`price_unit`、`volume_input_unit`、`volume_output_unit`、`timezone`、`conversion_notes`。当前 v1 证据契约必须与现有 Tushare 适配器的实际单位语义严格一致：`currency=CNY`、`price_unit=CNY/share`、`volume_input_unit=lot`、`volume_output_unit=share`、`timezone=Asia/Shanghai`；`executed_at` 也必须使用与该 timezone 一致的 `+08:00` offset；`conversion_notes` 仍需非空说明。单位或执行时间 offset 不一致时整条证据结构校验失败，不能让“字段完整但语义或日期基准不一致”的记录支持 provider-side readiness。未来若引入单位/时区语义不同的供应商，应升级/扩展证据契约，而不是复用 v1 并静默改写单位。

## 七类 market-data boundary

`market_data_boundaries` 必须恰好包含：`calendar`、`suspension`、`corporate_actions`、`price_limits`、`risk_warning_history`、`survivorship_bias`、`pit_features`。每项必须包含 `status` 与 `evidence`，并可带 `evidence_sha256`；`status` 只能是 `verified` / `unknown` / `not_covered`。

当某项标记为 `verified` 时，`evidence_sha256` **必须**存在且为小写 64 位 SHA-256，用于把“已验证”声明绑定到一个稳定、可追溯的 supporting-evidence artifact/脱敏证据包身份。授权原始数据或事件级证据可以继续只保存在本地，但共享记录至少要冻结其 supporting evidence 的哈希，不能只用一段自由文本把 boundary 升级为 verified。`unknown` / `not_covered` 可不提供哈希；若提供，也必须是有效 SHA-256。

`unknown` / `not_covered` 可以诚实保存，但会使 `can_support_holdout_opening=false`。未知状态不得被静默填成安全的 false/0。`evidence_sha256` 只提供 provenance commitment，不证明 artifact 内容真实、许可充分或 boundary 判断正确；这些仍需独立审查和真实 binding 门禁。

## Blocker 与敏感信息

`known_blockers` 是去重文本数组；存在任何 blocker 时保持 fail-closed。校验器递归拒绝键名中疑似 token、secret、password、API key、cookie 等凭据字段。唯一允许的凭据相关 attestation 是 `credentials_saved=false`，其它值全部拒绝。

## 与 frozen holdout 的关系

只有 `real_data_used=true`、执行时间与市场时区语义一致、样本身份与时间范围通过上述门禁、四个当前核心接口全部存在且全部成功、每个成功核心接口覆盖当前适配器所需字段、成功接口具有正行数、七类 boundary 全部 `verified` 且每个 verified boundary 都绑定有效 supporting-evidence SHA-256、`known_blockers` 为空且 `holdout_observed=false` 时，校验器才返回 `can_support_holdout_opening=true`。

这个布尔值只说明**供应商证据这一侧**没有已知 opening blocker，绝不单独授权打开 frozen holdout。随后仍必须创建真实 `BOUND_UNOPENED` binding，并由 `invest/evaluation.py` 对授权、数据/代码身份、development/validation/holdout、至少三个历史市场环境、候选、成本、基准、PIT/证券池和市场边界再次 fail-closed 校验；其它项目 gate 也必须全部通过。
