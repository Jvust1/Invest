# Invest 接续说明

截至 2026-09-29。先按 `AGENTS.md` 读取治理文件，再核对实时 PR/CI。

## 接续位置

- Draft [PR #17](https://github.com/Jvust/Invest/pull/17) / `feat/500cny-replay-risk-report-20260929`，基于 PR #16。
- 完整回归验证的功能提交：`735b1638c2e00ef5a14ce9b0e37b180f3946ddc7`；后续治理同步提交只改文档/状态，继续工作前核对实时 PR head。
- 主矩阵 `36531969490` 四环境全过（每组 532 项，11 项可选测试跳过）。
- 三库端到端 `36531969541` 两项通过；风险指标 `36531969509`、bt `36531969518`、日历 `36531969551`、优化器 `36531969501`、PyPortfolioOpt `36531969530` 均通过。
- #17 已完成费用感知的固定配置净值→日收益→六项风险报告闭环。首日收益包含已发生入场费用；Invest/bt 分歧或少于 30 个共同观测时 fail-closed。
- Hikyuu/Zipline 尚未运行，不要把 bt 账务一致和三库风险报告写成完整独立市场回测验收。

## 继续顺序

1. Hikyuu / Zipline 的隔离合成数据初始化/bundle、交易日历、成交与费用规则合同。
2. 授权真实数据与 provenance、停复牌、公司行动、历史规则证据；之后再规划真实市场结论。
3. 冻结 holdout、前向观察、独立审查、真实设备和重复使用价值继续保持未完成。

## 交付记录与范围

GitHub 为代码和当前状态权威。既有 Drive checkpoint ID `1vFoLqrAZmcrbmyHbXJUbLSpFSqImMJhZ81jfon-1Wwk` 已追加 PR #17 并回读验证，revision `ANLCKQm_NtGARTWf2gCAp3WZlHxCO52sRBJ9qA7e3IKyRWTEwMHLfO14T20-2VR68bxr0k8_w_tj9z8DMTIVG0kgE81p3dg1lUhn8_oqpOw`。没有新 EXE/APK 或替换历史交付。

仅 `PUBLIC_RESEARCH_ONLY` / `SCENARIO_ONLY`。不自动打开 holdout、连接券商、下单、修改 main 或合并 PR。功能和状态 PR 保持 Draft，等待明确合并指示。
