# Invest 聊天插件 0.2 升级

架构仍为 **tool-only**：直接在现有 Python MCP 服务上升级，不另造聊天应用或账户系统。
16 个只读工具支持已有研究流程；没有新增写仓库、下单、执行源码或扩大 Drive 范围的权限。
工具描述、结构化返回与注解参考官方[工具设计](https://developers.openai.com/plugins/plan/tools)和
[MCP 服务](https://developers.openai.com/plugins/build/mcp-server)文档；不把这些配置当作账户授权。

## 1. 连接诊断：connection_check

默认 `include_network=false`，完全不联网：检查私有 SQLite 的只读完整性、模式、数量、大小、
SHA256 与文件修改时间。文件大小最多 64 MiB，SQLite 操作有步数上限；活跃 WAL/journal、
损坏/变化中的文件不会报告健康。绝对私有路径、正文和异常原文不出现在结果中。
**文件 mtime/哈希不证明市场数据新鲜或真实。**

显式 `include_network=true` 才检查绑定 GitHub 的身份/ref 与每个已授权 Drive 根目录的单页元数据。
默认每个 HTTP 请求超时 20 秒；根目录最多 10 个，完整网络检查可能比单次请求更久。
不会读取整个 Drive，部分成功返回 partial；缺少 Drive OAuth 返回 not_configured。

| 字段 | 正确解释 |
|---|---|
| configured | 仅配置存在 |
| status=not_checked | 未做网络调用，不是连接成功 |
| status=healthy | 本地索引检查通过，不是来源事实验证 |
| status=connected | 本次限定身份/ref 或根目录检查成功，不代表全部资源可读 |
| checks_passed=true | 实际执行的检查没有错误；可选组件仍可能未配置/未检查 |
| chat_acceptance_verified=false | 普通 Chat 的账户验收仍未完成 |

可在源码目录通过命令行运行：

```sh
python -m invest.chat.mcp_server --check
python -m invest.chat.mcp_server --check --check-network
```

`--check` 输出 JSON 后退出：0=已执行检查健康，1=实际检查失败，2=命令参数错误。
不是监听端口，也不会创建隧道；单独 `--check-network` 会被拒绝。

## 2. 显式历史序列：analyze_price_series

当在线行情失败时，不伪造价格，也不静默换数据源。只有你明确提供有来源的 OHLC，才用此独立工具。
输入最多 5000 行；日期必须唯一递增、不晚于 as_of/上海今天；OHLC 必须满足价格关系。
价格和可选 volume 只能是有限 JSON 数字，拒绝布尔、数字字符串、NaN、未知字段及超范围值。
币种为三个大写字母；标的标签/币种/来源只作声明，不验证证券身份或许可。

示例 **仅为合成接口测试，不是实际报价或投资建议**：

```json
{
  "symbol": "SYNTHETIC",
  "currency": "CNY",
  "source": "SYNTHETIC protocol fixture",
  "as_of": "2026-09-28",
  "adjustment": "unknown",
  "max_staleness_days": 2,
  "bars": [
    {"date":"2026-09-23","open":100,"high":100,"low":100,"close":100},
    {"date":"2026-09-24","open":90,"high":90,"low":90,"close":90},
    {"date":"2026-09-25","open":99,"high":99,"low":99,"close":99}
  ]
}
```

结果含 CALLER_SUPPLIED 标记、标准化数据/请求哈希、日期覆盖、距 as_of 的日历天数、
陈旧/间隔/复权/许可警告，以及 close-to-close 描述性收益和风险摘要。
日历间隔不等于缺失交易日；252 次观察/年的年化假设未经交易日历验证。
不足三条价格不估计风险；极端价格导致数值失真时不报告误导性风险指标。
这些是样本内描述，不能从三条合成记录外推投资表现。数据不写盘、不被联网验证，不自动流入执行引擎。

## 3. 金额与检索修复

- `portfolio_snapshot` 不再先转 float 再验证 Decimal。亚分币、伪整数和略超限输入不会被浮点舍入后放行。
  输出人民币金额固定两位小数；`max_quote_age_days`（默认 7，范围 0–366）增加相对 as_of 的报价年龄/陈旧标记。
  这是日历天阈值，不是交易日或实时成交保证。
- `Catalog.search` 和 fetch 共用内容 SHA256 校验：被修改的正文不会配旧哈希返回。
- 本地检索额外探测一条记录，服务保留 GitHub/Drive 截断信息，`limited=true` 不再被错误覆盖。

## 4. 验收边界

原始源码、原始 BASELINE.zip 保持不变，主交付仍复用 MODIFIED_FILE.zip / DIFF_FILE.patch /
VERIFICATION.txt / ROLLBACK.sh 四角色。旧版本移入交付 history，失败和修复记录保留。
源码 core 版本保持既有兼容合同，独立 plugin.json 版本升级为 0.2.0。
新增单元、HTTP MCP 调用、CLI、极端数值、只读目录和异常脱敏测试；以本提交实际 CI/证据为准。

浏览器注册/授权由用户随后完成。公网认证部署、实时 Drive OAuth、行情连通/许可、真实留出与前向验证
仍是独立门槛；升级不将项目百分比伪造为 100%，不新增券商或自动真实资金交易能力。
