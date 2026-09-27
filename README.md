# Invest · ChatGPT 云端投研工作台

**最终目标：你只需要说“我现在有 500 元，怎么投？”，ChatGPT + Invest 就给出金额级、可执行、可复盘的人民币投资方案。**

当前默认使用方式仍是直接在 ChatGPT 里调用 Invest。你可以直接说：
- “我现在有 500 元，怎么投？”
- “用 Invest 看 600000.SH 最近三个月。”
- “把 000001.SZ 最近一年做一份研究报告。”
- “换另一个公开数据源交叉核对。”
- “继续分析上次那个标的。”

ChatGPT 会在 Invest 的非 main 分支建立研究任务，GitHub Actions 云端执行，结果进入短期 artifact，再由 ChatGPT 读取、解释并按需归档 Drive。普通公开研究**不需要你本机 Python、CMD 或数据 Token**。

当前云端公开研究固定 AKShare 1.18.97。数据源必须显式声明；首次 Eastmoney 路径因远端断连失败并保留证据，第二个独立 Tencent 任务成功。详情见 [ChatGPT 云端模式](docs/CHATGPT_CLOUD_MODE.md)。

## 开源能力池

Invest 已建立机器可读的开源量化能力库，当前纳入 33 个 GitHub 项目，覆盖：
- 中国市场数据和行情；
- A 股/独立回测；
- 小资金组合优化和风险预算；
- 风险/绩效分析；
- 交易日历与技术指标；
- 因子、机器学习和自动研究；
- 金融新闻/情绪研究。

机器清单：`invest/upstream_registry.json`  
统一代码入口：`invest/upstreams.py`  
详细策略：[开源生态接入](docs/OPEN_SOURCE_ECOSYSTEM.md)

第三方源码默认不复制。许可证、数据权利、运行身份分别治理；GPL/AGPL/许可证未确认项目先作为研究参考。

## 已验证

- 云端运行代码：`f2ab93b6a23c57517d1348e4efe5dd8703386289`
- Windows/Linux × Python 3.11/3.12：每组 491 tests，全部通过（这是开源生态扩展前的最后验证基线）
- 首次成功任务：`600000.SH`，2026-08-01～2026-09-25
- 成功接口：AKShare `stock_zh_a_hist_tx`
- 实际得到 39 个交易日并生成 JSON、CSV 和中文 Markdown 报告
- Draft PR #9，未合并 main

## 下一步

围绕“500 元怎么投”优先做：
1. PyPortfolioOpt / Riskfolio-Lib / skfolio 组合适配；
2. 真实最小交易单位、手续费和离散金额分配；
3. 双交易日历校验；
4. QuantStats / Empyrical 风险指标交叉验证；
5. Hikyuu / Zipline / bt 独立历史验证；
6. Qlib / Alphalens 因子研究。

## 边界

云端公开模式统一标记 `PUBLIC_RESEARCH_ONLY`。它适合行情复盘、收益/回撤/波动/均线等描述性研究，但不是独立许可审阅后的执行级行情，不会自动进入正式成交合同、evaluation binding、frozen holdout、券商或下单链。

最终投资决定仍由用户做出。Invest 可以把研究结果转化成具体金额、候选标的、风险条件和后续动作，但不会把回测或模型输出包装成未来收益保证。

如果未来取得明确的数据权利和完整市场事实，原 ENG-04A/04B 正式证据链继续使用；本机采集工具不删除，但不再是普通 ChatGPT 投研的前置要求。

权威入口：[当前状态](docs/CURRENT_STATE.md)、[云端交付回执](governance/assistant_cloud_result.json)、[开源生态回执](governance/upstream_ecosystem_result.json)、[接续](docs/HANDOFF.md)。
