# Invest · ChatGPT 云端投研工作台

**默认使用方式：直接在 ChatGPT 里调用 Invest。**

你可以直接说：
- “用 Invest 看 600000.SH 最近三个月。”
- “把 000001.SZ 最近一年做一份研究报告。”
- “换另一个公开数据源交叉核对。”
- “继续分析上次那个标的。”

ChatGPT 会在 Invest 的非 main 分支建立唯一任务，GitHub Actions 云端执行，结果进入短期 artifact，再由 ChatGPT 读取、解释并按需归档 Drive。普通公开研究**不需要你本机 Python、CMD 或数据 Token**。

当前云端公开研究固定 AKShare 1.18.97。数据源必须显式声明；首次 Eastmoney 路径因远端断连失败并保留证据，第二个独立 Tencent 任务成功。详情见 [ChatGPT 云端模式](docs/CHATGPT_CLOUD_MODE.md)。

## 已验证

- 云端运行代码：`f2ab93b6a23c57517d1348e4efe5dd8703386289`
- Windows/Linux × Python 3.11/3.12：每组 491 tests，全部通过
- 首次成功任务：`600000.SH`，2026-08-01～2026-09-25
- 成功接口：AKShare `stock_zh_a_hist_tx`
- 实际得到 39 个交易日并生成 JSON、CSV 和中文 Markdown 报告
- Draft PR #9，未合并 main

## 边界

云端公开模式统一标记 `PUBLIC_RESEARCH_ONLY`。它适合行情复盘、收益/回撤/波动/均线等描述性研究，但不是独立许可审阅后的执行级行情，不会自动进入正式成交合同、evaluation binding、frozen holdout、券商或下单链，也不会自动给出买卖结论。

如果未来取得明确的数据权利和完整市场事实，原 ENG-04A/04B 正式证据链继续使用；本机采集工具不删除，但不再是普通 ChatGPT 投研的前置要求。

权威入口：[当前状态](docs/CURRENT_STATE.md)、[云端交付回执](governance/assistant_cloud_result.json)、[接续](docs/HANDOFF.md)。
