# ENG-04A：本机原始数据与证据核验 v0.1

## 本轮交付范围

这是可选的、纯离线的源码工具，不是新 Windows EXE。它读取用户本机已经获得的四份 Tushare JSON 响应，核对原始字节、字段转换、已存在的 Invest 数据集、许可声明范围和市场事实声明。工具不会访问数据供应商、读取 Token、连接券商、打开留出集，也不会把旧工作台的未知执行字段改成 false。

**真实数据尚未取得，真实许可尚未确认。** 随包的全部行情、许可正文和市场事实附件都是人工测试材料。测试通过只证明已覆盖的代码行为；本轮不是 ENG-04 真实市场验收完成。

基线为 PR #6 / `31bdb8cce253c243c8ffb0860a81e14c859bf6d3`。原 ENG-03、RQAlpha worker、rc2 EXE 不替换。先前的原生执行证据属于原始提交，不算作本工具的实时行情联调证据。

## 1. 先看演示

在项目根目录执行：

```sh
python tools/market_evidence.py fixture --output demo-input --complete
python tools/market_evidence.py audit --input demo-input --output demo-report --as-of 2024-01-10T12:00:00+08:00
```

打开 `demo-report/index.html`。`--complete` 仅补齐**假的、明确标注 SYNTHETIC 的测试附件**，不是提供授权。重放时间也是调用者声明，不是可信时间戳。所有输出目录必须不存在，旧目录不能被覆盖；输出不能放进输入目录。写入中断会留下 `.incomplete`，这种输入会被拒绝。

批量查看22个预定义反例：

```sh
python tools/market_evidence_suite.py --output demo-suite
```

打开 `demo-suite/reports/index.html`。正确识别错误、拒绝不支持输入也是预期行为，不能把22个测试通过理解成22份合格真实数据。

## 2. 使用已获得的真实导出（只在有权使用的本机环境）

先依现有 `REAL_DATA_PROVIDER_VALIDATION_RUNBOOK.md` 确认供应商账号、数据使用范围及许可，不把开源软件许可当作金融数据授权。通过供应商允许的方式取得下面四个响应体，保存为 UTF-8 JSON；不要保存含凭据的请求体、请求头或浏览器会话：

- `daily.json`：必需 ts_code、trade_date、open、high、low、close、vol。
- `adj_factor.json`：必需 ts_code、trade_date、adj_factor。
- `stk_limit.json`：必需 ts_code、trade_date、up_limit、down_limit。
- `trade_cal.json`：必需 exchange、cal_date、is_open；不能只导出开市日。

每份响应使用供应商 `code/msg/data.fields/data.items` 的表格结构。本工具还识别可选 `has_more`：只有严格 false 才允许继续；没有该字段不代表供应商做了完整性证明。通过完整自然日日历、请求区间和逐日关联进一步发现缺行。

```sh
python tools/market_evidence.py assemble --input raw-exports --output intake-bundle --symbol 600000.SH --start-date 2024-01-02 --end-date 2024-01-08 --captured-at 2024-01-09T12:00:00+08:00
python tools/market_evidence.py audit --input intake-bundle --output intake-review
```

上面代码、日期只是命令形状示例，不是股票建议，也不表示真实请求发生。必须替换成自己真实导出的请求区间与获取时刻。`assemble` 保留原始响应字节，并计算哈希；`origin=provider_export` 只是用户声明，不是来源真实性认证。它不会替用户填写“已授权”。不支持的代码、重复字段、重复行、含已识别凭据字段的文件、越界路径、符号链接和超限文件会拒绝。普通无标记文本中的秘密不能被保证自动识别，因此原始正文从不复制进报告，仍需人工检查隐私。

## 3. bundle.json 数据合同

完整可运行范例由 `fixture` 生成。顶层字段必须恰好是：

| 字段 | 约束 |
|---|---|
| schema / provider | `invest-raw-intake-v1` / `tushare` |
| origin | `provider_export` 或 `synthetic_fixture`，不得当作真实性证明 |
| symbol | 当前支持的单只沪深主板标准代码 |
| start_date / end_date | ISO日期、最多366个自然日 |
| captured_at | 带时区ISO时间，转换为+08:00核对；不能晚于核验时点 |
| raw | 四个接口，各含相对 path 和实际原始文件 sha256 |
| license_review | 缺失为 null；否则为下述完整声明 |
| market_facts | 缺失为 null；否则为市场事实JSON的 path/sha256 |
| normalized_candidate | 缺失为 null；否则为待核对 Invest 数据集JSON的 path/sha256 |

文件路径只能在输入目录内。单个文件2MiB、已引用附件合计16MiB；清单另限2MiB。响应最多10,000行；单证券请求区间和重复日校验会进一步收紧。额外供应商字段只登记名称，不进入当前转换，也不代表其语义已经验证。原始文件哈希区分换行、BOM及空白变化；规范化值比较与原始字节身份是两回事。

## 4. 数值与逐行核对

价格按现有核心合同使用人民币元、精确到分，复权因子单独处理。`vol` 以 Decimal 乘100换成整数股数，不能四舍五入成“差不多正确”。会逐一检查证券、日期、OHLC、成交量、复权因子、涨跌停价和交易所。原始精度无法由现有核心数值表示保留时，返回 `CORE_NUMERIC_REPRESENTATION_LOSS`，不悄悄丢精度。

每行保存原始文件哈希、接口、`data.items` 的0起始索引、字段名、转换规则和规范化CSV行号。代码使用独立的原始表关联逻辑，不通过网络重跑旧适配器。测试另用人工表对照既有 Tushare 适配器输出，属于模拟的适配一致性测试，不是实际供应商调用。

可选 `normalized_candidate` 首先验证自身数据指纹，再按行比较值、开市日历、单位和未知标记。即使改价后重新计算了候选指纹，也会被原始响应对照发现。旧指纹不涵盖 audit 提示，因此还检查无依据的 `backtest_ready=true`。匹配只针对数据合同与上述提示，不验证自由文本来源，也不采用候选审计结果来放行执行。

开市日没有 daily 记录，不推定停牌，不补价；复权因子变化不被转换成完整公司行动。规范化数据的 `suspended`、`corporate_action` 始终为 null，即使另附事实声明也不会自动修改。原始限价/日历是供应商声明，不等于交易所事实。

当前日线导出若在样本最后一天16:00（+08:00）之前完成，会标记 `CAPTURE_BEFORE_DECLARED_EOD_CUTOFF`。这是按官方入库时间说明设置的保守研究检查，不保证16:00之后一定完整；每日最终可用状态仍须独立核验。日线全日成交量不能作为当日开盘已知流动性。

## 5. 许可与市场事实必须分开

许可声明要求 `artifact`（path/sha256）、provider、symbol、data_start/data_end、valid_from/valid_until、permitted_uses、decision、reviewed_at。decision 可为 declared_authorized/unknown/denied。程序只检查附件确实存在且哈希一致，以及声明是否覆盖供应商、证券、数据区间、获取时刻、核验日期与 local_research 用途。范围吻合状态是 **DECLARED_SCOPE_MATCH**，不是“法律授权已核实”。本程序从不授予再分发权，不解释许可条款的法律效力。

`market_facts` JSON使用 `invest-market-facts-v1`，绑定 symbol/start_date/end_date，包含：

- evidence：每条记录含附件path/sha256、无凭据参数的HTTPS来源URL、published_at、retrieved_at。只有引用与时间顺序被检查，正文事实不由程序认证。
- calendar：请求区间每个自然日的 date/is_open/evidence_id，与供应商日历逐日对照。
- sessions：每个开市日的 date/suspended/corporate_action/risk_warning/evidence_id。布尔未知必须是null；不允许用数字0代替。检查漏日、停牌却有成交量、非停牌但无行情及不支持的公司行动。
- rules：effective_from/effective_to/tick_size/buy_lot/evidence_id。检查生效区间遗漏或重叠、最小价格单位以及当前核心尚不支持的规则。

事实公开时间按**显式研究假设：每个相关日期09:00 +08:00**比较。不是声称交易所09:00开盘。晚于该时点的信息会标记不可用于该时点决策，不能把后来的公告当时已知。该版本没有完成存活偏差或财务特征PIT验证，明确标为 NOT_VERIFIED；不能靠勾选布尔值使它们变成完成。

## 6. 输出、退出码及下游边界

`report.json` 是核验记录；`normalized.json`、`prices.csv`、`calendar.csv` 是重建结果；`index.html` 是离线中文报告。原始响应、许可正文和事实附件不复制到输出；输出本身仍可能包含有使用限制的规范化行情，分享前须检查。`SHA256SUMS.json` 覆盖所有其他成品文件，不作递归自哈希；`RUN_CONTEXT.json` 保存核验时刻。

状态分三层：原始字节/数值转换、许可声明、市场事实声明。`RAW_MAPPING_CHECKED` 不代表附属证据齐全。CLI退出0只代表转换检查通过，2代表输入拒绝或存在数据阻塞；程序从不以退出0授予交易权限。人工样本的 review_state 固定为 SYNTHETIC_FIXTURE_ONLY。真实导出即使声明完整也仅是 AWAITING_INDEPENDENT_REVIEW。

**此模块不生成旧 provider_validation 所接受的“真实供应商验证成功”凭据，不创建 evaluation binding，不改写 opening gate。** 真实获取、授权和独立审阅完成后，应使用既有供应商验证手册收集真实接口尝试记录，再做受版本控制的下游适配。当前只是 ENG-04A 工具实现与合成反例验收。

## 7. 官方接口与使用边界参考

以下页面在本轮公开查阅；它们说明字段与使用条款，不构成用户自己的数据许可证明。无市场数据从这些页面提取到测试集。

- Tushare HTTP结构： https://tushare.pro/document/1?doc_id=130
- daily原始价格、手单位及入库说明： https://tushare.pro/document/2?doc_id=27
- trade_cal交易所/自然日字段： https://tushare.pro/document/2?doc_id=26
- 复权因子： https://tushare.pro/document/2?doc_id=28
- 每日限价： https://tushare.pro/document/2?doc_id=183
- 用户协议： https://tushare.pro/document/1?doc_id=409
- 数据服务协议： https://tushare.pro/document/1?doc_id=405
- AKShare研究用途说明（只用于说明软件许可不等于数据授权，不是本模块支持的输入格式）： https://akshare.akfamily.xyz/introduction.html

## 8. 接续

优先取得用户有权使用的真实四接口响应及适用许可材料，再用本工具做原始/规范化对应关系检查。之后补独立的交易所日历、停复牌、公司行动和历史规则证据。任何缺失如实保留；不得把真实数据改标为synthetic_fixture来制造测试或验证成功。
