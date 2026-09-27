# Invest · 人民币研究与复盘

当前新增：**本机授权采集入口 v0.1**。它连接“范围预览 → 本机权限确认与隐藏凭据 → 四接口原始保存 → 自动离线核验”。已验证软件，不代表已经取得真实数据或许可。原 Windows 0.2.0-rc2 EXE 与账本未替换。

从原 Drive Invest 文件夹取得 `Invest-Local-Acquisition-v0.1-20260927.zip`，完整解压后进入 `source`，双击 `Collect-Market-Data-Windows.cmd`。需要已有 Python 3.11+ 和适用供应商权限；Token 只在本机隐藏输入，不发聊天、不写命令参数。没有权限时仍可使用原工作台，不编造材料。

命令入口：`python tools/collect_market_data.py wizard`。只预览用 `plan`，不会访问凭据或网络。说明见 [采集操作](docs/MARKET_DATA_COLLECTION.md)。

两平台各481项测试、334子测试及5种人工采集链路通过；Windows向导取消通过。真正有凭据接口、本机网络和用户设备尚未验证。采集或映射成功不自动授权回测、交易、分享或留出开启。

最新权威入口：[当前状态](docs/CURRENT_STATE.md)、[采集交付回执](governance/market_acquisition_result.json)、[接续](docs/HANDOFF.md)。源码扩展保留在 Draft PR #8，未合并 main。旧桌面、双引擎、成交合同和原始证据工具各自的交付回执继续保留。
