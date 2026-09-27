# Invest：5 本书与开源参考项目

书目查证：2026-09-22 至 2026-09-26；GitHub 元数据复核：2026-09-26（UTC，北京时间 9 月 27 日）。

已核对PR #4及其治理：G1–G5离线工程能力已有候选交付；真实数据许可、独立引擎、未见留出与前向观察仍需证据。先将资料用于补证和审查，不重复从零搭工作台。

成长次序见[长期路线图](LONG_TERM_ROADMAP.md)。本清单包含 **5 本书、12 项 GitHub 参考**；按项目能力与使用范围扩大来选择，不按月份排课。

本次现状依据：[开发 PR #4](https://github.com/Jvust/Invest/pull/4)、[读取时的固定版本](https://github.com/Jvust/Invest/tree/8d1700155d7f487804f6c51e16067799e504cbe5)。这些是开发分支证据，不代表已经合并或完成用户设备验收。

## 先从哪里开始

先读两本的相关章节：[Investments](https://www.mheducation.com/highered/product/investments-bodie.html)；[Python for Data Analysis](https://wesmckinney.com/book/)。

先看三个仓库：[pandas-dev/pandas](https://github.com/pandas-dev/pandas)、[unionai-oss/pandera](https://github.com/unionai-oss/pandera)、[akfamily/akshare](https://github.com/akfamily/akshare)。

第一项可评审产物：一页指标词典与三组手算收益/风险对账样例。

| 成长环节 | 用户价值 |
|---|---|
| G1 可信研究样本 | 看懂数据质量与基本收益计算 |
| G2 可验证的假设实验室 | 公平比较不同研究假设 |
| G3 可持续模拟组合 | 跟踪假设在后续可见信息中的表现 |
| G4 个人投研工作台 | 独立完成数据检查、比较、解释与复盘 |
| G5 需求驱动的研究扩展 | 解决当前工具无法覆盖的新问题 |

P0＝当前先学；P1＝能力深化时参考；P2＝需求成立后再评估。推荐指向学习或候选比较，没有承诺安装全部依赖。

## 五本书：用途与最小产物

### 1. Investments

- 作者：Zvi Bodie / Alex Kane / Alan J. Marcus / Nicholas Racculia。
- 版本：2026 Release（官方 Evergreen 版本；不与页面另列第13版混为一版）；语言：英文；本轮未核验对应中译本。
- [出版社／作者入口](https://www.mheducation.com/highered/product/investments-bodie.html)。官方目录/试读；全文通过正规购买或图书馆借阅。
- 对应成长：G1–G3。
- 解决的问题：补齐风险、收益、基准、分散化与组合绩效概念；将教材案例与人民币/A股规则分开。
- 最小应用产物：一页指标词典与三组手算收益/风险对账样例。

### 2. Python for Data Analysis

- 作者：Wes McKinney。
- 版本：第 3 版，2022；作者开放版持续修勘；语言：英文；本次未核验中译本。
- [出版社／作者入口](https://wesmckinney.com/book/)。作者官网合法免费 HTML 全书；正文保留版权，开放阅读不等于可复制进课程包；另有纸书/电子书购买入口
- 对应成长：G1：可信数据与账本。
- 解决的问题：检查时间、缺失值、证券身份和连接规则，防止数据清洗悄悄引入未来信息。
- 最小应用产物：对一个合法离线样本生成字段合同、异常表与重复运行报告。

### 3. Forecasting: Principles and Practice

- 作者：Rob J Hyndman / George Athanasopoulos。
- 版本：第3版，2021；官方在线版持续修订；语言：英文；本轮未核验对应中译本。
- [出版社／作者入口](https://otexts.com/fpp3/)。作者/OTexts官方免费在线全书。
- 对应成长：G2：时间外验证。
- 解决的问题：学习简单基准、滚动验证和预测区间；书中采用R，迁移的是评测方法，无需为读书重写Python核心。
- 最小应用产物：包含时间边界、基准、误差指标和失败结论的评测协议。

### 4. Quantitative Trading

- 作者：Ernest P. Chan。
- 版本：第2版，2021；语言：英文；本轮未核验对应中译本。
- [出版社／作者入口](https://www.oreilly.com/library/view/quantitative-trading-2nd/9781119800064/)。官方目录/试读；全文通过正规购买或图书馆借阅。
- 对应成长：G2–G3：回测与模拟。
- 解决的问题：选读历史数据库、回测陷阱、费用和模拟偏离分析；市场制度与书中策略均不能直接照搬。
- 最小应用产物：一份前视偏差、幸存者偏差、成本和不可成交场景检查表。

### 5. Advances in Financial Machine Learning

- 作者：Marcos López de Prado。
- 版本：2018；语言：英文；本轮未核验对应中译本。
- [出版社／作者入口](https://www.oreilly.com/library/view/advances-in-financial/9781119482086/)。官方目录/试读；全文通过正规购买或图书馆借阅。
- 对应成长：G2验证方法；复杂模型仅在G5按需引入。
- 解决的问题：重点关注标签重叠、金融交叉验证和回测过拟合；先证明现有简单模型与数据质量。
- 最小应用产物：合成重叠标签案例及隔离评测设计，明确哪些结果已被观察。

## GitHub 参考总览

许可摘要是本轮筛选依据；最近推送不等于稳定发行、可靠性或本项目兼容性。仓库代码的许可与模型权重、数据、字体、图片及角色素材的许可分别核对。

| 优先级 | 官方仓库 | 成长环节 | 许可摘要 | 已归档 | 最近推送（UTC） |
|---|---|---|---|---|---|
| P0 | [pandas-dev/pandas](https://github.com/pandas-dev/pandas) | G1 | BSD-3-Clause | 否 | 2026-09-26T16:28:46Z |
| P0 | [unionai-oss/pandera](https://github.com/unionai-oss/pandera) | G1 | MIT | 否 | 2026-09-26T16:31:24Z |
| P0 | [akfamily/akshare](https://github.com/akfamily/akshare) | G1–G2 | MIT | 否 | 2026-09-23T04:16:34Z |
| P1 | [statsmodels/statsmodels](https://github.com/statsmodels/statsmodels) | G2 | BSD-3-Clause | 否 | 2026-09-26T10:34:51Z |
| P1 | [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | G2 | BSD-3-Clause | 否 | 2026-09-24T17:11:32Z |
| P2 | [mementum/backtrader](https://github.com/mementum/backtrader) | G2 | GPL-3.0 | 否 | 2024-08-19T17:47:36Z |
| P1 | [kernc/backtesting.py](https://github.com/kernc/backtesting.py) | G2 | AGPL-3.0 | 否 | 2026-08-05T12:39:16Z |
| P2 | [microsoft/qlib](https://github.com/microsoft/qlib) | G2–G5 | MIT | 否 | 2026-09-22T05:57:23Z |
| P1 | [PyPortfolio/PyPortfolioOpt](https://github.com/PyPortfolio/PyPortfolioOpt) | G3 | MIT | 否 | 2026-07-07T21:18:14Z |
| P1 | [ranaroussi/quantstats](https://github.com/ranaroussi/quantstats) | G3–G4 | Apache-2.0 | 否 | 2026-09-26T08:58:39Z |
| P2 | [duckdb/duckdb](https://github.com/duckdb/duckdb) | G4–G5 | MIT | 否 | 2026-09-25T19:09:44Z |
| P2 | [vnpy/vnpy](https://github.com/vnpy/vnpy) | G4–G5 | MIT | 否 | 2026-09-13T06:36:50Z |

## 各仓库具体怎么用

### 1. pandas-dev/pandas · P0

- 使用方式：候选组件；接入前评估；适用阶段：G1。
- 本项目用途：读取与审计表格数据、时间索引、收益和现金流。
- 最小产物：确定性数据合同和异常清单。
- 适用限制：自动填充和连接不是业务事实；时间可见性、复权口径、人民币币种须独立核验。
- 查证：[官方仓库](https://github.com/pandas-dev/pandas) · [许可依据](https://api.github.com/repos/pandas-dev/pandas) · [维护元数据](https://api.github.com/repos/pandas-dev/pandas)。

### 2. unionai-oss/pandera · P0

- 使用方式：候选组件；接入前评估；适用阶段：G1。
- 本项目用途：定义列、类型、取值范围和跨字段的数据质量约束。
- 最小产物：20类异常样本的审计规则表。
- 适用限制：结构通过不证明行情真实、许可有效或不存在未来信息。
- 查证：[官方仓库](https://github.com/unionai-oss/pandera) · [许可依据](https://api.github.com/repos/unionai-oss/pandera) · [维护元数据](https://api.github.com/repos/unionai-oss/pandera)。

### 3. akfamily/akshare · P0

- 使用方式：候选组件；接入前评估；适用阶段：G1–G2。
- 本项目用途：研究国内数据适配器、字段差异和更新失败的处理。
- 最小产物：单一来源的许可/字段/时点适配卡。
- 适用限制：MIT是代码许可；数据提供方条款、可见时点、再分发权限与接口稳定性另查。先用授权样本，接口获取不代表交易授权。
- 查证：[官方仓库](https://github.com/akfamily/akshare) · [许可依据](https://api.github.com/repos/akfamily/akshare) · [维护元数据](https://api.github.com/repos/akfamily/akshare)。

### 4. statsmodels/statsmodels · P1

- 使用方式：候选组件；接入前评估；适用阶段：G2。
- 本项目用途：建立可解释统计与时间序列基准，检查残差及假设。
- 适用限制：统计显著性不等于可交易收益；应与简单基准用同一成本和样本比较。
- 查证：[官方仓库](https://github.com/statsmodels/statsmodels) · [许可依据](https://api.github.com/repos/statsmodels/statsmodels) · [维护元数据](https://api.github.com/repos/statsmodels/statsmodels)。

### 5. scikit-learn/scikit-learn · P1

- 使用方式：候选组件；接入前评估；适用阶段：G2。
- 本项目用途：流水线、预处理隔离、简单模型与时间切分。
- 适用限制：TimeSeriesSplit不会自动解决公告时点、标签重叠和证券池偏差。
- 查证：[官方仓库](https://github.com/scikit-learn/scikit-learn) · [许可依据](https://api.github.com/repos/scikit-learn/scikit-learn) · [维护元数据](https://api.github.com/repos/scikit-learn/scikit-learn)。

### 6. mementum/backtrader · P2

- 使用方式：历史设计参考；不作为默认新引擎；适用阶段：G2。
- 本项目用途：比较事件驱动的策略、经纪模拟与分析器分层。
- 适用限制：最近推送为2024年，保留设计对照价值；GPL许可及新Python兼容需核验，旧行情示例不能视为可用。
- 查证：[官方仓库](https://github.com/mementum/backtrader) · [许可依据](https://api.github.com/repos/mementum/backtrader) · [维护元数据](https://api.github.com/repos/mementum/backtrader)。

### 7. kernc/backtesting.py · P1

- 使用方式：候选组件；接入前评估；适用阶段：G2。
- 本项目用途：构造小型第二引擎对照实验。
- 适用限制：AGPL-3.0；不能宣称默认满足A股停牌、涨跌幅、交易单位和交收规则。独立实现才有交叉验证价值。
- 查证：[官方仓库](https://github.com/kernc/backtesting.py) · [许可依据](https://api.github.com/repos/kernc/backtesting.py) · [维护元数据](https://api.github.com/repos/kernc/backtesting.py)。

### 8. microsoft/qlib · P2

- 使用方式：候选组件；接入前评估；适用阶段：G2–G5。
- 本项目用途：研究特征、数据处理、实验和模型比较的组织方式。
- 适用限制：先解决真实数据、验证协议和资源瓶颈；不直接搬样例结果或将模型复杂度当作质量。
- 查证：[官方仓库](https://github.com/microsoft/qlib) · [许可依据](https://api.github.com/repos/microsoft/qlib) · [维护元数据](https://api.github.com/repos/microsoft/qlib)。

### 9. PyPortfolio/PyPortfolioOpt · P1

- 使用方式：候选组件；接入前评估；适用阶段：G3。
- 本项目用途：学习组合约束、风险估计与权重计算接口。
- 适用限制：估计误差、交易成本、输入频率与可交易性仍需审查；优化权重不是买入指令。
- 查证：[官方仓库](https://github.com/PyPortfolio/PyPortfolioOpt) · [许可依据](https://api.github.com/repos/PyPortfolio/PyPortfolioOpt) · [维护元数据](https://api.github.com/repos/PyPortfolio/PyPortfolioOpt)。

### 10. ranaroussi/quantstats · P1

- 使用方式：候选组件；接入前评估；适用阶段：G3–G4。
- 本项目用途：学习组合绩效报告、回撤与指标解释。
- 适用限制：收益序列、基准、频率和资金流口径必须统一；报告漂亮不代表结论有效。
- 查证：[官方仓库](https://github.com/ranaroussi/quantstats) · [许可依据](https://api.github.com/repos/ranaroussi/quantstats) · [维护元数据](https://api.github.com/repos/ranaroussi/quantstats)。

### 11. duckdb/duckdb · P2

- 使用方式：候选组件；接入前评估；适用阶段：G4–G5。
- 本项目用途：历史样本确有规模瓶颈时，评估本地列式查询。
- 适用限制：不提前迁移现有账本；默认分支不等于稳定发行版，实际接入需固定release。
- 查证：[官方仓库](https://github.com/duckdb/duckdb) · [许可依据](https://api.github.com/repos/duckdb/duckdb) · [维护元数据](https://api.github.com/repos/duckdb/duckdb)。

### 12. vnpy/vnpy · P2

- 使用方式：架构参考；适用阶段：G4–G5。
- 本项目用途：参考事件、网关与模块边界，理解研究层和执行层如何隔离。
- 适用限制：只读架构参考；本任务不接券商、不提交凭据、不启用真实下单或自动交易。
- 查证：[官方仓库](https://github.com/vnpy/vnpy) · [许可依据](https://api.github.com/repos/vnpy/vnpy) · [维护元数据](https://api.github.com/repos/vnpy/vnpy)。

## 检索覆盖与未采用项

本清单按以下环节筛选，不能穷尽 GitHub。成长适配、优先级和应用产物是结合本项目的建议；书目身份、许可和维护状态依据链接中的一手来源。

- 人民币/A股数据
- 数据合同与异常审计
- 可解释统计与时间验证
- 独立回测对照
- 模拟组合与本地报告

以下未采用项的细节沿用初次筛选证据；不把未入选项目说成永久不可用。

- **ricequant/rqalpha**：当前LICENSE带非商业限制，不按普通Apache-2.0开源项目计入推荐；只保留受限源码参考入口。 [依据](https://github.com/ricequant/rqalpha/blob/master/LICENSE)

## 使用这份清单的方式

每次从当前成长环节选一本书的一部分和一至三个相关仓库，先形成小产物，再决定是否接入。实际采用时固定版本，核对当前官方文档、许可证和项目已有实现。旧书中的 API 示例以现行官方文档为准。

本次交付是书目和公开项目研究：未购买或复制整书，未安装或运行候选项目，也没有把候选能力计作本项目的已验证成果。


## ISBN 清单（按项目归档）

以下是本项目书目中的 ISBN/在线版本标记；相同书目按项目保留。这里只记录书目信息，不包含或分发书籍正文。

| # | 书名与版本 | ISBN-13 / 版本说明 |
|---:|---|---|
| 1 | Investments（2026 Release） | 9781265417550 |
| 2 | Python for Data Analysis（第3版） | 9781098104030 |
| 3 | Forecasting: Principles and Practice（第3版） | 9780987507136 |
| 4 | Quantitative Trading（第2版） | 9781119800064 |
| 5 | Advances in Financial Machine Learning | 9781119482086 |
