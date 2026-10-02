# Invest 0.3：高星项目从清单到实际调用

本批不是把整个第三方仓库复制进 Invest，而是在已有架构中实现 **11 个可运行、可选依赖、固定输入边界的原生后端**。
部分项目此前仅有目录记录，现在晋级实际适配器；SciPy/scikit-learn 已是基础依赖，本次新增它们的研究接口，不把它们算作首次引入的库。
本批原生 API 在本机直接调用和实际 MCP stdio 子进程执行；验收使用合成数据，不能推断行情可用性或收益。

## 能力与实测版本

| backend | 项目 / 版本 | 实际新增能力 | 最小点数 |
|---|---|---|---:|
| polars | [Polars](https://github.com/pola-rs/polars) 1.44.2 | 原生列式聚合、总体标准差 | 8 |
| duckdb | [DuckDB](https://github.com/duckdb/duckdb) 1.5.6 | 独立内存数据库、固定参数化描述统计查询 | 8 |
| pyarrow | [Apache Arrow](https://github.com/apache/arrow) 25.0.1 | Arrow Table 与 C++ compute 核心统计 | 8 |
| statsmodels | [statsmodels](https://github.com/statsmodels/statsmodels) 0.15.0 | ACF 与预先固定滞后的 Ljung–Box 诊断 | 8 |
| arch | [arch](https://github.com/bashtage/arch) 8.0.0 | 显式增量累积后的稳健方差比诊断 | 32 |
| scipy | [SciPy](https://github.com/scipy/scipy) 1.18.1 | 分布矩、分位数、探索性正态性检验 | 8 |
| ta | [ta](https://github.com/bukosabino/ta) 0.11.0 | RSI14、SMA20、EMA12、布林带20 | 26 |
| ffn | [ffn](https://github.com/pmorissette/ffn) 1.2.2 | 正价格/NAV 总收益、回撤和简单收益描述 | 8 |
| networkx | [NetworkX](https://github.com/networkx/networkx) 3.7 | 涨/跌/平状态转换图与 PageRank 描述 | 8 |
| plotly | [Plotly](https://github.com/plotly/plotly.py) 7.1.0 | 本地生成可审查的图表 JSON 规格 | 8 |
| sklearn | [scikit-learn](https://github.com/scikit-learn/scikit-learn) 1.9.1 | 时间顺序三折 Ridge/持续值基准比较 | 24 |

Polars / DuckDB / Arrow 用相同输入相互核对，统一 `ddof=0`；没有把三个不同统计约定冒充一致。
arch 接受**加法增量**，不是价格或复合简单收益；ta/ffn 接受 >=1e-6 的正价格/NAV。
所有工具返回输入 SHA256、用户声明来源/as_of、实际后端版本和边界说明。

## 安装（完整研究组合使用 Python 3.12）

```sh
python -m pip install -e '.[chat,test,research]'
python -m pip check
python -m unittest discover -s tests -p 'test_opensource*.py' -v
python -m unittest discover -s tests -p 'test_chat_research.py' -v
python tools/check_research_backends.py
python tools/check_research_backends.py --mcp
```

`research-data`、`research-stats`、`research-features` 可以分组安装。基础安装和既有 Chat 能力不强制安装这批依赖。
`research` 固定直接依赖的被测版本；**不是完整传递依赖锁文件**。SciPy 1.18.1 / NetworkX 3.7 需要 Python >=3.12，
所以完整组合只在 Python 3.12 CI 验证；不要把原有基础 Chat 的 3.11 测试当作完整研究组合的兼容性证明。
不在工具调用中自动 pip install，也不在缺失后端时偷偷用另一个算法替代。

## Python 与 Chat 调用

```python
from invest.opensource import integration_catalog, run_integration

print(integration_catalog())
result = run_integration(
    'duckdb', {'values': [100, 101, 99, 102, 103, 102, 105, 104]},
    source='SYNTHETIC example, not market data', as_of='2026-10-03')
print(result)
```

MCP 增加 `research_catalog`、`research_run`，工具总数 **16 → 18**。
在已经完成授权的 Chat 客户端可请求：“列出 Invest 研究后端，再用我明确提供的序列分别调用 Polars、DuckDB、Arrow 并比较均值和标准差。”
`research_run` 参数为 `backend`、`values`、`source`、`as_of`；`values` 最多5000点，只接受有限 JSON 数字，绝对值≤1e6，拒绝 bool/字符串/NaN。
来源是调用者声明，不会被当作 URL 抓取。数据无逐点日期，因此不验证日历/陈旧性；需要 OHLC 日期检查时继续使用 `analyze_price_series`。

## 有意保留的边界

- DuckDB 禁止外部访问、扩展自动下载加载和磁盘溢写；不接受用户 SQL、表名或文件路径。
- Plotly 仅返回 JSON，不执行 HTML/脚本、不发布外链、不表示普通 Chat widget 已验收。
- sklearn 的 scaler 只在训练折拟合，时间顺序三折、gap=1；这是**滚动单步**评估，后续测试点可使用此前已经观察到的测试值作为滞后特征，不是固定起点多步预测。
- p 值不是“策略有效概率”，PageRank 不是收益/转移概率，RSI/布林带不是自动下单指令。
- 常量/近常量/浮点精度不足有显式 null/原因或拒绝，不伪造“零风险”结论。
- Windows 实际 stdio 测试曾卡在 SciPy `_fblas` 延迟加载，已在启动传输读线程前初始化基础依赖 `scipy.linalg`；不因此导入全部可选库。CI 同时运行直接 API 和冷启动实际 MCP 的11后端验收。
- 当前许可证、身份、星数、默认分支 commit 见 [GitHub 证据](OPEN_SOURCE_EVIDENCE_20261003.json)；
  [许可筛查说明](OPEN_SOURCE_LICENSES_20261003.md) 保留原始标签。arch 的 NOASSERTION 仍须人工许可复核；
  NetworkX 原文标明 BSD-3-Clause，但保留 GitHub 的 NOASSERTION。Arrow/SciPy 发行物可能包含其他许可组件。
- GitHub 默认分支 commit 不等于被测 PyPI 发行版源码 commit；不得混淆它们的证据。
- 不搬运 GPL/AGPL/商业限制项目源码以充数量；原来 reference_only 的项目仍保持边界。
- 星数和安装状态都不是质量、数据许可、收益或端到端验收保证。
- 本批没有配置普通 Chat 账号授权、生产 HTTPS/隧道、实时 Drive OAuth 或券商连接；这些既有待办没有被软件测试“清零”。
