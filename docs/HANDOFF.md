# Invest 接续：本机采集入口之后

先读AGENTS、project_state、market_acquisition_result、CURRENT_STATE、artifact_manifest、pending_sync，再核实live分支/PR/CI。当前 `Jvust/Invest` ID1381007406，Drive沿用 `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u`。

当前分支 `feat/local-data-acquisition-20260927` / Draft PR #8，基于PR #7。执行源码6742f30d、CI36286072515；后续治理提交不是新运行。原rc2 EXE仍是5075cf74，不因源码工具而自动更新。

已交付的采集器、向导、四接口原始保存、固定错误码、失败标记及自动核验不需要重做。两平台481测试/334子测试/5人工链路与Windows取消通过；实际有凭据采集未做。完整源码和原始CI证据在Drive新包，回执有精确哈希与下载回读。

**下一动作需要真实材料：** 由实际持权用户在本机运行 `Collect-Market-Data-Windows.cmd` 或 `python tools/collect_market_data.py wizard`。不在聊天索取Token，不假造访问证明。核实样本范围和各接口权限，失败保留原批次，重试新建目录。当前直连HTTPS不使用代理环境变量；不暗中改系统代理/证书或回退明文。

随后审阅适用许可、同源对应、日历、停复牌、公司行动、历史有效规则，再单独设计下游provider/binding桥接。当前工具永不以采集成功代替执行授权或未见样本开启。无法取得材料时保持真实数据待办，不通过增加人工测试宣称完成。

旧源码/包/结果不覆盖，主分支和PR合并仍需明确指令。原生保守策略适配、独立信号、留出和持续前向是独立任务，不借旧验证计数。上版完整治理在 `governance/checkpoints/pre_local_acquisition`；各组件详细结果继续看其历史回执。
