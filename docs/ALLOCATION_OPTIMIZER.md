# 可选组合优化器：最小方差候选权重

`invest.allocation_optimizer.min_variance_scenario(history, sizing_request)` 接收共同日期的各观测日简单收益、来源和 `PUBLIC_RESEARCH_ONLY` 标记，使用可选的 PyPortfolioOpt 最小方差模型产生候选权重，再交给 `invest.allocation.size_allocation` 检查人民币资金、整手、费用、流动性上限和剩余现金。安装：`python -m pip install '.[optimization]'`。

`history` 格式：

```json
{
  "data_scope": "PUBLIC_RESEARCH_ONLY",
  "source": "explicit research dataset identity or source description",
  "daily_returns": [
    {"date": "2026-08-03", "returns": {"DEMO_A": "0.01", "DEMO_B": "-0.01"}}
  ]
}
```

实际调用至少需要 30 个严格递增的共同观测日，每行资产集合必须与配置候选完全一致；历史不能晚于方案日期或候选报价日期。`sizing_request` 与 [离散配置格式](SMALL_CAPITAL_ALLOCATION.md) 相同，只是各候选的 `target_weight` 会由优化器结果明确覆盖。输出包含后端版本、目标、历史输入 SHA256、历史截止日、原始权重和归一化权重、以及完整配置结果。

失败时不自动换优化器或使用等权配置。当前只实现 PyPortfolioOpt；Riskfolio-Lib 与 skfolio 尚未接入。最小方差只拟合输入区间内的协方差，不进行资产选择、收益预测、样本外/前向验证，也不能证明输入数据可用于交易。数值输入和费用/规则仍须单独核实。正式市场事实、双日历与独立风险计算尚待后续工作。

上游接口依据：[PyPortfolioOpt EfficientFrontier 文档](https://pyportfolioopt.readthedocs.io/en/latest/MeanVariance.html)。仓库的可选 CI 工作流在 Ubuntu/Python 3.11 安装锁定版本并运行真实求解器合同测试；主测试矩阵仍无需安装第三方优化器。
