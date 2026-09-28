# 日收益风险与绩效指标交叉核验

`invest.risk_metrics.compare_risk_metrics(history, as_of="YYYY-MM-DD")` 对同一份明确传入的非累计日简单收益分别调用 QuantStats 和 Empyrical Reloaded。安装可选依赖：`python -m pip install '.[risk-metrics]'`。模块不会抓取行情、挑选策略或给出交易指令。

输入必须仅含 `data_scope: PUBLIC_RESEARCH_ONLY`、非空 `source` 和 30 至 5000 条严格递增的 `daily_returns`。每行仅有 `date` 和 `return`，日期不晚于 `as_of`；收益可为数字或数值字符串，须有限且在 `(-1, 10]` 内。例如：

```python
history = {"data_scope": "PUBLIC_RESEARCH_ONLY", "source": "已声明的研究来源",
           "daily_returns": [{"date": "2025-01-02", "return": "0.01"}, ...]}
result = compare_risk_metrics(history, as_of="2025-04-01")
```

输出保留规范化输入 SHA-256、来源、起止日期、样本数、两个包的版本和各自原值。核验三项指标：年化波动率、最大回撤（负值）、零无风险利率的年化 Sharpe。年化固定 252 期，波动率采用样本标准差 (`ddof=1`)；三项绝对差阈值均为 `1e-8`。逐项为 `AGREE`、`DISAGREE` 或 `UNDEFINED`；常数收益流的 Sharpe 为 `UNDEFINED`，整体为 `PARTIAL_UNDEFINED`，不把它误记为一致。上游缺失、输出非有限或不完整会失败，不会静默替代结果。

这是输入样本内的公式/实现核验。两库一致不验证来源授权、收益列的完整性、实际可交易性或样本外表现。若要核验 500 元方案，应先按费用、整手、现金和交易日契约得到研究组合的逐日净值，再将有来源与截止日期的日简单收益传入；此接口不会从单个资产收益擅自推断组合绩效。

参考： [QuantStats](https://github.com/ranaroussi/quantstats)，[Empyrical Reloaded](https://github.com/stefan-jansen/empyrical-reloaded)。
