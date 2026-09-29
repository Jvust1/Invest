# Invest 接续说明

截至 2026-09-29。先按 `AGENTS.md` 读取治理文件，再核对实时 PR/CI。

## 接续位置

- Draft [PR #18](https://github.com/Jvust/Invest/pull/18) / `feat/independent-engine-contracts-20260929`，基于 PR #17。
- 完整回归验证功能提交：`3507e511e293c3004342896272bdd576c74f00b1`；后续治理同步提交只改状态/文档，继续工作前核对 live PR #18 tip。
- 主矩阵 `36532883762` 四环境全过（每组 534 项，13 项可选测试跳过）。
- 独立引擎 `36532883781`：Hikyuu 与 Zipline 两个 job 均通过。Hikyuu 已验证临时 K 线和 ETF 最低佣金原语；Zipline 已验证 XSHG 日历和隔离 bundle 注册/移除。
- 不要把 #18 写成完整独立回测验收：Hikyuu 的事件驱动 System/TradeManager 与 Zipline 的 ingest/run_algorithm、自定义中国市场执行语义都还没完成。

## 继续顺序

1. Hikyuu：临时 K 线 → TradeManager/System 合成成交，记录整手、费用取整、成交时点、T+1 差异。
2. Zipline：临时 bundle ingest → run_algorithm → 自定义佣金/滑点/整手适配。
3. 两套事件驱动合同明确后，再进入授权真实行情与 provenance gate；holdout、前向观察、独立审查和券商连接继续关闭。

GitHub 为权威来源。Drive checkpoint ID `1vFoLqrAZmcrbmyHbXJUbLSpFSqImMJhZ81jfon-1Wwk` 已追加 #18，revision `ANLCKQmNxbR8J48dJPuptTkeRx-eRCIE3W0-_JPT0kMlqICLdeAhLrlseUWadcsR3O6NUU1x78FAglRINCNWMhxip7MPZxltmW1HE--5xss`。没有新 EXE/APK 或历史交付替换；PR 保持 Draft / Open / Unmerged，`main` 不动。
