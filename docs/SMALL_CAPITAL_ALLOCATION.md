# 500 元配置可行性原型

`invest.allocation.size_allocation(request)` 是独立的人民币情景计算函数。它不获取行情、不连接券商、不输出订单，也不把公开数据提升为正式执行行情。调用方必须明确提供日期、报价与来源、交易单位与规则来源、流动性上限、买入佣金/最低佣金/过户费率、卖出税率、目标权重和至少保留的现金。缺项、未来日期、重复资产、非法数字会拒绝。

输入示例（数值和来源仅是单元测试情景，不代表实际 ETF 价格、规则或券商费率）：

```json
{
  "cash_cny": "500.00",
  "reserve_cny": "100.00",
  "as_of": "2026-09-28",
  "data_scope": "PUBLIC_RESEARCH_ONLY",
  "max_entry_fee_fraction": "0.05",
  "candidates": [{
    "symbol": "DEMO.ETF", "target_weight": "1", "price_cny": "1.90",
    "quote_date": "2026-09-25", "quote_source": "explicit test quote",
    "rule_date": "2026-09-25", "rule_source": "explicit test rule",
    "buy_lot_shares": 100, "max_buy_shares": 300,
    "commission_rate": "0.0003", "min_commission_cny": "5.00",
    "transfer_fee_rate": "0", "sell_tax_rate": "0"
  }]
}
```

用 `python -c 'import json,sys; from invest.allocation import size_allocation; print(json.dumps(size_allocation(json.load(sys.stdin)), ensure_ascii=False, indent=2))' < scenario.json` 复现。示例计算 200 股，报价金额 380.00 元、买入费用 5.00 元、投入现金 385.00 元，剩余 115.00 元。这里的 100 股、费率和流动性只是明确输入的测试假设，不是通行市场规则。

算法按目标名义金额的平方偏差逐手选择增量，每一步重新检查总现金、最低佣金、费用比例和输入的流动性上限。它是确定性的启发式计算，**不保证组合全局最优**；固定最低佣金等约束可能使某些整体可行解被遗漏。最多 10000 步，超出则拒绝。结果含输入 SHA256、每个候选的数量与费用、保留现金、来源及拒绝原因，状态恒为 `SCENARIO_ONLY`。

税费输入中卖出税率只记录为完整输入门槛，当前函数仅计算买入现金。未模拟未来卖出、盘口成交、停牌、公司行动、有效期变更，也没有连接 PyPortfolioOpt / Riskfolio-Lib / skfolio 优化器。后续适配器应给出候选权重，由本层在明确市场事实下离散化，并接受独立日历、风险计算和实际规则校验；这些门槛完成前不应输出真实交易指令。
