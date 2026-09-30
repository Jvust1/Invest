# ENG-04B 本机授权采集入口 v0.1

## 这次解决什么

上一版 ENG-04A 需要用户手工准备 `daily.json`、`adj_factor.json`、`stk_limit.json`、`trade_cal.json` 四份原始响应。本版新增一个独立、显式启动的采集入口，把范围预览、用户权限确认、本机隐藏输入、原始保存、失败留痕、组包和旧版离线核验串起来。原 ENG-04A、成交合同、RQAlpha worker、rc2 EXE 均不改写。

**已实现的是采集软件，不是已经完成真实行情采集。** 开发及 CI 的四接口响应全部由人工运输替身提供；真实用户账号、许可和有凭据请求尚未验证。公网 HTTPS 地址能够返回未认证错误，只说明公开入口可访问，不是本机网络或有效账号验证。

## 最简单的使用方式

电脑需要 Python 3.11 或更高版本。解压整个源码文件夹，双击根目录 `Collect-Market-Data-Windows.cmd`。按照提示输入一只当前支持的沪深主板代码、历史日期范围、本机适用的权限/许可材料路径和一个尚不存在的结果目录。

示例代码 `600000.SH` 仅说明输入格式，不是投资建议。默认日期是截至昨天的约一个月历史区间，可修改；本版最多366个自然日，不采集仍变化的当日日线。

预览中会列出固定 HTTPS 地址、四个接口、字段和日期。只有输入 `YES` 确认自己有权获取并在本机研究这批数据且允许此次网络请求后，程序才尝试读取 Token。优先从当前进程的 `TUSHARE_TOKEN` 环境变量读取；未配置时在终端隐藏输入。**不要将 Token 填到命令参数、聊天、截图、代码或任何要上传的文件中。** 隐藏输入不可用时直接报错，不降级为可见输入。

许可/权限材料必须是本机已有、非空、不超过2MiB的文件；程序仅记录它的 SHA-256 和大小，不复制正文、不解释其法律效力。已知带 SYNTHETIC 标记的测试材料被拒绝；这不是证明其他材料真实的鉴伪机制。你确认的范围仍须独立审阅，程序不会据此把旧核验链的 `license_review` 自动标成通过。

没有 Python 或没有供应商账号/适用权限时，不要用假的文件和 Token 反复尝试；仍可使用原 rc2 工作台及历史离线报告。

## 命令行

只预览，不访问凭据、不发请求、不创建目录：

```sh
python tools/collect_market_data.py plan --symbol 600000.SH --start-date 2024-01-02 --end-date 2024-01-08
```

交互式启动：

```sh
python tools/collect_market_data.py wizard
```

明确启动（将示例目录和日期替换为真实范围）：

```sh
python tools/collect_market_data.py collect --symbol 600000.SH --start-date 2024-01-02 --end-date 2024-01-08 --evidence D:\Private\permission.pdf --output D:\Private\Capture-001 --confirm-access --allow-network
```

这不是已发生的调用记录。开始前先核实你自己的账号及接口使用范围；程序不购买权限、不启用付费服务、不绕过配额、不使用他人凭据。

## 网络与失败行为

只向 `https://api.tushare.pro/` 做 POST，使用系统默认 TLS 证书与主机名校验。拒绝 HTTP 明文回退、301/302等跳转、非JSON/压缩响应、超过2MiB的响应及明显不完整结构。默认直连，不采用 `HTTP_PROXY` / `HTTPS_PROXY` 环境变量；若本机只有代理路径可用，此版本会失败，不修改你的代理配置或系统证书。系统级 VPN 是否能路由该连接取决于本机环境。

每个接口最多一次请求，共最多4次；接口间间隔1秒，网络套接字超时30秒，无自动重试。失败后停止其余接口，保留已成功收到的原始响应和 `.incomplete` 标记，不补造缺失数据、不回退到其他数据源。若需要重试，排除问题后选择新目录；不能把先前部分成功的不同批次悄悄拼成一次同步快照。

权限、网络、结构或反射凭据错误只保存固定诊断码。失败响应体和服务端错误消息不保存。成功体保存前，检查原始字节和JSON解码后的精确凭据反射；请求体与凭据本身不写文件。该检查不能保证识别服务端任意变换后的秘密，也不提供Python内存安全擦除、操作系统加密或同用户恶意进程隔离。

公网未认证响应可能与成功响应结构不同。只有与现有四接口合同兼容的成功响应才能组包；出现新字段或不支持结构时明确拒绝，不静默删字段来通过核验。

## 结果目录

- `raw/`：已成功收到并通过结构/敏感回显检查的原始JSON字节。
- `collection.json`：请求范围、逐接口开始/完成时刻、状态、行数、大小、原始SHA-256、本机来源代码身份和访问材料哈希。它不是第三方签名或可信时间戳。
- `bundle/`：四份成功响应组成的旧版 ENG-04A 输入，保留原始字节。许可审阅和市场事实仍为空，不代填。
- `review/index.html`、`review/report.json`：自动调用原离线核验器产生的中文报告与结构化结果。
- `.incomplete`：未完成/异常批次标记，存在时不能当成完整交付。

四接口采集完成后，如缺交易日、证券串号、价格或成交量转换有误，状态是 `CAPTURED_WITH_DATA_BLOCKERS`；不会改写原始错误或伪装成可交易。转换检查通过的状态为 `CAPTURED_MAPPING_CHECKED`，仍 `execution_authorized=false`，真实材料仍等待独立审阅。CLI退出0只表示本次采集及映射流程完成，2表示失败或有数据阻塞，1表示用户取消。

原始及规范化行情都可能受使用限制。默认结果留在本机；本工具没有上传、共享、券商下单、创建真实 evaluation binding 或开启留出集的操作。不要直接把完整采集目录传到共享 Drive。脱敏、许可和必要材料范围审阅应先行。

## 本地复现与测试

```sh
python -m unittest discover -s tests -v
python tools/market_acquisition_rehearsal.py --output acquisition-rehearsal
```

演练覆盖全流程成功、权限拒绝、中途断网、日历缺口和敏感回显。全部使用人工运输替身，目录及记录带 `TEST_TRANSPORT_NOT_REAL` / `synthetic_fixture` 标记。程序逻辑成功不能替代账号授权、真实接口联调、市场事实或投资有效性验证。原始 `.cmd` 向导、隐藏输入和你的Windows设备仍需设备侧确认。

## 实施依据与已知边界

本轮复核了以下官方页面，只据其实现HTTP字段和数据接口，不把公开页面当用户许可：

- HTTP协议： https://tushare.pro/document/1?doc_id=130
- 调用参数与权限错误码： https://tushare.pro/document/1?doc_id=40
- daily及手单位： https://tushare.pro/document/2?doc_id=27
- trade_cal： https://tushare.pro/document/2?doc_id=26
- adj_factor： https://tushare.pro/document/2?doc_id=28
- stk_limit： https://tushare.pro/document/2?doc_id=183

官方旧示例仍写HTTP地址；本实现主动要求HTTPS，失败不降级。未对用户账号的当前权限、接口成功响应、个体授权或实际网络进行验证。现有规范化停牌与公司行动字段依旧未知；下一步应由实际持权用户取得本地材料，再独立核对许可、日历、停复牌、公司行动及历史规则，而不是继续制造人工成功证明。
