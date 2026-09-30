# RQAlpha 固定源码研究与第二执行引擎适配

## 目的与定位

本轮在 Invest 0.2.0-rc2 已验证工作台之外，新增可独立关闭的 **合成双引擎执行实验室 v0.1**。原有 Invest `execute_order` 与真实 RQAlpha 成交、账户模块分别执行同一份下单意图，逐日比较现金、持仓、净值和分项费用。没有将 Invest 成交单交给 RQAlpha 复读，也没有把旧的算术回放重新命名为第二引擎。

它是 G2 独立执行对照的工程证据增量，不是完整 A 股市场适配、策略信号的独立实现、未见留出测试、真实前向观察或全部 G1–G5 验收。只有固定合成数据场景可以运行。本轮不接入真实行情、券商或模型服务，不改旧账本、原冻结结果或 main。

## 来源身份与复用现有归档

- 上游：`ricequant/rqalpha`。
- 实际研究源码：`0d98adefa87956e26f3e7ca5b26b5f3fc7ca834f`。
- 上游固定链接：https://github.com/ricequant/rqalpha/tree/0d98adefa87956e26f3e7ca5b26b5f3fc7ca834f 。
- 原始 ZIP：`ricequant__rqalpha__0d98adefa879.zip`，5,135,462 字节，SHA-256 `9baa67dc8a1ed195894489bac52a0b92c307c9d79c164de55da5ed59df1d2b29`。
- 现有保险库：Drive `Github/03_Invest_量化投资`，文件夹 ID `1oU0O8bQDy6yaIZoQdblf1goui8laOi1I`。其中两个分片重组得到类别 ZIP，SHA-256 `e60b831695820ef749d9684cc7fb0e405c7319448237cfd12e281b1f14d39497`。
- 分片原 Drive ID：`1rb4OfgtCEZtVZ4Fw0lF4_O7nBlMKt6tc` 与 `1YQ8bTDHexBlh1iAGqgZzyBt70LTRjaMG`。本轮复用它们，不重复上传同一第三方快照。
- 包内 151 个 Python 文件按 UTF-8/LF 核验；生成的 `_version.py` 不参与固定源码比较。完整映射见 `integrations/rqalpha/source-lock.json`，其规范映射身份为 `4617f50229799b78a31692c3edfbe2c1b99b004ef4d95a93bdc98242a9494260`。

检查的是已安装的源码文件、锁定清单及实际 worker 输出。它不是执行中字节码签名、硬件证明或独立第三方审计；依赖包版本在每次安装和 CI 中另行记录。

## 许可证事实

归档中的 `LICENSE` 区分非商业个人/教育科研使用与商业/组织使用，并要求后者取得米筐授权；不能仅凭打包元数据中的 Apache-2.0 标签宣称无条件商业使用权。本适配不附送授权，命令要求用户先阅读上游许可并明确确认其使用符合许可。计划用于实际投资业务、公司系统、服务或分发时应先核实授权范围。代码许可也不等于金融数据许可。

固定许可原文：https://github.com/ricequant/rqalpha/blob/0d98adefa87956e26f3e7ca5b26b5f3fc7ca834f/LICENSE 。本轮合成研究不需要买入证券或调用数据供应商。

## 实际阅读的模块与设计取舍

| 固定源码路径 | 检查重点 | 本项目采用方式 |
|---|---|---|
| `rqalpha/main.py` | Environment、Mod、数据/事件源、Portfolio、Executor 初始化顺序 | 使用公共 `run_func`，不复制主循环 |
| `rqalpha/interface.py` | AbstractDataSource / AbstractEventSource / AbstractMod | 只适配合成数据和代理事件 |
| `rqalpha/core/executor.py` | 交易日前置、BAR、收盘、结算事件 | 真正运行上游执行器，不直接伪造账户变化 |
| `rqalpha/mod/rqalpha_mod_sys_simulation/simulation_broker.py` | 即时匹配、剩余单取消与事件顺序 | 保留原生 broker；只提交意图并读取 TRADE |
| `rqalpha/mod/rqalpha_mod_sys_simulation/matcher/bar_matcher.py` 与 `matcher/base.py` | 百分比滑点、涨跌停、累计成交容量、部分成交 | 不替换匹配器，不把分歧调成一致；匹配规则保留原样 |
| `rqalpha/mod/rqalpha_mod_sys_accounts/api/api_stock.py` | 固定股数与金额下单的区别、风控调用 | 只用固定股数 `order_shares`；关闭买入金额自动转换 |
| `rqalpha/portfolio` 及股票 position 实现 | 原生现金、持仓、T+1、估值 | 每日从原生账户读取，不用 Invest 数字覆盖 |
| `rqalpha/mod/rqalpha_mod_sys_transaction_cost` | 最低佣金、税率、ETF 配置继承与数值精度 | 原生费用计算；演示参数显式映射并保存请求配置 |

公开接口参考：https://rqalpha.readthedocs.io/zh-cn/latest/development/data_source.html 。这是接口参考，不替代对固定源码的检查。

## 日线代理事件，不冒充真实开盘行情

Invest 现有执行器以日开盘价尝试成交；RQAlpha 原生日线默认时点不应直接混用。因此每个合成评价日提供两个明确代理 BAR：09:31 时把匹配器的当前价格设置为合成开盘价；15:00 提供合成收盘估值，且不再下单。第一条行情仅供前日状态初始化。

数据模型标记为 `SYNTHETIC_DAILY_OPEN_CLOSE_PROXY_NOT_INTRADAY_DATA`。整日 OHLC/成交量是**事后已知的测试边界**，不是上午可知的真实流动性。未来扰动测试只检查后续日期不改变前缀结果，不证明这一代理模型具有真实开盘可交易性，也不证明策略构造意图时没有未来信息。

证券身份、无公司行动、复权因子1、T+1、非ST、上市状态及测试日历均为合成声明。V1 不处理 ETF、分钟线、除权分红、历史身份变化、融资、做空、真实市场规则版本或多证券组合。

## 对照协议与观察结果的解释

冻结在代码内的最终协议有24组：18组预期一致、6组预期存在已识别规则差异。每组都还核验独立手算/人工指定的成交数量，防止“两边都没干活”被当成通过。套件 PASS 表示全部观察符合逐项检查；其中6组报告仍明确标记 DIVERGED。

| 差异场景 | 保留的实际差异 |
|---|---|
| 日成交容量不足 | Invest整笔拒绝；RQAlpha可按100股单位部分成交 |
| 同日多单共用成交容量 | 原Invest按单检验日容量；RQAlpha匹配器累计扣减同一BAR容量 |
| 分项费用取整 | Invest逐项到分；原生费用保留更细精度 |
| 过户费用 | Invest明确计算；本RQAlpha原生股票费用不单列该项 |
| 百分比滑点 | Invest按不利方向到分；原生百分比结果可能有更细小数 |
| 滑点超出声明OHLC | Invest拒绝；原生路径的成交可不同 |

额外提供16组未来日期价格扰动、同输入重复运行、实际Python网络审计钩子拦截探测。它们是工程行为证据，不是16次真实市场试验。

### 初次实验发现与保留的修正

第一次24组探索记录保留在成果证据中：3组因“股票零比例佣金+非零最低佣金”被未使用的ETF继承配置拒绝；通过给不使用的ETF配置显式0/0解决，股票的原生佣金逻辑未改。初读源码时把金额API的可用持仓裁剪混同为固定股数API，导致超额卖出、新旧仓位两组预期有误；实际固定股数API和风控整笔拒绝，与Invest一致。重新检查 `api_stock.py` 后修正协议并保留旧预期/结果，未修改任何成交引擎来追求一致。

中间一次为报告新增配置快照时遇到RQAlpha把原字典改为专用属性对象的JSON序列化错误；改为运行前保存请求配置，随后重跑整个套件。协议在开发期发生过上述修正，不宣称首次运行即全通过，也不声称未见留出。

## 独立性、验证与局限

worker是单独 `python -I` 进程，不导入Invest。输入仅有合成case、源码锁和许可确认，不含参考成交/现金/净值。真正使用上游broker、matcher、账户、仓位与风控；自定义Mod只提供数据、事件和结果采集。

父进程用环境变量白名单，不传供应商Token、PYTHONPATH或代理凭据。worker的Python审计钩子拒绝DNS和socket出站操作；RQData配置为disabled。超时、来源不符、非法JSON、缺成交、缺估值、费用不守恒或逐日账本不一致都拒绝接受。此边界不是对恶意本机管理员/原生扩展的完整操作系统沙箱。

核心53项新增单元测试使用明确标注的传输夹具或mock来检查合同，不拿它们冒充实际RQAlpha运行。原259项测试保持；真实第三方运行证据由单独实验套件和精确源码CI产出。具体成功/失败以当前回执、CI和包内证据为准。

## 后续边界

下一阶段应先确定真实数据许可与版本化市场事实，再选择是否统一部分成交、累计流动性、费用与价格精度合同，并明确这是新研究协议，不覆盖旧冻结结果。把有分歧的报告变成可复现、可解释的研究问题，比强行消除分歧更有价值。真实策略的独立信号生成、不同市场环境、留出和前向观察仍未通过。
