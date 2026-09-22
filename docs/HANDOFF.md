# 接手说明

本说明对应 2026-09-22 的 v0.1 提交前本地工作树。安全 bootstrap 已完成，功能分支与草稿 PR 在本快照时尚未发布；不要把计划状态当成已完成事实。

## 先恢复权威状态

1. 读取项目 `AGENTS.md`、`SECURITY_POLICY.md`、实时全项目入口及动态基线，按 [PRE_FLIGHT_CHECKLIST.md](PRE_FLIGHT_CHECKLIST.md) 确认权限和同步范围。
2. 在 GitHub 核对 `Jvust2/Invest` 的 main、活动 PR、base/head SHA 和 CI。记录中的原始 main 为 `71b32347fd954b7952f748b852503779851dbf1a`，安全 bootstrap 为 `172803ad30cd2065719944f1fab26a952c42be54`，它们不是后续功能发布的固定结论。
3. 查找计划分支 `feat/a-share-research-v0.1-20260922` 及其对 main 的单个草稿 PR；若不存在，仍按未发布处理。保留已有工作，不自动合并或覆盖分支。
4. 阅读 [PROJECT_NORTH_STAR.md](PROJECT_NORTH_STAR.md)、[CURRENT_STATE.md](CURRENT_STATE.md)、[ARCHITECTURE_INVARIANTS.md](ARCHITECTURE_INVARIANTS.md)、[DECISION_LEDGER.md](DECISION_LEDGER.md) 与 [EVALUATION_LEDGER.md](EVALUATION_LEDGER.md)。GitHub 管代码与治理，Drive 管源码检查点等大文件。

发布前已发现并行文档 [PR #1](https://github.com/Jvust2/Invest/pull/1)，分支 `docs/long-term-roadmap-20260922`，head `4fc6e668cd60f544809a0a204ad688c2edf37961`，base `security-bootstrap`，尚未合并。它只改 README 与 `docs/LONG_TERM_ROADMAP.md`。本轮应用发布不改该 PR/分支；后续安排合并顺序时核对双方 README，保留应用使用说明和长期路线图入口。

## 启动与复核

在仓库根目录使用 Python 3.11 或更高版本：

```sh
python -m invest --open
```

默认打开 `http://127.0.0.1:8765`；端口冲突可用 `python -m invest --port 8766 --open`。运行目录 `.invest/` 保存本地数据、回测、私人账户与笔记，已忽略提交；不要上传其中的私密内容。退出使用 Ctrl+C。

```sh
python -m unittest discover -s tests -v
python -m compileall -q invest
```

当前单测结果为 82 PASS（35/20/16/11）。复跑时记录实际环境、提交 SHA、命令和输出，不把这份历史结果沿用为新改动的验收。浏览器检查脚本与结果见 `validation/20260922/`；Playwright/浏览器属于开发验证工具，不是应用运行依赖。执行脚本前确认其本机服务地址与浏览器环境。

先用“加载演示数据”检查完整流程。演示数据和 `examples/` 都是 140 个合成日期 × 2 个代码，不是真实市场；日历也不能当成交易所官方日历。UI 的合成标识必须保留。

## 本轮发布交接

- 主执行者负责汇总代码、文档与验证材料，并发布计划分支和单个草稿 PR；不得据本文推定已获合并授权。
- 提交前核对 `validation/20260922/` 中的脚本、结果与这份记录一致；截图放 Drive 源码检查点 zip 的 `review/` 路径，避免将私人运行数据混入检查点。
- 发布后回读 refs、PR base/head/diff 与 CI 结果；功能提交和 PR 编号以 GitHub 实际产生的记录为准。若后续更新本文，保留本轮验证的合成数据及环境边界。

## 下一阶段的优先事项

1. **真实供应商验证。** 在获授权的本机环境设置 `TUSHARE_TOKEN`，核实权限、返回字段、单位、停牌缺行和日历；记录脱敏结果，禁止将 Token 放页面、仓库或验证附件。现有 mock 通过不代表接口账号联调通过。
2. **企业行动与执行数据契约。** 在允许真实数据执行前，先定义停复牌、除权除息、登记/派息日期、送转/配股、红利税和逐日价格限制的覆盖范围及反例。四接口 Tushare 导入继续研究专用；不能简单把未知状态改为 false 或删除阻断。
3. **目标平台验证。** 在 Windows 复跑启动与关键流程；发布后读取实际 Actions 结果，处理真实失败再入账。
4. **研究效果评价。** 先冻结有出处、可追溯的样本及评价方案，分清开发样本、样本外与前向模拟；检查成本、基准和存活偏差。软件正确性与合成曲线不能代替收益证据。

仅在用户明确选择相应方向后扩展范围，不将这些待办视为券商连接、真实下单或全自动交易授权。对第三方框架的现有调查限 README、许可与官方 API；未拷贝其代码、未引入运行依赖，也未完成深层源码研究，详见 [REFERENCES_AND_RULES.md](REFERENCES_AND_RULES.md)。
