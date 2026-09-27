# ChatGPT ↔ Invest 云端任务入口

这里不是用户手工操作目录，而是给 ChatGPT/GitHub connector 使用的云端控制面。

## 工作方式

1. 用户在 ChatGPT 里说“分析 600000.SH 最近三个月”之类的任务。
2. ChatGPT 读取 Invest 最新治理状态。
3. ChatGPT 在非 main 的工作分支新增一个唯一的 `assistant_jobs/requests/<job-id>.json`。
4. GitHub Actions 自动运行 `.github/workflows/assistant-cloud-research.yml`。
5. Actions 通过固定版本 AKShare 获取公开研究数据，运行 Invest 的标的格式约束与描述性分析。
6. 结果只进入 Actions artifact；ChatGPT 下载 artifact、核对来源/状态并向用户解释，必要时再按去重规则归档 Drive。

用户无需本地 Python、无需运行 CMD、无需向聊天提供 Token。

## v1 请求

```json
{
  "schema": "invest-assistant-job-v1",
  "job_id": "20260927-600000-public-research",
  "operation": "public_stock_research",
  "symbol": "600000.SH",
  "start_date": "2026-08-01",
  "end_date": "2026-09-25"
}
```

当前只接受 Invest 原有沪深主板代码合同，区间最多 366 个自然日。

## 证据边界

本入口是 **PUBLIC_RESEARCH_ONLY**：

- 不把 AKShare/公开网页数据标成已独立核实许可的执行数据；
- 不创建 evaluation binding；
- 不打开 frozen holdout；
- 不连接券商或下单；
- 不自动生成买卖推荐；
- 不将 provider 的成交量单位静默改成 Invest 的执行股数；
- 缺少停复牌、公司行动、历史规则等事实时，不送入正式成交回测。

AKShare 代码许可与其采集的数据权利是两件事。当前 v1 固定使用 AKShare 1.18.97，并在每次 artifact 中记录实际包版本与依赖快照。

失败也会保留 artifact；ChatGPT 应读取 failure.json，而不是自动换源伪装成功。
