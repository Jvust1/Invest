# ChatGPT ↔ Invest 云端任务入口

这里是给 ChatGPT/GitHub connector 使用的云端控制面，不要求用户本机运行 Python。

## 工作方式

1. 用户在 ChatGPT 里说“分析 600000.SH 最近三个月”。
2. ChatGPT 读取 Invest 最新治理状态并选择一个**明确命名**的公开研究数据源。
3. ChatGPT 在非 main 分支新增唯一 `assistant_jobs/requests/<job-id>.json`。
4. GitHub Actions 自动运行云端研究。
5. 结果进入短期 Actions artifact；ChatGPT 读取后解释，并按需去重归档 Drive。

## v1 请求

```json
{
  "schema": "invest-assistant-job-v1",
  "job_id": "20260927-600000-public-research",
  "operation": "public_stock_research",
  "symbol": "600000.SH",
  "start_date": "2026-08-01",
  "end_date": "2026-09-25",
  "provider": "akshare_tencent"
}
```

允许的数据源：
- `akshare_tencent` → AKShare `stock_zh_a_hist_tx`
- `akshare_eastmoney` → AKShare `stock_zh_a_hist`

**不会在一次 job 中自动换源。** 若一个源失败，ChatGPT 可以创建新的、显式标识另一数据源的 job；两个运行分别保留 provenance。

旧的不带 `provider` 请求为了可复现性继续解释为 `akshare_eastmoney`。

## 证据边界

所有结果均为 **PUBLIC_RESEARCH_ONLY**。不创建 evaluation binding、不打开 frozen holdout、不连接券商、不下单、不自动生成买卖推荐，也不把公开接口的许可/完整性当成执行级市场证据。

当前固定 AKShare 1.18.97。代码包许可与底层网页数据权利是两件事。失败同样保留 artifact。
