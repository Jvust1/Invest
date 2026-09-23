# 接手说明

更新时间：2026-09-23。本文已按 GitHub/Drive 实时状态重建，不再沿用 2026-09-22“功能分支尚未发布”的旧快照描述。

## 先恢复权威状态

1. 读取 `AGENTS.md`、目标分支 `SECURITY_POLICY.md`、Drive 根目录 `全项目` 入口及动态发现的全部 `全项目_` 基线，再按 [PRE_FLIGHT_CHECKLIST.md](PRE_FLIGHT_CHECKLIST.md) 恢复项目。
2. GitHub `Jvust2/Invest` 是代码、治理、当前状态与下一步权威；Drive 项目目录 `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u` 保存原始资料和长期 artifact。
3. 当前功能线为 `feat/a-share-research-v0.1-20260922`，Draft PR #2 → `main`，保持未合并；任何合并都需要针对 PR #2 的明确授权，禁止直接写 main。
4. 并行长期路线图在 PR #1 / `docs/long-term-roadmap-20260922`，继续独立保留；未来处理合并顺序时同时保留应用 README 使用说明和长期路线图入口。
5. 接手后读取 [PROJECT_NORTH_STAR.md](PROJECT_NORTH_STAR.md)、[CURRENT_STATE.md](CURRENT_STATE.md)、[ARCHITECTURE_INVARIANTS.md](ARCHITECTURE_INVARIANTS.md)、[DECISION_LEDGER.md](DECISION_LEDGER.md)、[EVALUATION_LEDGER.md](EVALUATION_LEDGER.md)、`governance/project_state.json`、`governance/artifact_manifest.json` 与 `governance/pending_sync.json`。

## 当前已验证的软件状态

- v0.1 已实现标准库本机中文网页、CSV/交易日历审计、有限日频均线回测、人民币模拟账本和 Tushare 四接口研究导入边界。
- 应用/测试基线的 GitHub Actions 已在 Ubuntu/Windows × Python 3.11/3.12 四组合通过 82 项单测与源码编译。
- 样本外与 forward-paper 方法协议 v1 已冻结，状态为 `FROZEN_METHOD_V1`。
- `invest/evaluation.py` 的 fail-closed evaluation binding 校验器已完成远端四矩阵 CI；它只校验冻结身份、窗口、成本、基准、PIT/证券池与市场数据边界，不证明真实数据完整或策略有效。
- 当前首个真实数据 binding 仍为 `PENDING_LICENSED_REAL_DATA`；frozen holdout=`NOT_OPENED`，forward-paper=`NOT_STARTED`。

## Drive 与恢复证据

Drive 当前项目根目录已回读，只存在已核验的 `Invest_v0.1.0_source_checkpoint_20260922.zip` 和 `05_Reference_Materials/`。源码检查点 ID 为 `1Iscm0akdNG5s0WNJfc83-T_eh88xIz1F`；它是发布前冻结源码/截图证据，不因后续 GitHub 治理与代码增量而重写。

本次恢复未发现新的已授权真实行情数据集、真实 evaluation binding 或可代替本地授权 Tushare 联调的 artifact。因此不得伪造 provider 验收，不得把 mock、合成数据或格式校验当成真实供应商证据，也不得为了自动化把 Token 写入 GitHub、聊天或共享 Drive。

## 本机复核入口

在 Python 3.11+ 环境可运行：

```sh
python -m invest --open
python -m unittest discover -s tests -v
python -m compileall -q invest
```

默认服务仅绑定 `127.0.0.1:8765`。`.invest/` 中的本地数据、模拟账户和笔记不进入仓库或共享 artifact。每次新代码提交都要重新以 live head/checks 验证，不能沿用旧 CI 结论。

## 当前唯一主线与阻塞边界

1. **真实供应商验证**：仅在本地合法授权可用时调用真实 Tushare，核对权限、返回字段、单位、交易日历、停牌缺行、复权/公司行动边界，并只保存脱敏证据。
2. **首次 `BOUND_UNOPENED` binding**：授权真实数据集形成后、任何 frozen holdout 结果被读取之前，固定原始/规范化数据身份、代码身份、development/validation/holdout 区间、候选参数、至少三组成本情景、基准、证券池/PIT 证据和市场数据边界，并运行 `invest/evaluation.py`。
3. 若 `can_open_holdout=false`，继续保持 holdout 未打开；未知市场边界必须显式阻断，不能静默补安全值。
4. 只有候选、合法数据 binding 和 opening blockers 全部闭环后，才开始 append-only forward-paper；不得事后回填信号或把已见数据重新称为 unseen。

若合法真实数据仍不可用，可继续做与上述主线直接相关、可独立验证且不制造伪证据的治理/测试/研究准备；不要用无关功能扩张替代真实数据门禁。当前恢复检查点见 `governance/checkpoints/20260923_real_data_gate_reconciliation.json`。
