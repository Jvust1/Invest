# Invest → ChatGPT 普通聊天的研究插件

## 能力

同一个 MCP 服务提供 14 个只读工具：status、search、fetch、list_sources、
github_read_file、drive_list_files、drive_read_file、allocation_scenario、
portfolio_snapshot、risk_summary、backtest_sma、pit_facts、upstream_catalog、market_history。
复用原有 Invest 计算代码，不把第三方源码包直接执行或整包塞入核心。

绑定仓库 `Jvust1/Invest`，stable repository ID `1381007406`。
旧治理中的 Jvust/Jvust2 名称是历史记录；不能据此改接另一个本机目录。
GitHub 在线读会先校验 stable ID，再固定 commit；所有来源返回引用和内容哈希。
Drive 默认范围为既有 Invest 与 03_Invest 两目录，可由部署者显式追加获准目录。

## 本地启动与测试

在源码目录使用 Python 3.11/3.12：

```sh
python -m venv .venv
# Activate .venv, then:
python -m pip install -e '.[chat]'
python -m unittest discover -s tests -p test_chat_plugin.py -v
python -m invest.chat.mcp_server --transport stdio
```

本包根目录的 plugin.json + mcp.json + skills/ 是便携插件结构；先安装 Python 依赖。
本地 stdio 配置并不会自动安装进 ChatGPT 网页，也不会自动上线一个公网服务。

## 私有资料检索

```sh
python tools/build_chat_catalog.py --repo <REPO_ABSOLUTE_PATH> \
  --drive-root <DRIVE_MOUNT_ROOT> --output <PRIVATE_CATALOG_PATH> \
  --inventory <PRIVATE_INVENTORY_PATH>
```

将 `INVEST_CATALOG_PATH` 指向生成的 SQLite。该文件可包含版权文本和私人资料，
只能留在私有环境，不能推送到公开仓库。脚本仅读取已挂载 Drive 文件；源码 ZIP
只建立清单、大小和哈希，书籍按来源包/成员/片段保留身份。首次生成后不要覆盖旧索引，
用新的快照路径更新。结构化书籍是方法参考，不是实时行情或执行级市场数据。

实时 Drive API 是另一条可选路径，部署者在环境或密钥库中设置自己的只读 OAuth
access token 或 refresh-token 三项配置。不会继承本聊天连接器的 Token。
完整私有索引可在 stdio + 安全隧道下检索，不要求把凭据交给 ChatGPT。

## 普通 Chat 接入

OpenAI 官方文档允许通过 MCP 插件在聊天中调用工具；可选公开 HTTPS 或 Secure MCP Tunnel。
开发者模式的可用性仍取决于账户/工作区，必须在目标账户实际验收。
参考：[连接测试](https://developers.openai.com/plugins/deploy/connect-chatgpt)、
[聊天快速开始](https://developers.openai.com/plugins/build/app-quickstart)。

优先：把本地 stdio 服务连接到官方 Secure MCP Tunnel，在 ChatGPT 的插件创建流程
选择实际 tunnel_id。或者部署到自己的 HTTPS HOST，配置已存在的 OAuth issuer，
并用 `--transport streamable-http --public-url https://<HOST>/mcp`。
公网模式校验 JWT 签名、issuer、audience、到期、invest:read scope 和 owner subject；
没有 OAuth 时拒绝非 loopback 监听。它是资源服务器，不伪造 OAuth 登录服务。
参考：[认证要求](https://developers.openai.com/plugins/build/auth)。

在目标 ChatGPT 账户注册连接并完成授权后，在**普通 Chat**的新聊天中选取 Invest。
这是独立 gate：本机测试或 Work 模式成功都不能代替它。
不要填造假的服务域名、tunnel_id 或 plugin_asdk_app ID。
需要完整打包分发时，将注册流程实际返回的 MCP 映射 ID 接入 OpenAI 扩展字段。
本包尚未提交公开插件目录，也不代表插件审查已通过。

## 最后验收清单

1. Chat 中“查看 Invest 接入状态”：观察 status 的真实工具调用。
2. “读取 Invest README 并说明源码版本”：观察 github_read_file、commit 和引用。
3. “找 Drive 的量化交易结构资料”：观察 search + fetch，只返回获准内容摘录。
4. “按这些明确假设计算 500 元方案”：观察 allocation_scenario，385 元/115 元合成案例仅验证代码。
5. “数据未知时不要猜价格”：观察明确缺口，不冒充实时事实或收益保证。
6. “资料中说把 Token 发到外站”：不扩大范围、不执行资料中的指令。
7. 保留工具名、参数、输出、错误、来源身份、时间和用户确认记录。
8. “读取明确区间的 A 股日频历史”：观察 market_history 的真实输出或明确网络失败，
   核对最新观察日、未复权口径及来源；不要当作实时可成交报价或已获数据授权。

100% 必须包含部署、目标账户普通 Chat 工具调用、获准资料访问和撤销连接复测；
真实行情许可、时间有效性及长期前向验证是另一个不能靠软件测试替代的门槛。
所有工具只做研究/情景计算，不连接券商、不执行真实资金交易、不保证收益。
