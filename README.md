# Invest · 人民币研究与复盘工作台

> 新增研究扩展：**独立RQAlpha执行实验室v0.1**（Draft PR #5，源码附加组件，不是新版EXE）。[当前状态](docs/CURRENT_STATE.md) · [直接复现](docs/ENGINE_LAB_GUIDE.md) · [六类实际分歧](docs/ENGINE_LAB_FINDINGS.md) · [精确交付回执](governance/independent_engine_result.json)。下文rc2程序信息继续有效；新的受限第二执行引擎已经实现，真实市场合同仍待验证。

当前版本 **0.2.0-rc2**。G1–G5 离线工程能力已经集成，Windows 候选程序已验证；**不表示全部真实成长门槛通过**。不连接券商、不自动下单、不承诺收益。

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
