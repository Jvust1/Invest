# 聊天插件候选版：验收状态（2026-10-02）

这不是把项目进度字段改成 100%，也不是收益或可交易性背书。

## 已观察到

- 基于 `Jvust1/Invest` 的 `4831ae9bd446079e87b4245a9053b409916d920e` 副本实现 14 个 MCP 研究工具。
- Windows / Python 3.12 全套 unittest：601 项，588 项通过、13 项跳过，进程退出 0。
  跳过的可选依赖/外部运行环境不视为验收通过；负路径测试的 `round_trip: ERROR / FAIL`
  标准输出保留，不能单凭此行推翻 unittest 的实际退出状态，也不应删掉失败证据。
- 实际 stdio 子进程完成初始化、列工具、调用配置计算、无效输入失败；HTTP 完成
  初始化/列工具/调用、恶意 Host 421、缺失 OAuth Bearer 401 与资源元数据发现。
  JWT 使用测试签名校验 issuer/audience/subject/scope/expiry，不是生产身份提供者授权。
- 实际 MCP 工具读取绑定的 GitHub README，固定到上述 commit；私有 Drive 挂载索引
  search/fetch 成功。直接 Drive API 尚未在此服务设置 OAuth，不能称为已经在线接通。
- 私有索引：225 份仓库文档、15 条 Drive 文件元数据、1239 条结构化资料片段。
  三套投资相关书籍包通过声明 SHA256 校验，正文仅留在私有索引。
- Drive 分卷重建为 115991587 字节，组合 SHA256
  `e60b831695820ef749d9684cc7fb0e405c7319448237cfd12e281b1f14d39497`；
  八套嵌套源码包的声明哈希和全成员 CRC 通过。仅审计，没有执行未知源码包。
- 修复基线暴露的合并断层：版本字段、PaperLedger、桌面兼容入口、备份合计大小、
  stockstats 导出、构建脚本导入副作用、工作台路由/锁及历史行情十一字段解析。

## 不标记完成

- 生产 Secure MCP Tunnel / HTTPS OAuth 部署和健康状态。
- 目标账号**普通 Chat**选择 Invest 后实际调用工具、目录范围检查、断开/撤销复测。
- 当前网络的 Eastmoney 历史读取出现代理连接错误。`market_history` 返回明确错误，
  没有以合成价格或其他未声明来源替代。解析合同的修复用固定源码和测试证明，
  不把网络失败写成行情接通。
- 数据使用/再分发许可、实时报价可靠性、交易日历完整性、公司行动和 PIT 覆盖。
- 真实留出集、三种真实市场环境、持续前向验证、第三方独立审阅。
- 自动真实下单、券商账户接入和收益保证（本插件不提供）。

## 资料的使用方式

| 资料 | 当前适用范围 | 不能直接推导的结论 |
|---|---|---|
| GitHub 主仓库 | 当前源码、已有研究/配置/风险/时点事实模块、上游注册表 | 所有可选上游均已安装或验证 |
| Invest 历史交付 ZIP、capsule、checkpoint | 版本、证据、历史记录的来源审计 | 历史百分比就是当前真实接入状态 |
| Qlib/AKShare/vn.py/backtesting.py/Backtrader/vectorbt/FinRL/RQAlpha 固定源码 | 按各自许可证选择性适配；回测、数据、模型能力参考 | LFS 指针、样例 CSV、测试 fixture 是完整获准市场数据 |
| Forecasting Principles and Practice、Python for Data Analysis、Quantitative Trading 的 JSONL 等 | 私有方法参考，来源包/成员/片段可追溯 | 实时行情、投资建议标签、可公开再分发的训练集 |

公开仓库不包含私人索引、书籍正文、交易账户信息或真实 Token。
最后的普通 Chat 步骤见 [接入说明](CHAT_PLUGIN.md)，需在目标账户实际观察后补记，
不能用本页或 CI 结果代替。
