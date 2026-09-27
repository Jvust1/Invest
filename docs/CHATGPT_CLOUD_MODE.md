# ChatGPT 云端研究模式

目标：用户直接在 ChatGPT 对话中使用 Invest，而不是维护本地 Python、CMD 或行情采集目录。

## 架构

`ChatGPT → GitHub request commit → GitHub Actions → public research artifact → ChatGPT analysis → optional Drive archive`

GitHub 是代码/治理权威；Drive 是长期成果库；Actions artifact 只是运输层。

## 公开研究模式

无需用户 Token。当前支持显式选择：
- `akshare_tencent`：Tencent Securities 日线接口；
- `akshare_eastmoney`：Eastmoney 日线接口。

源选择写入 request 和结果。某一源失败时不会在同一次运行里偷偷切换；ChatGPT 若改用另一源，会新建第二个任务并保留第一份失败证据。

输出只做价格区间、收益变化、回撤、波动率和移动均线等描述统计，标记 `PUBLIC_RESEARCH_ONLY`。

## 正式证据模式仍独立存在

ENG-04A/04B 不删除。只有未来取得明确适用的数据权利并补齐日历、停复牌、公司行动、历史有效规则等证据后，才可单独推进正式 provider/binding 适配。

公开云端研究永不：
- 冒充执行级数据；
- 打开 holdout；
- 连接券商；
- 下单；
- 自动输出买卖结论。

## 对话体验

用户以后只需要说：
- “用 Invest 看 600000.SH 最近三个月。”
- “换另一个公开源交叉看一下。”
- “继续分析上次标的。”

ChatGPT 负责建立任务、读取结果和管理项目证据。
