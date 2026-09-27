# Invest 接续：ChatGPT 云端研究模式

先读 AGENTS、project_state、assistant_cloud_result、CURRENT_STATE、artifact_manifest、pending_sync，并核实 live PR/CI。当前仓库 `Jvust/Invest`，开发分支 `feat/chatgpt-cloud-research-20260927` / Draft PR #9，基于 PR #8。

## 默认操作

当用户说“用 Invest 分析某只股票”时，优先使用 ChatGPT 云端公开研究模式，不要求用户本地运行采集器：

1. 验证请求属于当前支持证券和日期范围；
2. 明确选择 provider；
3. 在 `assistant_jobs/requests/` 创建唯一 JSON；
4. 等待 `Invest assistant cloud research` workflow；
5. 获取 artifact，核对 `result.json` 或 `failure.json`；
6. 由 ChatGPT 解释结果；需要长期保存时按 Drive 去重规则归档。

当前已验证 provider：`akshare_tencent`。Eastmoney 首次云端尝试失败证据保留。换源必须创建新 job，不静默 fallback。

运行代码 `f2ab93b6a23c57517d1348e4efe5dd8703386289`；四矩阵测试 run `36315941217` 每组 491 tests 全绿。成功 smoke request commit `e093baa3265bae4d00239932c47def79be2a55b1` / run `36316010850`。

Drive 云端模式证据包：`Invest-ChatGPT-Cloud-Research-v0.1-20260927.zip`，ID `1kumrq8YMaRZWbaf12HpWdCOo4F9itvjh`，SHA256 `66a4a45b570a29bd95afa1bca35751d2d088b59a44b9483a441476a325b3d0ca`，已回读验证。

## 不要混淆

公开云端研究不等于正式授权行情。不得据此创建正式 evaluation binding、打开 holdout、连接券商或下单。ENG-04A/04B 的本地/许可证据工具仍保留，但仅在未来需要正式 execution-data 证据时使用；不要再把它当普通用户使用 Invest 的前置步骤。

原 rc2、RQAlpha、成交合同和历史成果保持不变；main 与所有 PR 未自动合并。
