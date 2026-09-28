# 三套最小方差后端交叉检查

`min_variance_scenario(history, sizing_request, backend="pypfopt")` 保持原来的默认调用。`backend` 可显式设为 `riskfolio` 或 `skfolio`，分别调用 Riskfolio-Lib 的 Classic/MV/MinRisk 和 skfolio 的 MeanRisk/VARIANCE/MINIMIZE_RISK。三者都只生成候选权重，继续由 Invest 离散配置层计算股数、买入费用和剩余现金。

可选安装组：`optimization`、`optimization-riskfolio`、`optimization-skfolio`；一次比较可安装 `optimization-all`。这些依赖只在需要运行对应后端时加载，主测试和原桌面路径不用安装。

`compare_min_variance_backends(history, sizing_request)` 默认依次运行三套模型。每套使用同一份输入历史与报价约束，结果保留后端版本、历史 SHA256、权重和可行性配置；`pairwise_gaps` 明示任意两套的最大绝对权重差、剩余现金差。**差异不是投票，也不选胜出模型。** 任意后端缺失或求解失败会中止比较，不静默改用另一套结果。

API 依据：[Riskfolio-Lib Portfolio](https://riskfolio-lib.readthedocs.io/en/latest/riskfoliolib/portfolio.html) 与 [skfolio MeanRisk](https://skfolio.org/generated/skfolio.optimization.MeanRisk.html)。本轮用 30 个合成观测日测试真实库接口与计算传递；这只验证软件链路。输入许可、真实交易日历、市场规则、停复牌、公司行动、样本外/前向表现仍未验证。即使三个后端接近，也不能推出盈利能力或交易可执行性。
