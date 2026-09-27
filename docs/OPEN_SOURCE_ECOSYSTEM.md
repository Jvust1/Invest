# Invest 开源生态接入

本文件定义 Invest 如何系统吸收 GitHub 开源量化生态，而不是把第三方仓库整包复制进本仓库。

目标服务于 Invest 的最终形态：

> 用户只需要告诉 ChatGPT“我现在有 500 元，怎么投？”，Invest 能综合真实可执行约束、公开研究数据、组合优化、风险评估、独立回测、因子研究和复盘证据，给出金额级决策支持。

机器可读清单：`invest/upstream_registry.json`。查询入口：`invest.upstreams`。

## 接入原则

1. Invest 自己的 `engine / portfolio / evaluation / provenance` 保持核心权威，不让单个第三方框架替代整个项目。
2. 外部项目通过“可选适配器、独立验证器、研究参考或数据源候选”接入。
3. 默认不复制第三方源码。MIT / Apache-2.0 / BSD-2-Clause / BSD-3-Clause 项目可进入直接适配候选；GPL / AGPL / GitHub 未能确认许可证的项目先保持参考层，除非以后单独完成许可证审查。
4. 软件许可证与底层金融数据权利是两回事。即使客户端是 MIT，也不能自动推导数据可用于回测、再分发或实盘。
5. 外部引擎首先用于“交叉验证 Invest 的结果”，而不是把单一引擎结果当成事实。
6. 对 500 元小资金，交易单位、手续费、流动性、停复牌、公司行动和现金余量优先于复杂模型。
7. RL / LLM / 情绪模型只能作为研究信号或实验支线，不能直接成为默认买卖决策器。

## 已纳入能力池（33 个项目）

### 中国市场数据与行情

- **akfamily/akshare** — 当前云端公开研究数据入口，继续作为现有主路径。
- **waditu/tushare** — 正式/权限型中国市场数据候选；必须把服务权限和软件许可分开核验。
- **shidenggui/easyquotation** — 免费行情源候选，用于公开报价交叉检查。
- **mootdx/mootdx** — 通达信数据读取候选，适合未来本地数据路径。
- **yutiansut/QUANTAXIS** — A 股数据、回测、模拟、多账户的一体化比较对象。
- **OpenBB-finance/OpenBB** — 数据聚合和 agent 化研究架构参考；许可证未确认前不直接拷贝源码。

### A 股 / 独立回测引擎

- **ricequant/rqalpha** — Invest 已有独立引擎路径，继续保留。
- **fasiondog/hikyuu** — 中国市场导向、高性能回测与策略分析，优先做独立结果交叉验证。
- **stefan-jansen/zipline-reloaded** — 事件驱动独立回测候选。
- **pmorissette/bt** — 组合级回测，适合资产配置策略。
- **QuantConnect/Lean** — 成熟的独立算法交易引擎，作为执行模型和组合模型参考。
- **wondertrader/wondertrader** — 国内高性能研发/交易架构参考。
- **vnpy/vnpy** — 事件引擎、风险管理和交易架构参考；当前 Invest 不默认连接券商。
- **polakowo/vectorbt** — 向量化参数研究很有价值，但许可证未确认前维持参考层。
- **mementum/backtrader** — GPL-3.0，只做行为/架构参考，不直接纳入源码。
- **kernc/backtesting.py** — AGPL-3.0，只做行为/架构参考，不直接纳入源码。

### 500 元组合配置与风险预算

- **PyPortfolio/PyPortfolioOpt** — 优先接入。用于有效前沿、Black-Litterman、HRP 等组合构建。
- **dcajasn/Riskfolio-Lib** — 优先接入。用于更多风险度量和风险预算组合。
- **skfolio/skfolio** — 优先接入。利用类似 scikit-learn 的组合模型选择和交叉验证。
- **pmorissette/bt** — 同时承担资产配置策略历史验证。
- **pmorissette/ffn** — 金融函数与组合绩效交叉计算。

500 元场景不能直接拿优化器的连续权重当交易方案。适配层必须在优化后增加：
- A 股/ETF 最小交易单位；
- 单笔佣金与最低佣金；
- 卖出税费等真实成本；
- 可买数量离散化；
- 剩余现金；
- 单一资产最低/最高仓位；
- “不值得交易”的成本阈值。

### 风险与绩效分析

- **ranaroussi/quantstats** — 收益、回撤和报告交叉验证。
- **stefan-jansen/empyrical-reloaded** — 风险/绩效指标独立实现。
- **stefan-jansen/pyfolio-reloaded** — 组合风险诊断与 tear sheet。
- **pmorissette/ffn** — 再提供一套独立金融指标实现。

同一关键指标至少允许由 Invest 自己实现 + 一个外部实现交叉验证，降低单一实现错误。

### 因子、机器学习与实验自动化

- **microsoft/qlib** — 高优先级。用于因子、监督学习、组合研究和未来模型交叉验证。
- **stefan-jansen/alphalens-reloaded** — 因子 IC、分组收益、衰减和有效性分析。
- **AI4Finance-Foundation/FinRL** — 强化学习实验参考，不作为默认资产配置器。
- **microsoft/RD-Agent** — 自动化研究/实验循环参考，可用于未来批量研究假设。

### 新闻、文本与情绪研究

- **AI4Finance-Foundation/FinGPT** — 金融 LLM / 新闻情绪研究参考。
- **ProsusAI/finBERT** — 金融情绪模型参考；用于中文/A 股前必须另做语言与领域有效性验证。

文本情绪永远不能跳过价格、基本面、交易成本和风险约束直接产生买卖动作。

### 交易日历与指标交叉验证

- **gerrymanoim/exchange_calendars** — 优先接入交易会话与日历交叉验证。
- **rsheftel/pandas_market_calendars** — 第二套日历实现，用于独立核对。
- **TA-Lib/ta-lib-python** — 技术指标独立实现，用于校验 Invest 特征/指标。
- **jealous/stockstats** — 指标 API 参考；许可证未确认前不直接集成源码。

## 500 元决策流水线

目标流水线如下：

```text
用户：我有 500 元
        ↓
ChatGPT 解析资金、期限、风险和明确约束
        ↓
AKShare / 其他显式 provider 获取公开研究数据
        ↓
交易日历 + 市场规则 + 最小交易单位 + 成本检查
        ↓
候选资产筛选（股票 / ETF / 现金等）
        ↓
PyPortfolioOpt / Riskfolio-Lib / skfolio 产生候选配置
        ↓
Invest 离散化为真实金额与数量
        ↓
RQAlpha / Hikyuu / Zipline / bt 做独立历史验证
        ↓
QuantStats / Empyrical / Pyfolio / ffn 做风险交叉检查
        ↓
Qlib / Alphalens 作为因子和模型证据支线
        ↓
输出：买什么、多少钱、分几次、剩余现金、风险条件、复盘条件
```

若成本、最小交易单位或风险条件不满足，合法输出必须允许为：
- 暂不交易；
- 只投入一部分；
- 改用可执行的 ETF / 现金方案；
- 等待资金积累后再执行。

## 集成优先级

### P0：直接服务 500 元配置

1. PyPortfolioOpt adapter
2. Riskfolio-Lib adapter
3. skfolio adapter
4. exchange_calendars + pandas_market_calendars 双日历校验
5. QuantStats + Empyrical 双风险指标校验
6. 离散化/最小交易单位/交易成本层

### P1：提高结论可信度

1. Hikyuu 独立 A 股回测
2. Zipline-reloaded 独立事件驱动回测
3. bt 组合回测
4. Alphalens 因子验证
5. TA-Lib 指标交叉验证

### P2：扩大研究面

1. Qlib 因子与 ML 工作流
2. QUANTAXIS 数据/回测比较
3. Tushare / mootdx / easyquotation provider adapter
4. FinGPT / FinBERT 文本信号
5. RD-Agent 自动研究循环
6. FinRL 实验性 RL

### Reference-only

- backtrader：GPL-3.0
- backtesting.py：AGPL-3.0
- vectorbt：当前 GitHub 元数据未确认许可证
- OpenBB：当前 GitHub 元数据未确认许可证
- stockstats：当前 GitHub 元数据未确认许可证

这些项目可以学习架构、行为和公开文档，但不直接复制代码进入 Invest。

## 验收要求

任何新 adapter 进入“可用于用户方案”前至少满足：

- 有明确上游仓库和版本/commit 身份；
- 软件许可证已记录；
- 数据权利另行记录；
- 输入输出转换有测试；
- 与 Invest 自有实现至少完成一个可重现交叉样例；
- 失败不静默 fallback；
- 不能绕过当前 frozen holdout / broker / execution-data 边界；
- 不能把单次回测或模型分数包装为未来收益保证；
- 对 500 元资金必须证明实际可交易，而不只是数学权重可行。

