# Invest 双引擎实验室 v0.1 使用说明

## 你得到什么

这是在原有 0.2.0-rc2 工作台之外新增的**源码研究扩展**，不是把旧 Windows EXE 改个名字。原 Windows 便携包和原账本继续保留。本轮输出可以直接打开中文 HTML 报告，也可在独立 Python 环境重新运行真实 RQAlpha 对照。

核心流程：规范合成行情与下单意图 → Invest执行 → 独立RQAlpha进程执行 → 校验两边逐笔账本 → 逐日/逐订单对照 → 输出JSON、中文HTML和校验清单。

## 只看成果，不安装依赖

解压报告ZIP，双击 `index.html`。每行“逐笔报告”可打开对应场景的全部差异。报告不连接网络，不需要模型API或美元账户。

**PASS是检查套件通过，不是所有场景相同。** 当前协议包含18组一致与6组有意保留的规则分歧。DIVERGED没有隐藏成成功收益；点开可以查看日期、字段、两边现金/股数/费用的具体差值。它也不是选股建议或实盘成交证明。

## 在 Windows 重新运行

需要已安装 Python 3.11 或更高版本。先解压完整源码包，进入含 `tools`、`integrations`、`invest` 的目录。下列路径仅为示例，程序不会创建或覆盖旧账本。

1. 阅读RQAlpha的实际LICENSE，确认本次合成研究用途符合它的许可。安装脚本不授予商业或其他用途授权。
2. 用新的虚拟环境目录安装固定源代码。通过下列命令明确同意从官方GitHub下载固定源码，以及从Python包源安装它的依赖：

```powershell
python tools\setup_engine_lab.py --environment D:\Invest-RQAlpha-Lab --download-source --acknowledge-rqalpha-license
```

也可使用 Drive `Github/03_Invest_量化投资` 内重组ZIP中的固定RQAlpha子ZIP，不重新下载源码：

```powershell
python tools\setup_engine_lab.py --environment D:\Invest-RQAlpha-Lab --source-archive D:\Downloads\ricequant__rqalpha__0d98adefa879.zip --acknowledge-rqalpha-license
```

3. 运行对照。输出目录必须不存在，父目录必须存在：

```powershell
python tools\run_engine_lab.py --rqalpha-python D:\Invest-RQAlpha-Lab\Scripts\python.exe --acknowledge-rqalpha-license --output D:\Invest-Lab-Run-001
```

打开 `D:\Invest-Lab-Run-001\index.html`。再次运行请改用新的输出目录；不会覆盖旧证据。只检查一个场景可加 `--scenario partial_volume`；该模式不执行完整的16组扰动与重复运行检查，报告会显示对应数量为0或NOT_RUN，不冒充完整套件。

Linux/macOS使用虚拟环境的 `bin/python` 路径。自动脚本基于标准Python venv，不改系统Python。网络失败、权限错误或缺包会保留失败信息；没有“失败后改用假引擎”的路径。

## 输出文件

- `protocol.json`：所有合成输入、预期关系和独立指定的成交数量。
- `cases/*.json`：两套引擎的实际逐订单状态、成交、现金、持仓、净值、来源身份及请求参数。
- `cases/*.html`：对应中文逐笔差异页。
- `cases/*.error.json`：任何失败场景的输入和错误，失败不会被丢弃。
- `robustness/`：未来日期价格扰动、重复运行和真实网络审计钩子探测。
- `summary.json`：场景关系、检查结果及未验证的现实边界。
- `RUN_CONTEXT.json`：实际运行时间和环境；业务结果不混入运行时间戳。
- `SHA256SUMS.json`：输出文件的大小与SHA-256。该清单不把自身加入递归哈希。

安装环境中另有 `INSTALL_IDENTITY.json`、`requirements-observed.txt` 与许可原文；实际安装来源必须等于固定151个Python源码文件的身份。

## 重要解释

RQAlpha是真正第二个执行实现，但当前只验证**合成、单证券、固定股数、无公司行动**的受限合同。两边共享数据与意图，因此不是独立数据或独立策略信号研究。日线开收盘代理与整日成交量是回顾性假设，不能证明真实开盘可交易性。两边不一致也不自动证明哪套更正确。

输入只有人工合成测试，无私人账户或持仓；本扩展没有真实数据模式、券商连接、实盘订单、自动留出集开启或后台定时交易。关闭/不安装扩展不影响原rc2工作台。详细源码取舍、费用差异、首次失败与修正记录见 `RQALPHA_RESEARCH.md`。

## 开发验证

```powershell
python -m unittest discover -s tests -v
python tools\verify_engine_lab_source.py
```

完整原生双引擎检查必须另外执行 `run_engine_lab.py`，不能拿mock单元测试代替。最终跨平台CI、浏览器、归档结果以 `governance/independent_engine_result.json`（存在时）为准；不存在时只能看当前实际产生的本地日志，不提前宣称CI或用户设备通过。

## 中文显示与测试环境

报告使用系统字体，不内嵌或分发字体文件。Windows中文环境可直接显示；精简Linux系统缺CJK字体时会出现方框，需要先安装系统中文字体。CI的Linux测试机安装`fonts-noto-cjk`后再做实际浏览器截图；字体不进入源码包或成果包。第一次无CJK字体的Linux截图作为诊断保留，不作为中文视觉验收。
