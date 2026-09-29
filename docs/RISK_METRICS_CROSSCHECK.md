# 日收益风险与绩效指标交叉核验

`invest.risk_metrics.compare_risk_metrics(history, as_of="YYYY-MM-DD")` 对同一份明确传入的非累计日简单收益分别调用 QuantStats 0.0.86 和 Empyrical Reloaded 0.5.12。安装可选依赖：`python -m pip install '.[risk-metrics]'`。模块不会抓取行情、挑选策略或给出交易指令。

输入必须仅含 `data_scope: PUBLIC_RESEARCH_ONLY`、非空 `source` 和 30 至 5000 条严格递增的 `daily_returns`。每行仅有 `date` 和 `return`，日期不晚于 `as_of`；收益可为数字或数值字符串，须有限且在 `(-1, 10]` 内。

```python
history = {"data_scope": "PUBLIC_RESEARCH_ONLY", "source": "已声明的研究来源",
           "daily_returns": [{"date": "2025-01-02", "return": "0.01"}, ...]}
result = compare_risk_metrics(history, as_of="2025-04-01")
```

## 标准六项报告

同一收益流同时计算并保留两套上游实现的原值：

1. `cumulative_return`：累计复利收益；
2. `annualized_return`：按 252 期年化的复利收益；
3. `annual_volatility`：年化波动率；
4. `max_drawdown`：最大回撤（负值）；
5. `sharpe_zero_rf`：零无风险利率的年化 Sharpe；
6. `sortino_zero_target`：零目标收益的年化 Sortino。

年化固定为 252 期，波动率采用样本标准差 (`ddof=1`)；累计/年化收益按复利口径。逐项绝对差阈值为 `1e-8`，状态为 `AGREE`、`DISAGREE` 或 `UNDEFINED`。常数收益流的 Sharpe 未定义；没有任何负收益观测时，零目标 Sortino 未定义。未定义项不会被强行填成 0。上游缺失、字段不完整或应定义指标返回非有限值时直接失败，不会静默替代。

输出继续保留规范化输入 SHA-256、来源、起止日期、样本数、两个包的版本、逐项差异和整体状态。`DISAGREE` 只表示两个实现超出约定容差，不会自动选择某个库作为权威。

## 与 500 元固定配置回放的连接

`invest.replay_risk.compare_allocation_risk_report(...)` 负责把已经通过 Invest / bt 账务一致性检查的逐日净值转换为本接口需要的日简单收益。首个观测日以**扣除入场费用后的净值相对初始资金**计算，因此买入费用不会在收益序列中消失；之后按相邻净值计算。

这是输入样本内的公式/实现核验。两库一致不验证来源授权、收益列完整性、实际可交易性或样本外表现，也不代表未来收益。

上游参考：QuantStats、Empyrical Reloaded。软件许可与行情数据权利仍分别处理。
