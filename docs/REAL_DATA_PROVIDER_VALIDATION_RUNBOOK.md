# 授权真实行情供应商验证执行手册 v1

状态：**RUNBOOK_READY / NO_REAL_DATA_USED / NO_PROVIDER_CALL_PERFORMED**

用途：在 Invest 首次创建真实 `BOUND_UNOPENED` evaluation binding 之前，规定本地授权环境中必须收集、核对和脱敏保存的供应商证据。本文是 credential-free 的准备材料，不代表已经完成 Tushare 联调、取得真实行情、验证收益或打开 frozen holdout。

## 1. 当前代码事实

当前 `invest/data.py` 的 Tushare 适配器只调用四类官方接口：

- `daily`
- `adj_factor`
- `stk_limit`
- `trade_cal`

适配器会把成交量从手转换为股，严格检查请求证券、日期区间、重复行、交易日历自然日覆盖和必要字段，并对补充接口失败显式登记 blocker。它故意把 `suspended` 与 `corporate_action` 保持未知；四接口本身不能证明完整停牌与公司行动历史，因此当前真实在线导入即使成功也只能先作为研究数据，不能自动解锁模拟成交或 frozen holdout。

## 2. 执行环境与凭据边界

真实供应商验证只允许在用户本地、已经合法授权的环境执行。

- Token 仅从本地受信环境变量读取，不进入 GitHub、聊天、共享 Drive、截图、日志或 evaluation binding。
- 禁止把 API 响应中的敏感账户信息或完整凭据作为证据上传。
- 自动化若无法访问本地授权环境，应保持 `LICENSED_REAL_DATA_REQUIRED=OPEN`，不得使用 mock、合成数据、旧 ZIP 或格式校验冒充真实联调。
- 任一网络/权限/额度失败都记录为失败证据，不生成替代数据。

## 3. 首轮最小验证样本

首轮验证的目标不是追求大数据量，而是证明供应商边界可以被可靠识别。

至少选择：

1. 一只当前适配器支持的沪深主板标准代码；
2. 一个不超过 366 个自然日的区间；
3. 区间内应包含足够的开市日与非开市日，以验证 `trade_cal` 的覆盖和缺行判断；
4. 若用于验证停牌、风险警示或公司行动，则必须另外选择有可核验事件的历史样本，不能从“没有观察到事件”推断覆盖完整。

每次样本必须冻结：证券代码、请求区间、获取时间、代码 SHA、供应商来源、原始响应/导出身份、原始 SHA-256 与规范化数据身份。

## 4. 七类 market-data boundary 的证据要求

### `calendar`

可标记 `verified` 的最低要求：

- `trade_cal` 返回的交易所与证券所属交易所一致；
- 覆盖请求区间每一个自然日，日期唯一；
- `is_open` 只接受明确的 0/1；
- 规范化开市日严格递增；
- `daily` 缺少某个开市日时保持 `missing_session`，不得自动解释为停牌。

否则保持 `unknown` 或 `not_covered`。

### `suspension`

当前四接口适配器**不能**把缺失 `daily` 行等价为停牌。

只有存在独立、PIT 可追溯的停牌/复牌来源，并能与 `daily` 和交易日历逐日对账时，才允许标记 `verified`。没有这类证据时必须保持 `unknown`。

### `corporate_actions`

`adj_factor` 变化只能证明复权因子发生变化，不能独立重建现金分红、送转、配股等完整经济事件。

只有额外的、授权且可追溯的公司行动来源覆盖目标区间，并能够与价格/复权口径对账时，才允许标记 `verified`。否则保持 `unknown` 或 `not_covered`，继续阻断需要真实成交语义的评价。

### `price_limits`

当前 `stk_limit` 可提供逐日涨跌停价，但仍需验证：

- 证券/日期完全匹配；
- 必要日期无静默缺失；
- 价格单位与当前 CNY/元口径一致；
- 不把固定 ±10% 等经验规则替代逐日供应商数据。

缺少逐日证据时保持 `unknown`。

### `risk_warning_history`

必须使用带历史有效期的风险警示/名称状态证据，能够回答“当日是否已经处于相关状态”。只知道当前 ST/*ST 状态不能证明历史 PIT。

没有历史证据时保持 `unknown`。

### `survivorship_bias`

需要记录证券池形成规则，以及是否包含当时可见但后来退市、暂停上市、改名或不再交易的证券。仅用当前仍存续证券列表不能标记 `verified`。

若本轮只验证单证券数据接口，可明确标记该边界尚未覆盖，而不是伪装成全市场无存活偏差。

### `pit_features`

任何财务、公告、风险状态、证券身份或其它特征都必须保存其“当时可见时间”证据。无法证明发布时间/生效时间的字段不得进入历史决策。

当前只使用价格与交易规则字段时，也要明确说明哪些特征根本未启用；未覆盖的 PIT 能力保持 `not_covered`。

## 5. 供应商验证输出

一次真实验证完成后，至少生成一份**脱敏**记录，包含：

- `executed_at`
- `code_sha`
- 证券与请求区间
- `daily`、`adj_factor`、`stk_limit`、`trade_cal` 四个当前核心接口的实际尝试结果，以及任何额外接口记录
- 每个接口实际返回字段集合及行数
- 数据单位与转换说明
- 原始数据身份/哈希引用（原始授权数据本体可只留在本地）
- 规范化数据身份
- 七类 boundary 的 `verified / unknown / not_covered`
- 每项 boundary 的证据摘要
- 明确 blockers
- 是否存在 provider call、是否使用真实数据
- 明确声明凭据未被保存

不要在脱敏记录中保存 Token、Cookie、密码、账户凭据或可恢复这些凭据的内容。四个核心接口中任一缺失或失败都可以如实保存，但 provider-side opening readiness 必须继续 fail closed，不能把“没有记录”解释为成功。

## 6. Fail-closed 判定

真实供应商请求成功 ≠ 数据完整 ≠ 可以打开 holdout。

只有以下条件同时满足，才进入“可以创建/完善真实 binding”的下一步：

1. 数据许可明确 `authorized`；
2. 原始与规范化数据身份被冻结；
3. `daily`、`adj_factor`、`stk_limit`、`trade_cal` 四个当前核心接口均存在真实尝试记录且全部成功；
4. 所有 evaluation binding 所需市场边界均有真实证据；
5. 任何不能验证的边界如实写为 `unknown` / `not_covered`；
6. 没有未处理的已知 blocker；
7. 尚未读取 frozen holdout 结果。

随后创建 `BOUND_UNOPENED` binding，并由 `invest/evaluation.py` 校验。只有 `can_open_holdout=true` 且项目其它 gate 也全部通过，才允许首次观察 holdout。

## 7. 当前状态

截至 2026-09-24，本手册仍只完成 credential-free 准备：

- `provider_call_performed=false`
- `credential_used=false`
- `real_data_used=false`
- `real_binding_created=false`
- `frozen_holdout=NOT_OPENED`
- `forward_paper=NOT_STARTED`

因此本手册本身不产生任何真实市场或收益结论。
