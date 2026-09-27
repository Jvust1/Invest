# Invest 当前状态：ChatGPT 云端公开研究 v0.1

当前开发分支 `feat/chatgpt-cloud-research-20260927`，Draft PR #9 基于 PR #8。云端运行代码 `f2ab93b6a23c57517d1348e4efe5dd8703386289`；四矩阵回归 run `36315941217`。首次成功任务提交 `e093baa3265bae4d00239932c47def79be2a55b1`，云端 run `36316010850`。

## 用户现在怎么用

普通公开研究不再要求用户本机安装 Python、运行 CMD 或准备 Token。用户直接在 ChatGPT 中说明标的和研究范围；ChatGPT 负责写入唯一 job、观察 GitHub Actions、下载结果并继续分析。

云端 job 只接收白名单字段和 Invest 已支持的沪深主板证券格式，日期区间最多 366 个自然日。数据源显式写入请求；一个 provider 失败时不在同一次运行中偷偷换源。

## 实际验证

云端模式代码在 Windows/Linux × Python 3.11/3.12 四个矩阵中各跑 491 项测试，全部成功。Windows UTF-8 默认编码差异在 CI 环境变量中修正，不改旧测试逻辑。

第一次云端公网尝试明确使用 Eastmoney 路径，run `36315653626`，到达 provider 后出现 `ConnectionError / RemoteDisconnected`；failure artifact `10930656841` 完整保留。

第二次建立独立任务并显式指定 Tencent，run `36316010850` 成功，artifact `10930891754`：
- 标的：600000.SH
- 请求：2026-08-01～2026-09-25
- 实际交易日：2026-08-03～2026-09-24，共 39 日
- 首/末收盘：9.63 / 9.00
- 区间价格变化：-6.54%
- 5/20 交易日变化：-0.66% / -0.77%
- 收盘序列最大回撤：-6.85%
- 日收益年化波动率：18.90%
- MA5 / MA20：9.02 / 9.184；MA60 样本不足
- 规范化 CSV SHA256：`1c11dfbb921b5af8b2797bc76ee2c730502cef4bcf0cbe896d005488c89ed017`

以上仅是云端链路验收与描述性示例，不是对该股票的推荐。

## 长期归档

Drive 原 Invest 目录新增 `Invest-ChatGPT-Cloud-Research-v0.1-20260927.zip`：
- Drive ID：`1kumrq8YMaRZWbaf12HpWdCOo4F9itvjh`
- 8,279 bytes，6 个成员
- SHA256：`66a4a45b570a29bd95afa1bca35751d2d088b59a44b9483a441476a325b3d0ca`
- 已下载回读，大小、SHA256、ZIP 完整性和包内 manifest 验证通过
- 同时保存第一次 Eastmoney 失败证据与第一次 Tencent 成功证据
- 不复制整个仓库源码：代码权威继续是 GitHub 精确 commit

正式回执：`governance/assistant_cloud_result.json`。

## 仍未改变的边界

所有该模式数据都标为 `PUBLIC_RESEARCH_ONLY`。AKShare 软件包和底层公开数据权利是两件事；本模式没有独立验证数据许可、停复牌、公司行动、历史有效交易规则或券商成本，因此不能把结果升级为正式执行级市场证据。

原 ENG-04A/04B 保留为未来正式证据路径，但普通研究不要求用户本地跑。原 0.2.0-rc2 EXE、账本、RQAlpha worker、成交合同、历史结果均未替换。frozen_holdout 仍未打开，forward observation 未开始，broker 未连接，没有实盘下单或收益承诺。
