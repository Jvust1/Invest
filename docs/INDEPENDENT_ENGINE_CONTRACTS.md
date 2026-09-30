# Hikyuu / Zipline-reloaded 隔离合同

这一阶段不把第三方框架包装成“完整回测已验收”，而是先验证最小、可审计、互不替代的独立能力边界。

## Hikyuu 2.8.2

专用合同使用 Hikyuu 的临时 `Stock` + `set_kdata_from_df` 注入 3 个合成日线观测，不下载行情、不读取用户本地数据库。随后使用 `TC_FixedETF(commission=0.00025, lowestCommission=5.0)` 探测 1.90 元 × 200 股的 ETF 买入费用，确认最低佣金原语为 5 元。

这只证明：Hikyuu wheel 可安装、内存 K 线可注入/读取、费用原语可独立调用。尚未证明其信号系统、事件时序、成交延迟、T+1、停牌、涨跌停或真实 A 股规则与 Invest 等价。

## Zipline Reloaded 3.1.1

专用合同读取 `XSHG` 交易日历，并注册/移除一个隔离的自定义 CSV bundle 定义，确认 bundle 绑定的日历仍为 `XSHG`。本阶段**故意不 ingest、不运行策略**，避免在没有明确数据目录、资产元数据和中国市场成交适配前制造“已完成回测”的假象。

Zipline 默认佣金/滑点模型也不等同于 Invest 当前的最低佣金、税费、过户费、整手和费用取整规则；下一步必须先做自定义执行模型和真正的临时 bundle ingest，再比较成交与净值。

## CI 隔离

`independent-engines.yml` 将两个引擎放在独立 job 中。Hikyuu 失败不能被 Zipline 成功掩盖，反之亦然。两个 job 都只在 PR 中运行，主环境继续不安装这些大依赖。

当前仍是 `PUBLIC_RESEARCH_ONLY` / `SCENARIO_ONLY`。真实授权行情、公司行动、停复牌、历史规则有效期、冻结 holdout 和前向观察仍是独立 gate。
