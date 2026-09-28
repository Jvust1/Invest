# Invest 当前状态｜500 元金额级决策支持

更新时间：2026-09-28 12:06:47 CST。GitHub `Jvust/Invest` 为代码、当前状态和决策的权威来源；Drive 保存长期成果与快照。

## 当前开发链

- 最近功能 head：`c29dbd0b1cdb0bdc6247ffb6b4ab1f1406840cde`，Draft PR #13（双日历）；PR #9–#13 均 Open、Draft、Unmerged。
- 本状态同步走独立 Draft PR #14，基于 PR #13；main 未修改。
- PR #13 主矩阵 run `36375284697`：Ubuntu/Windows × Python 3.11/3.12 四项通过。
- 双日历真实依赖 run `36375284696`、三个优化器真实合同 run `36375284617`、PyPortfolioOpt 真实求解器 run `36375284652` 均通过。

## 产品目标与已完成实现

产品目标：用户输入可投资人民币金额（当前示例 500 元），获得可解释、可复盘的配置情景，说明留存现金、资产候选、金额、交易单位、成本、流动性、风险与复评条件。

- PR #9：ChatGPT → GitHub Actions → Invest artifact 公开研究链路。Tencent smoke 成功 39 个交易日；Eastmoney 失败记录保留，provider 不静默回退。
- PR #10：报价、整手、费用、流动性、现金约束下的离散配置层，并回报股数、成本和剩余现金；仅情景计算。
- PR #11：PyPortfolioOpt 可选最小方差适配；拒绝不完整/非法输入及静默回退。
- PR #12：Riskfolio-Lib、skfolio 适配，并对三种后端权重及金额结果做交叉比较；分歧只作复核信号。
- PR #13：XSHG 与 SSE 两套日历会话逐项比较，保留版本、日期差集、输入观测缺口。周末区间终点缺陷已修复并由真实库测试覆盖。

## 尚未完成

- P0：QuantStats / Empyrical 风险与绩效指标交叉检查。
- P1：Hikyuu、Zipline-reloaded、bt 独立回测或第二引擎核对。
- 真实授权行情与许可证据、个券停复牌/公司行动/交易规则有效性、至少三个真实市场环境、frozen holdout、持续 forward observation、独立审查和真实设备验收仍未关闭。

## 治理边界

公开数据结果仍为 `PUBLIC_RESEARCH_ONLY`，离散金额例子为 `SCENARIO_ONLY`。算法输出不证明个券当前可成交，也不保证未来收益。没有券商连接、自动订单或 frozen holdout 开启。所有功能 PR 与状态同步 PR 保持 Draft，未合并 main。

## 下一步

1. 加入 QuantStats / Empyrical 双指标合同与真实库测试，明确输入口径及缺失数据行为。
2. 再做 Hikyuu / Zipline-reloaded / bt 中可在当前环境运行的独立复核，并记录兼容边界。
3. 真实行情工作只在授权证据可用时进行；先绑定 provenance 与规则有效期，再讨论任何非公开研究结论。
