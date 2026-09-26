# Invest 当前状态 — 0.2.0-rc2

本记录在 G1–G5 集成交付后对账；实时 refs、PR 和 CI 仍以 GitHub 为准。仓库 `Jvust/Invest`，稳定 ID `1381007406`；工作分支 `feat/g1-g5-workbench-20260926`，Draft PR #4，基于研究分支，未合并 main。

## 实际交付

Windows 候选包源提交：`5075cf746019b7d107de603384c0cf02ce1ac02a`。exact-source CI run `36259089513`。最终交付回执：`governance/growth_delivery_result.json`。Drive 文件 `Invest-G1-G5-0.2.0-rc2-完整交付.zip`，ID `1gzhcMhXqFCUChFW5nqBCTcFw0fawLEn7`，SHA256 `67ee272c6439073f1a1ed757ec6ca986f385cafe1adaf314ab92290c475f00f4`，14984511 字节，上传后已下载回读匹配。

本轮新代码修复：打包源码身份空哈希、满额账户成功操作重试、备份与恢复总容量不一致、导入脚本副作用、页面版本显示。没有修改旧研究记录或删除旧交付包。

## 验证事实

259 项完整测试通过（较 rc1 新增24项）；最终 Windows EXE 原生自测、23 项 Edge 浏览器检查、退出重启持久化通过，无 JavaScript 异常，无真实 provider 调用。16 个 Python 核心文件身份从源码到实际 EXE 导出一致；便携包 1007 个文件经清单覆盖核对。

实际 Windows 合成备份在 Linux 新目录恢复：6 个事件的哈希链通过，净资产11103.00元、净入金1000.00元、利润103.00元。该对账不证明真实交易或前向运行。

Windows 首次尝试因换行测试夹具失败，失败记录未删除。第二次代码与浏览器通过，但视觉检查发现旧版标签；最终版本绑定真实运行版本并新增浏览器断言，再次完整构建，而不是修改旧包标签。

## G1–G5 与真实门槛

已具备数据审计/回执、探索比较/算术回放、历史复盘/事件链、中文工作台/备份恢复及默认关闭的本地时点事实扩展。它们是离线工程候选能力。尚无真实数据许可与完整市场事实、三种真实市场环境、独立第二成交引擎、冻结留出有效性、连续前向观察、独立审阅或用户电脑验收。

`frozen_holdout=NOT_OPENED`；`forward_observation=NOT_STARTED`；`broker_connected=false`；`roadmap_all_empirical_gates_passed=false`。三段连续样本不当作三种环境；算术回放不当作第二成交引擎；历史补录不当作真实前向天数。

## 下一步

先在用户设备启动本候选版并验证备份恢复；然后按既有真实供应商 runbook 获取有许可、可追溯的小样本和市场事实证据。同时补独立执行引擎与隔离对照，前置证据齐全后才能冻结并首次观察未见留出集、开始真实前向记录。无需再从初始化仓库或 v0.1 的130项测试起点重复开发。

全量历史状态保存在 `docs/history/pre_growth_rc2` 和 `governance/checkpoints/pre_growth_rc2`。`growth_delivery_current.json` 是源提交中的历史快照，后续成品结果读 delivery_result。仅修改交接文档的后续提交不改变上述 EXE 源提交。
