# 合成演示 CSV

本目录 **没有真实证券行情**。`SYNTHETIC_DEMO_prices.csv` 包含 2 个格式合法的示例代码、每个 140 个合成开市日的虚构 OHLC、成交量、执行价格边界和公司行动字段。代码仅用于演示格式，不代表这些证券的真实表现。`SYNTHETIC_DEMO_calendar.csv` 是连续工作日历，**没有扣除中国节假日，不能用于真实行情**。

体验功能时，优先在界面点击“加载演示数据”，这样所有模块都带合成演示标签。CSV 文件用于检查导入格式；导入时来源必须明确填写“合成演示：虚构价格和日历”，不能声明成真实数据。两份文件必须配套使用。程序内 `demo_dataset()` 生成同样的确定性数据，不使用网络或随机行情。

## 自备数据格式

必填列为 `symbol,date,open,high,low,close,volume_shares`。单位分别为标准沪深主板股票代码、`YYYY-MM-DD`、人民币未复权价格、整数股数。股票代码必须保留前导零，如 `000001.SZ`；不支持 ETF、创业板、科创板、北交所或港美股。前缀校验只限定代码格式，不证明代码真实存在或当时已上市。

完整执行还需要 `suspended,up_limit,down_limit,adj_factor,corporate_action`。布尔字段只接受 `true/false`，不能填 `0/1`；空值保留未知并阻断回测。涨跌停价必须来自对应日期与证券的可靠来源，不能机械套用固定比例。复权因子应为正且区间内不变；公司行动为 `true` 或未知均不可执行。停牌日需显式保留一行、零成交量和有效 OHLC，不允许缺行后自动填充。

日历只含开市日期，每行一日，可带 `date` 表头；必须严格递增且不重复。行情可按代码分组，每个代码日期严格递增；导入后统一按日期、代码排序。日历应来自可靠且与行情日期覆盖一致的交易所日历，不能用工作日代替。

CSV 导入保留来源声明和 SHA-256 内容指纹，但不会独立证明提供者身份、日历完整性、未复权性质或没有公司行动。系统拒绝缺列、额外未知列、重复表头、长短行、非有限数、错误日期、重复行情、无效 OHLC 等结构错误；日历漏行、执行字段未知和未支持公司行动会作为可检查的阻断项保留。

## 官方在线数据边界

`fetch_tushare()` 仅向 `https://api.tushare.pro` 发起官方 HTTPS POST。服务端读取 `TUSHARE_TOKEN`，浏览器不接受或返回 token，下载与日志不包含凭据。单次只支持一只股票、最多 366 个自然日，不发起全市场抓取，不使用非官方网页抓取，不自动购买权限。

调用 `daily`、`adj_factor`、`stk_limit`、`trade_cal`，将 `vol` 的手数乘以 100 精确转换为股数。`daily` 不提供停牌日行情，因此缺行不能自动视为停牌。第一版四端点没有完整核验停复牌与公司行动，两个字段保留未知；取得的真实行情可用于研究，**不能直接执行回测或模拟成交**。缺少权限或补充字段时保留明确阻断，关键行情失败则直接报错，不回退到虚构数据。

真实 token、权限与在线返回尚未验证。当前测试使用 mock；官方字段参考：

- [日线行情与成交量单位](https://tushare.pro/document/2?doc_id=27)
- [交易日历](https://tushare.pro/document/2?doc_id=26)
- [复权因子](https://tushare.pro/document/2?doc_id=28)
- [涨跌停价格](https://tushare.pro/document/2?doc_id=183)

## Optional seeded Optuna research bundle

Run `python examples/optimized_research_bundle.py` after installing `.[optuna]`.
This uses only deterministic synthetic data and the real upstream optimizer;
parameter search sees an earlier prefix, while the reported backtest covers a
separate later suffix. Full trial evidence and split/metric scope are included.
See `docs/upstream/optuna-walkforward-2026-09-30.md` for the research boundaries.
