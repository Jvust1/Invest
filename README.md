# Invest

A composable investment research and backtesting toolkit.

## Included open-source components

The third_party/ tree brings in reusable modules from the MIT-licensed bt,
ta, and quantstats projects. See THIRD_PARTY.md for exact revisions and
attribution.

## Quick start

    python -m pip install -e .
    python examples/moving_average.py

The first integration layer in invest.pipeline supports an SMA crossover,
fee-aware long/flat backtests, and summary statistics. It avoids look-ahead by
applying each signal on the following bar.

## 可运行的完整研究链路

最新[完整源码候选与复现说明](docs/upstream/coherent-source-candidate-2026-10-01.md)涵盖实际输入到原生 JSON / PNG、空工作台恢复和独立现金研究两条完整链路；Draft 尚未合入 main，历史 MLflow 可用性限制仍明确保留。
[可复现源码包](docs/SOURCE_DELIVERY.md)从指定提交的 Git 对象构建，保留许可与来源，排除历史二进制，并单独验证解包后的 wheel / 无可选 SDK 恢复。

[六个成熟上游的融合候选](docs/upstream/research-stack-2026-09-30.md)包含两条明确区分数据口径的流程：

- 本地 Qlib 数据 → DuckDB 离线快照 → Optuna 仅训练段搜索 → 后续区间评价 → 可备份的原生研究记录
- 合成工作台数据 → scikit-learn 滚动验证 → 已保存研究 → 本地 MLflow 归档 / 重试 → Matplotlib 图表和备份恢复

    python -m pip install '.[qlib,mlflow,charts,duckdb,optuna,test]' 'duckdb==1.5.6' 'optuna==5.0.0'
    python -m pip wheel --no-deps --wheel-dir dist .
    python tools/research_stack_smoke.py dist

该验证只生成合成数据，不连接账户或下载行情。Qlib 原生归一化价格不会进入现金 / 整手 / T+1 撮合引擎。
[原生研究记录](docs/upstream/native-research-record-2026-09-30.md)保存原始输入行、全部训练试验和后段曲线，
可通过工作台“原生价格探索研究”下载，随私人备份恢复；源代码示例会把合成 SDK 试跑结果留在指定目录。

    python -m examples.native_research_record synthetic-pilot /tmp/invest-native-demo

已有原生研究 JSON 可[显式恢复到工作台](docs/upstream/native-json-recovery-2026-10-01.md)，无需可选 SDK：

    python -m examples.native_research_record restore /path/to/native-research.json --workspace /path/to/workbench

恢复保留原始 ID、内容、声明的生产者及时间；完整校验后才写入，相同记录可重复恢复，冲突不会覆盖原件。
此恢复功能独立于 MLflow；PR #59 的既有 Windows Python 3.10 初始化超时仍未解决，不能据此声称总体验证通过。

原生研究归档也可[下载单独标注的单位资金 / 评价回撤 PNG](docs/upstream/native-research-charts-2026-10-01.md)：安装既有 charts 扩展后，在同一归档行点击“下载原生研究 PNG”。图表只读取完整校验的保存记录，不再运行研究；来源、生产者和原生单位仍保留未核验声明。

已保存原生研究还可[导出收益统计诊断](docs/upstream/statsmodels-native-diagnostics-2026-10-01.md)：可选 `diagnostics` 扩展使用真实 statsmodels 检查后续评价收益的自相关和分布形状。不足样本与常量明确标记；渐近 p 值不代表策略有效或盈利，原始研究保持不变。

工作台本地归档需在源码启动时明确启用 `--track-experiments`；失败仍保留原研究，可在结果或归档列表中重试。

## 长期成长计划

[长期成长路线图](docs/LONG_TERM_ROADMAP.md)：按能力与证据推进 Invest 的研究、模拟和工作台扩展。

## 书籍与开源参考

[学习资源清单](docs/LEARNING_RESOURCES.md)：5 本书、12 项 GitHub 参考，按成长环节说明用途、许可与最小应用产物。

## 融合状态

[滚动验证工作台](docs/upstream/sklearn-walkforward-2026-09-30.md)：复用 scikit-learn
TimeSeriesSplit，在已有假设实验室中按较早训练段选择候选，再单独评价后续区间。
支持训练/评价间隔、保留全部训练与失败记录、独立账本回放和完整 JSON 导出。
这是探索性研究，不打开冻结留出集；桌面入口依赖 PR #48 的应用恢复。

[融合状态与目录边界](docs/INTEGRATION_STATUS.md)记录当前 main 已合入的高星适配器、桌面/研究归档和独立引擎合同。

## 50 项高星融合目录

[2026-09-30 高星开源项目 50 项融合目录](docs/HIGH_STAR_50_INTEGRATION.md)记录新批次的来源、星标、许可证和能力标签。
