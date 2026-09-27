# Invest · 当前开发：ENG-04A 原始数据与证据核验

当前源码扩展在 Draft PR #7 / `feat/market-evidence-20260927`，不替换以下0.2.0-rc2程序或旧执行实验室。使用说明见 `docs/REAL_DATA_INTAKE.md`，实际结果读 `governance/market_evidence_result.json` 和 `docs/CURRENT_STATE.md`。

原Invest Drive目录新增 `Invest-Market-Evidence-v0.1-20260927.zip`；解压后打开 `reports/index.html`，无需Python或网络。完整源码包含四响应本机组包、逐字段来源/规范化对照、许可及事实声明核验。干净两平台各437测试、22人工案例、77浏览器检查通过。实际源码1c8250a9，CI36284039387。

**没有取得真实行情或确认用户许可。** 示例全部人工构造，工具只检查字节/转换/声明，不授予交易、数据权利或留出开启。下一阶段需要实际有权使用的本地原始数据和独立审阅。新代码与旧EXE的身份分开保存；没有合并main。

---

## 保留的 ENG-03 版本化成交合同 v0.2

上一阶段源码附加组件在 Draft PR #6，`feat/execution-contract-20260927`。离线报告见 Drive 的 `Invest-Execution-Contract-v0.2-20260927.zip` 中 `reports/index.html`。它不是新 EXE，不替换下面原0.2.0-rc2桌面程序。

新增：共享成交量、部分/整笔成交政策、费用与价格精度合同、原生不支持显式拒绝、逐单容量报告。两平台370测试和110浏览器检查通过；99组合分为32原生一致、66原生不支持、1输入拒绝，不混记为全部一致。

ENG-03阶段回执：`governance/execution_contract_result.json`；使用和边界：`docs/EXECUTION_CONTRACT_V2.md`；接续：`docs/HANDOFF.md`。旧v1差异和rc2程序保留，main未合并，真实数据/留出/前向/独立审阅仍待验收。

---

## 保留的基础工作台说明

# Invest · 人民币研究与复盘工作台

> 保留的研究扩展：**独立RQAlpha执行实验室v0.1**（Draft PR #5，源码附加组件，不是新版EXE）。[当前状态](docs/CURRENT_STATE.md) · [直接复现](docs/ENGINE_LAB_GUIDE.md) · [六类实际分歧](docs/ENGINE_LAB_FINDINGS.md) · [精确交付回执](governance/independent_engine_result.json)。下文rc2程序信息继续有效；新的受限第二执行引擎已经实现，真实市场合同仍待验证。

桌面程序版本 **0.2.0-rc2**。G1–G5 离线工程能力已经集成，Windows 候选程序已验证；**不表示全部真实成长门槛通过**。不连接券商、不自动下单、不承诺收益。

## 启动

从现有 Drive `Invest` 目录取得 `Invest-G1-G5-0.2.0-rc2-完整交付.zip`，解压其中 `Invest-Windows-Portable.zip`，保留整个 `Invest` 文件夹并启动 `Invest.exe`。不要遗漏 `_internal`，也不要覆盖旧数据目录。先点“载入合成演示”；原有导入与回测入口在 `/legacy`。

源码运行：`python -m invest --data-dir D:\Invest-Data --open`。核心不需要模型 API、美元账户或 GPU。

## 已集成能力

| 成长级 | 离线能力 |
|---|---|
| G1 | 行情及日历审计、来源回执、非空源码身份、人民币账本 |
| G2 | 有界假设比较、共同窗口、三种成本情景、失败保留、独立算术回放 |
| G3 | 历史模拟及人工复盘、资金流/股息/费用、估值、哈希链、幂等重试 |
| G4 | 中文工作台、Windows 控制器、导出、完整备份与恢复 |
| G5 | 可关闭的本地时点事实扩展、可见时间与修订查询 |

## 原rc2程序核验

259 项测试通过，实际 Windows EXE 与 23 项浏览器检查通过；源码与包内身份、完整包哈希、跨平台备份重放通过。构建源码 `5075cf746019b7d107de603384c0cf02ce1ac02a`；CI run `36259089513`。用户本人电脑和独立审阅仍未验收。

详细结果见 [当前状态](docs/CURRENT_STATE.md)、[交付回执](governance/growth_delivery_result.json)、[API](docs/G1_G5_API.md)、[rc2 修复说明](docs/G1_G5_RC2.md)、[接续入口](docs/HANDOFF.md)。长期路线原稿位于 `docs/long-term-roadmap-20260922` 分支的 `docs/LONG_TERM_ROADMAP.md`，不以提交数或时间自动升级。

测试：`python -m unittest discover -s tests -v`；装有 pytest 的开发环境也可用 `python -m pytest -q`。真实数据许可、市场事实、第二引擎的真实市场合同、未见留出验证和持续前向观察仍待完成。

旧 README 与状态完整保存在 `docs/history/pre_growth_rc2`，不再作为当前执行起点。原rc2程序保留在 Draft PR #4；新增实验室在 Draft PR #5，均未合并 main。
