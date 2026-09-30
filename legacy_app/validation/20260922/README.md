# v0.1 本地验证记录（2026-09-22）

- `unittest.txt`：82 项标准库测试，以及源码编译检查。
- `independent-review.py` / `.txt`：独立审查的 8 组反例测试及输出。在项目根目录使用 `PYTHONPATH=. python validation/20260922/independent-review.py`。
- `browser-results.json`：root 独立浏览器验收的 10 项结果；真实 HTTP API、临时空白账户数据库，非页面接口 mock。
- `browser-check.cjs`：验收源码的可移植版本。它会创建合成数据和模拟账户，必须使用独立测试数据目录。需要开发机另装 Playwright/Chromium，应用运行本身不依赖它们。先 `python -m invest --port 8771 --data-dir <临时空目录>`，再 `node validation/20260922/browser-check.cjs`。可用 `PLAYWRIGHT_MODULE`、`CHROMIUM_PATH`、`INVEST_REVIEW_URL` 与 `INVEST_REVIEW_OUTPUT` 覆盖依赖及路径。截图和导出默认写系统临时目录。
- 原始浏览器脚本在执行环境使用绝对路径与临时中文字体配置；此处仅把这些环境路径参数化，不改变断言。截图置于 Drive 检查点 ZIP 的 `review/`。
- UI 实现者另验证了次日卖出及空/单点零值/恒定净值缺基准三类曲线，并检查 390px 四页无整页溢出。root 已独立复核主要流程并目视检查桌面和移动截图。

这些验证证明当前输入与反例下的软件行为，不证明收益或市场可成交性。Tushare 真实凭据、Windows 和远端 CI 在此提交前快照中尚未验证。
