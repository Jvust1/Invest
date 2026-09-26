# Invest 接续：ENG-03之后

先读AGENTS、project_state、execution_contract_result、CURRENT_STATE、EXECUTION_CONTRACT_V2、artifact_manifest及pending_sync，再核实live refs/PR/CI。仓库Jvust/Invest，ID1381007406；Drive原Invest目录15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u。

当前开发 `feat/execution-contract-20260927` / Draft PR #6；基于RQAlpha PR #5，后者基于rc2 PR #4。本轮未修改main或合并。最新执行源 `a013549109a29fc183a3b653f09ab70f5a3b3c1a`，精确CI `36266137882`。后续元数据提交不视为另一次执行。原EXE仍0.2.0-rc2，源5075cf74，当前新包是源码附加组件。

ENG-03不用重复：370测试/290子测试/平台，99组合中32原生一致、66原生不支持、1输入拒绝；8新扰动、110浏览器检查/平台。旧24原生对照和16扰动保留；新旧业务JSON跨平台结构一致。共享容量和费用/价格合同已实现；保守原生适配仍显式未支持。

查看reports/index.html无需Python；复现命令在EXECUTION_CONTRACT_V2中，结果目录须新建。上游固定源复用Drive/Github/03_Invest，不重复归档，不默认获得商业或数据许可。

下一优先ENG-04真实数据前置：来源许可、原始文件与规范化映射、有效交易日历、停牌、公司行动和规则日期。沿用provider_validation/evaluation/opening链，另做真实数据适配，不把真实数据重标为demo。独立策略信号、冻结未见留出与真正前向观察后续按证据推进。没有真实provider/券商/模型调用，没有独立人工审阅或用户电脑验收。

保留旧引擎、原生worker及旧金样本。新的原生保守适配必须新版本、重新source lock、完整回归与真实第三方执行；不为制造一致降低规则。当前Drive包和校验身份读execution_contract_result，pending_sync为空仅代表归档无欠项，不表示全部成长目标完成。
