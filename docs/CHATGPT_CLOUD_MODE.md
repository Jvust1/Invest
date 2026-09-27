# ChatGPT 云端研究模式

目标：让用户直接在 ChatGPT 对话中使用 Invest，而不是在本机运行采集脚本。

## 架构

`ChatGPT → GitHub request commit → GitHub Actions → public research artifact → ChatGPT analysis → optional Drive archive`

GitHub 继续是代码与治理权威；Drive 继续保存长期成果。Actions artifact 是短期运输层，不是长期权威存储。

## 两条数据路线必须分开

### 公开研究模式

无需用户 Token。ChatGPT 创建任务，云端使用固定版本公开财经接口获取研究数据并做描述性统计。结果明确标记 `PUBLIC_RESEARCH_ONLY`。

它适合：
- 价格区间复盘；
- 收益、回撤、波动、移动均线等描述性统计；
- 为后续研究选择需要进一步核验的问题。

它不适合：
- 冒充有明确授权的执行级数据；
- 自动回测正式成交合同；
- 打开 holdout；
- 自动交易。

### 正式证据模式

原 ENG-04A/04B 不删除。未来如果取得明确适用的数据权利和完整市场事实，仍走原来的原始字节、许可、交易日历、停复牌、公司行动、历史规则核验链。

## 用户体验

以后用户可以直接说：

- “用 Invest 看 600000.SH 最近三个月。”
- “把 000001.SZ 最近一年做一份研究报告。”
- “继续分析上次那个标的。”

ChatGPT 负责建立 job、等待云端执行结果、读取 artifact、解释结果以及按需同步 Drive。用户不需要维护本地 Python 环境。
