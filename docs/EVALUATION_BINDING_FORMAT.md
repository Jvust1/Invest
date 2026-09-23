# 真实数据评价 Binding 格式 v1

状态：**FORMAT_READY / NO_REAL_BINDING_CREATED**

本文件定义 `invest/evaluation.py` 校验的首个真实数据评价 binding 格式。它服务于已冻结的 `invest-oos-forward-paper-v1` 方法协议，不代表已经取得真实 Tushare 数据、打开 frozen holdout 或产生任何收益证据。

## 1. 使用时机

只有在合法授权的真实数据已经实际可用后，才创建真实 binding。顺序必须是：

1. 取得并核验授权数据，不把 Token、密码、Cookie 或其他凭据写入仓库、binding 或共享 artifact。
2. 在首次读取 frozen holdout 结果之前，冻结数据身份、代码身份、证券池形成规则、候选参数、时间窗口、成本情景、基准和市场数据边界。
3. 调用 `validate_evaluation_binding()` 校验并计算 `binding_id`。
4. 只有返回 `can_open_holdout=true` 且其它项目级 gate 也通过，才有资格进入首次 holdout 观察；校验器本身不会读取行情、运行回测或打开 holdout。

## 2. 顶层字段

真实 binding 必须是 JSON 对象，包含：

- `schema_version`: 固定为 `1`。
- `protocol_id`: 固定为 `invest-oos-forward-paper-v1`。
- `status`: 新 binding 固定为 `BOUND_UNOPENED`。
- `created_at`: 带时区 ISO-8601 时间。
- `dataset`: 授权、来源、原始快照与规范化数据身份。
- `universe`: 证券池描述、形成规则和 PIT 证据。
- `candidate`: 冻结候选身份与参数哈希。
- `windows`: development / validation / frozen_holdout 三个严格递进且不重叠的日期区间。
- `cost_scenarios`: 至少三个名称唯一、配置非空的成本情景。
- `benchmark`: 冻结的比较基准。
- `market_data_boundaries`: 关键数据边界的显式验证状态。
- `known_blockers`: 其它已知阻塞；有内容时不能打开 holdout。
- `holdout_first_observed_at`: 预观察 binding 必须为 `null`。
- `binding_id`: 可选；若提供，必须等于去掉本字段后规范 JSON 的 SHA-256。

## 3. dataset

必填字段：

- `source`: 数据来源说明。
- `source_kind`: 数据来源类型。
- `license_status`: 必须明确为 `authorized`，未知许可不能进入正式 binding。
- `retrieved_at`: 带时区获取时间。
- `raw_artifact_identity`: 原始文件、快照或其它不可含糊的来源身份。
- `raw_sha256`: 原始输入 SHA-256。
- `normalized_dataset_id`: 规范化数据 SHA-256 身份。
- `code_sha`: 产生/校验该数据身份的 40 位 Git commit SHA。
- `currency`: 当前 v1 必须为 `CNY`。
- `price_basis`, `volume_unit`, `timezone`: 明确口径与单位。

凭据字段会被递归拒绝。真实 Tushare Token 继续只存在于受信本地环境变量，不进入 binding。

## 4. 市场数据边界

以下七项必须全部出现：

`calendar`、`suspension`、`corporate_actions`、`price_limits`、`risk_warning_history`、`survivorship_bias`、`pit_features`。

每项包含：

- `status`: `verified` / `unknown` / `not_covered`；
- `evidence`: 对应证据或为何仍未知的说明。

`unknown` 与 `not_covered` 是合法、诚实的记录状态，但会使 `can_open_holdout=false`。校验器不会把未知静默变成安全值。

## 5. 不变式

- Development、Validation、Frozen Holdout 严格按时间向前且互不重叠。
- 至少三组成本情景，名称唯一，配置不可为空。
- 预观察 binding 不能写入首次 holdout 观察时间，也不能伪装成 `OBSERVED`。
- `binding_id` 对内容敏感；带 ID 的 binding 被修改后将校验失败。
- NaN、Infinity、非 JSON 类型、未知顶层字段和疑似凭据字段都会被拒绝。
- 校验通过只说明 provenance/binding 结构合规。真实数据本身是否完整、策略是否有效、收益是否可重复，仍必须由真实供应商验证、冻结样本外评价和后续 forward-paper 证据回答。

## 6. 当前状态

截至 2026-09-23，仅完成格式、离线校验器和针对危险边界的单元测试；**没有创建真实 binding，没有使用真实 Token，没有打开 holdout，也没有产生真实收益证据**。
