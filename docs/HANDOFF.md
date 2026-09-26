# Invest 接续入口：独立执行实验室之后

先读AGENTS、project_state、independent_engine_result、CURRENT_STATE、ENGINE_LAB_FINDINGS、artifact_manifest和pending_sync，再核实live分支、PR和CI。仓库 `Jvust/Invest`，稳定ID1381007406；Drive沿用 `15ypjgfIv3Xl0BWlxcEVm4OvP9XoyK30u`。

## 当前工作与原程序分别恢复

新增实验室在 `feat/rqalpha-comparison-20260927` / Draft PR #5，基于原rc2分支PR #4，均未合并main。实验室精确源码 `bfcb1ffbed99ff92089f098f4681c6e6594591d4`，CI `36263215741`。原Windows程序仍为0.2.0-rc2 / 源码5075cf74，不因为新源码附加组件而改名或自动更新旧EXE。

完整新包已上传Drive并回读，身份从independent_engine_result取得。第三方RQAlpha完整快照已经在Github/03_Invest两分片中，复用原对象；不要重新上传相同源码。安装环境需用户确认上游实际许可，安装网络与研究运行网络分开。

## 不重复开发的成果

312测试/平台、24原生对照（18一致+6分歧）、16未来日期扰动、重复运行、33浏览器检查/平台均通过；45份业务JSON跨Linux/Windows相同。worker运行真正上游成交、账户与风控，不接收Invest成交结果。六类差异及初次失败均保留。原工作台源码没有为制造一致而修改。

## 下一任务

优先ENG-03版本化执行合同：共享时段容量、整笔/部分成交与剩余单、费用精度与价格取整。用新版本新样本，不覆盖原冻结协议或历史结果。ENG-04真实数据需先核验许可、原始身份、交易日历/停牌、公司行动和规则有效日期，沿用原provider_validation/evaluation/opening链。ENG-05再做独立策略信号、留出、真正前向观察。

现有实验室只接收合成、单证券、无公司行动的固定股数合同。日线代理与全天成交量不是真实开盘已知信息；16组未来日期扰动不证明这点。CI成功不是用户电脑实测或独立审阅。没有任何全部G1–G5现实验收声明。

源码运行与安装步骤见ENGINE_LAB_GUIDE；不安装扩展仍可用原rc2。后续改引擎/worker必须重新核验源身份、全部核心回归、真实第三方执行和差异预期；不要只跑mock或只对最终收益。
