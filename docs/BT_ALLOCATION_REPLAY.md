# bt 固定配置账务与净值交叉核验

本增量调用真实 `bt==1.2.3`，使用初始 500 元等明确资金输入，将离散配置层生成的整股数量一次买入并持有。逐日比较 Invest 自有金额账与 bt 的现金、数量、估值和当日费用，绝对金额差阈值为 `0.000001` 元；持仓数量要求完全一致。输出两个实现的原值及每天的差异，不选择一个实现覆盖另一个。

这是独立引擎的**固定配置账务回放**。输入的首次买入数量仍由 Invest 决定；没有验证选股、信号、交易所成交规则或样本外策略收益。Hikyuu/Zipline 事件驱动与真实市场验证仍待完成。

## 输入与运行

安装 `python -m pip install '.[backtest-bt]'`，调用：

```python
from invest.bt_replay import compare_allocation_replay
result = compare_allocation_replay(history, sizing_request, as_of="2025-01-06")
```

`sizing_request` 复用 `invest.allocation.size_allocation` 的完整请求契约。`history` 必须仅含以下字段：

- `data_scope`: `PUBLIC_RESEARCH_ONLY`。
- `source`: 非空来源说明。
- `price_basis`: `UNADJUSTED_NO_CORPORATE_ACTIONS`，明确声明该情景使用无公司行动的原始价格。这是调用者声明，模块不把它升级成已验证事实。
- `daily_prices`: 2 至 5000 条严格递增观测，每条为 `{"date": "YYYY-MM-DD", "prices_cny": {"资产代码": "正数价格"}}`。价格须精确到分，每天覆盖全部候选资产。

配置日期、全部报价日期和首个观测日期必须相同，首日价格必须与报价一致。不得把较晚生成的配置回填至更早历史。所有观测不得晚于研究截止日；没有隐式补齐、前向填充或下载行情。

结果保存配置输入哈希、规范化历史哈希、来源、bt 版本、完整曲线与逐日比较。缺库、非有限输出、缺列或日期不匹配都会失败，不退回自有账本伪装为交叉验证成功。

## 费用与边界

每个资产只提交一次完整数量；bt 的 `fn(quantity, price)` 费用回调独立按输入佣金率、最低佣金和过户费率计算，各项四舍五入到分。不同资产在提交其唯一交易前设置各自费用函数。后续不再提交订单，因此该方式不适用于未来的频繁调仓接口。

bt 自动增加的初始化日期不计为价格观测。零数量资产不交易、不收最低佣金；价格太高的情景可全持现金。期末按最后价格估值，不强制卖出、不预扣卖出税费；不模拟分红、拆股、利息、现金流、停复牌、涨跌停、T+1 或排队成交。输入日期的交易所完整性须另走日历与行情契约。

## 独立路径选择与后续

| 路径 | 本次证据/状态 | 下一步 |
| --- | --- | --- |
| bt | 固定数量、整数持仓、费用回调与逐日净值实际运行；专用 CI 为 Ubuntu + Python 3.11 | 绑定合法历史数据与交易事实后扩展事件/成交模型；再连接风险指标 |
| Hikyuu | 已查官方入门，需配置数据导入；本次未运行，也未验证其平台兼容性 | 建立隔离的合成数据初始化与交易规则样例，固定版本后验证环境 |
| Zipline Reloaded | 已查官方 bundle 契约，需资产元数据、价格、调整数据和日历；本次未运行 | 注册独立研究 bundle，明确中国交易日历及成交/费用约束后验证 |

## 验证

基础测试覆盖 500 元的手算现金/费用/净值、逐项分歧、输入缺失、日期穿越和无回退失败。专门工作流安装固定 bt，实际测试单资产最低佣金与分项取分、全现金、双资产不同费率三个情景。样例均为合成价格，不能作为真实收益证据。

上游参考（2026-09-28 查阅）：[bt API](https://pmorissette.github.io/bt/docs/source/overview.html)、[bt 1.2.3](https://pypi.org/project/bt/1.2.3/)、[Hikyuu 入门](https://hikyuu.readthedocs.io/zh-cn/latest/quickstart.html)、[Zipline 数据 bundle](https://zipline.ml4trading.io/bundles.html)。bt 的 MIT 软件许可不证明输入行情的数据权利。
