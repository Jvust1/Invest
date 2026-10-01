# Invest 项目审计报告

- **审计日期**：2026-10-01
- **仓库**：`Jvust1/Invest`
- **分支**：`main`
- **审计基线**：`8d9e6aaa5ed8e2a71ef22430a45e0a77c4c24f8d`
- **范围**：当前主分支源码、测试、构建脚本、CI 配置、治理文档、第三方适配器和发布完整性逻辑
- **方法**：静态代码检查、GitHub Actions 结果复核、本地测试复现、编译检查、依赖和敏感信息扫描

## 1. 执行摘要

Invest 的核心定位是研究、回测和纸面交易工具，而不是券商实盘执行系统。核心引擎在订单约束、Decimal 金额、T+1、涨跌停、滑点手续费、交易日历和数据校验方面采用了较谨慎的实现；本地服务也设置了本机绑定、Host/Origin 校验、CSRF、请求体大小限制和 JSON 严格解析。当前代码中未发现明显的硬编码凭据，服务端不接受通过 HTTP 传入 Tushare token，整体安全边界方向正确。

当前主分支仍不具备可发布状态。最新提交的 `Invest tests` 工作流在四个矩阵任务中失败，失败不是单个边缘测试，而是主模块、桌面发布模块、测试依赖、第三方适配器和备份限制契约同时存在断裂。本地 `unittest` 也能复现主要问题。治理文档还停留在旧仓库名、旧提交和旧验证结果，导致文档中的“已验证”结论与实际 `main` 不一致。

**审计结论：不建议将当前 `main` 标记为 release-ready。** 优先修复模块契约和测试环境，使完整测试能够可靠执行；随后修复备份容量策略、测试发现边界和治理状态，再建立必需检查和依赖锁定。

## 2. 验证结果

| 项目 | 结果 | 证据 |
|---|---|---|
| GitHub Actions | 失败 | 最新提交 `8d9e6aa` 对应运行 `36804618814`；Ubuntu/Windows、Python 3.11/3.12 四个测试矩阵均失败 |
| CI 测试统计 | 失败 | `Ran 523 tests in 6.426s`；`FAILED (failures=2, errors=9, skipped=13)` |
| 本地标准库测试 | 失败 | `python -m unittest discover -s tests -q`：`Ran 522 tests`，`failures=2, errors=8, skipped=13` |
| 本地 pytest | 未能建立统一基线 | `legacy_research/tests` 与 `tests` 存在同名测试模块，触发 import-file mismatch，同时暴露相同的缺失模块问题 |
| 编译检查 | 通过 | `python -m compileall -q invest integrations tools tests` 返回成功 |
| 敏感信息扫描 | 未发现明显真实凭据 | 当前树中未发现硬编码 API token、私钥或密码；发现的 token 名称均为环境变量或测试占位符 |

本地测试是在安装当前项目和 `pytest` 后执行的；CI 工作流只执行 `pip install -e .`，没有安装测试专用依赖，因此 CI 与本地环境的失败形态略有差异，但主要代码缺陷一致。

## 3. 严重级别定义

- **P0**：可直接导致严重数据泄露、任意代码执行或不可逆资金风险。
- **P1**：阻塞主分支测试、服务启动、发布或关键功能的高优先级缺陷。
- **P2**：会造成可靠性、可维护性或部署风险，但不一定阻塞所有核心流程。
- **P3**：文档、工程体验或长期治理问题。

本次未发现 P0；发现多个 P1 和 P2。

## 4. 详细发现

### INVEST-001 — P1：主服务和测试所需模块契约已断裂

**现象**

当前 `invest/server.py` 在导入时执行 `from . import __version__`，但 `invest/__init__.py` 没有定义 `__version__`。服务相关测试因此无法收集。`tests/test_portfolio.py` 和服务代码还依赖 `invest.portfolio.PaperLedger`，而当前 `invest/portfolio.py` 只提供权重计算函数，不再提供 `PaperLedger`。桌面测试加载仓库根目录的 `desktop_runtime.py`，该文件在当前主分支不存在。

**实际错误**

- `ImportError: cannot import name '__version__' from 'invest'`
- `ImportError: cannot import name 'PaperLedger' from 'invest.portfolio'`
- `FileNotFoundError`：`tests/test_desktop_runtime.py` 找不到根目录 `desktop_runtime.py`

**影响**

服务、纸面账本和桌面运行时的基本导入路径不可用；部分安全控制虽然写在服务处理器中，但在模块导入失败时无法到达。

**建议**

1. 选择一个唯一的版本来源，并在 `invest/__init__.py`、打包元数据和服务响应之间统一使用。
2. 明确 `PaperLedger` 的归属：恢复兼容实现，或完成服务、测试、review 文档向新接口的迁移；不能同时保留两个含义不同的 `portfolio.py` 契约。
3. 决定桌面运行时是当前产品的一部分还是历史代码；若属于产品，应恢复并纳入包和测试，若属于历史代码，应从当前测试与发布链路移除。
4. 增加最小导入烟雾测试：`import invest.server`、创建服务对象、创建账本对象。

### INVEST-002 — P1：CI 没有安装测试和可选适配器依赖

`.github/workflows/tests.yml` 只执行 `python -m pip install -e .`，然后运行 unittest。当前测试直接导入 `pytest` 和 `playwright`；特征工程路径还需要 `stockstats` 的 `StockDataFrame`。这些并不在基础依赖中，导致 CI 出现：

- `ModuleNotFoundError: pytest`
- `ModuleNotFoundError: playwright`
- `ImportError: cannot import name 'StockDataFrame' from 'stockstats'`

**建议**

在 `pyproject.toml` 增加明确的 `test` 或 `dev` extra，至少包含测试实际需要的 pytest、Playwright 及对应浏览器安装步骤。对 stockstats 则要明确它是稳定的内置能力还是可选能力：前者修复 vendor 包导入契约，后者在能力探测失败时给出明确错误并让相关测试按能力标记跳过。CI 应安装同一个 extra，而不是依赖运行器预装包。

### INVEST-003 — P1：备份容量检查与发布完整性契约不一致

`invest/backup.py` 的 `export_backup` 对 `paper.sqlite` 和 `state.sqlite` 分别检查 `LIMIT`，但发布完整性测试要求数据库合计大小以及 manifest 也受限制。当前以下测试失败：

- `test_export_rejects_combined_database_limit`
- `test_export_limit_includes_manifest`

**影响**

单个数据库都小于限制时，两个文件的合计大小仍可能超过限制；压缩包还包含 `manifest.json`，因此导出结果可能超过设计的总量上限。该问题会削弱资源消耗保护，也说明导出接口的容量定义没有固定下来。

**建议**

统一定义限制是“所有未压缩成员总字节数”还是“最终 ZIP 字节数”。实现中应累计所有数据库原始字节数和 manifest 字节数，并在写入前后都校验上限；恢复端继续限制 ZIP 成员总量和单成员大小。补充边界测试：零数据库、恰好等于上限、数据库合计超限、manifest 导致超限、压缩比极端情况。

### INVEST-004 — P1：当前代码与 legacy 目录的测试发现边界未定义

仓库同时存在当前 `tests`、`legacy_research/tests` 和多个历史应用目录。两个测试树含有相同模块名，直接执行 pytest 会出现 import-file mismatch；当前测试又引用历史目录中的接口和文件。这不是单纯的 pytest 配置问题，而是代码所有权和迁移状态没有完成。

**建议**

先确定唯一权威测试树，再做以下之一：

- 将历史测试完整迁移到当前命名空间并删除重复副本；或
- 为历史测试建立明确包名，并在 pytest 配置中显式排除非当前产品的目录。

无论选择哪种方式，当前测试必须只验证当前主分支实际打包的代码，不能依赖工作区中的旧文件。

### INVEST-005 — P1：治理文档和实际主分支严重滞后

`governance/project_state.json` 仍记录仓库为 `Jvust2/Invest`，并引用 2026-09-25 的旧状态。`docs/CURRENT_STATE.md` 仍声称完整测试为 120 个、最新验证提交为 `c6ada...` 且 Actions 成功；`docs/HANDOFF.md` 仍描述旧 feature 分支和未合并的 PR。实际仓库为 `Jvust1/Invest`，当前 `main` 为 `8d9e6aa`，最新测试运行失败。

**影响**

审计、交接和发布人员可能根据过时的成功记录作出错误判断。文档不能作为当前质量门禁的证据。

**建议**

在修复测试后重新生成项目状态和交接文档，记录真实仓库、提交、测试命令、运行 ID、失败或通过状态。所有“已验证”声明必须带提交 SHA 和运行链接或运行 ID，并在每次主分支发布前更新。

### INVEST-006 — P2：导入面过宽，非核心能力容易拖垮核心模块

`invest/__init__.py` 聚合导入多个模块和适配器。当前环境中即使只想导入一个核心模块，也可能因为可选 provider、第三方适配器或 vendor 路径问题而失败。stockstats 的失败已经体现了这类耦合。

**建议**

把核心数据结构、引擎和服务接口与可选适配器分开；可选能力在调用点进行延迟导入，并返回包含安装或能力状态的明确错误。`import invest` 应只依赖基础运行时，不能要求所有可选研究工具都已安装。

### INVEST-007 — P2：stockstats vendor 路径与接口不匹配

`invest/features.py` 通过 `load_vendor("stockstats", module="stockstats")` 导入 `StockDataFrame`。当前 CI 解析到的 `stockstats` 模块不包含该名称，说明 vendor 目录结构、模块名或加载器约定至少有一处不一致。

**建议**

为 vendor 包增加独立导入测试，验证从干净 Python 环境加载、版本和 `StockDataFrame` 符号。若不再维护该 vendor，则移除隐式路径注入并把 stockstats 作为显式可选依赖；不要让导入一个特征函数影响其他核心模块。

### INVEST-008 — P2：桌面发布脚本在导入时读取环境和可选依赖

`tools/build_windows_delivery.py` 在模块导入阶段读取 `DESKTOP_APP`，测试清空环境后直接导入会得到 `KeyError`。`tools/desktop_browser_test.py` 在导入阶段读取 Playwright，基础安装环境会得到 `ModuleNotFoundError`。

**建议**

把环境变量读取和第三方导入放到 `main()` 或实际调用函数内；模块导入应保持安全。缺少可选依赖时返回带安装提示的可读错误。构建脚本需要单元测试时，应提供纯函数配置解析，不要在 import 时执行环境副作用。

### INVEST-009 — P2：portfolio/server/review 的接口所有权不一致

当前 `invest/portfolio.py` 是权重优化模块，`server.py` 仍使用 `PaperLedger`，`review.py` 又把 legacy PaperLedger 描述为执行模型。仓库同时存在新旧两种 portfolio 语义，升级边界没有写成版本化接口。

**建议**

为分配优化和纸面账本使用不同、稳定的模块名和类型名；服务层依赖接口协议而不是历史路径。迁移完成前，至少为兼容层增加弃用说明和契约测试，避免后续提交再次覆盖同名模块。

### INVEST-010 — P2：依赖版本范围较宽，缺少可复现锁定

基础依赖和可选 MLflow 依赖使用范围表达式，例如 `mlflow>=3`，仓库未提供完整锁文件或 hash 约束。对于金融研究和 CI，第三方小版本变化可能造成 API、数值结果或导入行为变化。

**建议**

为 CI 和发布构建生成约束文件或锁文件，记录 Python 版本、操作系统、依赖版本和 hash。定期更新依赖时单独运行完整矩阵，并把更新后的结果绑定到提交 SHA。

### INVEST-011 — P2：主分支没有把失败矩阵设置成明确门禁

GitHub Actions 有测试运行记录，但提交状态接口没有返回对应 status；分支信息显示 `protected: false`。因此目前不能确认 `main` 被强制要求通过四个测试矩阵后才能推进。

**建议**

配置主分支必需检查，名称与实际 workflow/job 一致；确认 push 到 `main` 和 pull request 都会报告状态。若仓库策略暂时不能启用保护，至少在发布脚本中拒绝失败或缺失的 CI 运行。

### INVEST-012 — P3：README 和发布文档没有覆盖当前恢复路径

README 介绍了研究和回测能力，但没有说明服务导入、桌面运行时、测试 extra、stockstats 能力和历史目录边界。发生当前这类模块漂移时，新维护者无法从文档判断哪些文件必须存在。

**建议**

补充“开发安装”“完整测试”“可选能力”“服务启动”“发布前检查”和“legacy 目录用途”章节，并让命令与 CI 完全一致。

## 5. 已确认的正向控制

- `invest.server` 设计为本机服务，限制本地地址，并校验 Host/Origin、CSRF token 和请求体大小。
- JSON 解析拒绝重复键和非标准数值；错误响应不会回显 token 或内部堆栈。
- Tushare token 通过环境变量或受控程序调用传入，HTTP 请求不接受公开 token 字段。
- `invest.engine` 使用 Decimal 金额和显式市场约束，处理 T+1、最小交易单位、涨跌停、滑点和手续费；回测流水线对持仓使用前一日值，避免明显的未来函数。
- 数据 provider 和 evaluation 校验采用 fail-closed 策略，要求真实调用证据、字段契约、市场边界和哈希绑定。
- workspace 使用 SQLite 事务、追加事件、内容哈希和不可变记录触发器；比较工具使用隔离子进程、超时和受限环境。
- 未发现 `shell=True`、明显的 `eval/exec`、pickle 反序列化或硬编码真实凭据。
- 产品边界是研究和纸面交易；当前未发现券商下单或公开服务的实现。

这些控制只能在相应模块成功导入并进入运行路径时生效，因此不能抵消当前的模块契约和 CI 阻塞问题。

## 6. 优先修复计划

### 阶段一：恢复可运行主线

1. 增加统一 `__version__` 来源并修复服务导入。
2. 决定 `PaperLedger` 的归属，修复 server、tests、review 和打包路径。
3. 恢复或移除根目录桌面运行时，确保测试只引用当前产品文件。
4. 增加测试 extra，修复 Playwright、pytest 和 stockstats 的安装/能力契约。
5. 在干净环境执行标准库测试和 pytest，直到没有导入错误。

### 阶段二：修复测试和发布契约

1. 按总未压缩成员大小实现 backup export 限制，并覆盖 manifest 边界。
2. 统一当前与 legacy 测试树，消除 pytest import-file mismatch。
3. 让 CI 使用与本地相同的测试入口，明确 optional tests 的标记和安装步骤。
4. 保留 compileall，并增加 `import invest.server`、桌面工具安全导入和打包 smoke test。

### 阶段三：治理和发布门禁

1. 更新 `project_state.json`、`CURRENT_STATE.md`、`HANDOFF.md`，绑定真实仓库、SHA、测试命令和运行 ID。
2. 为 `main` 设置必需 CI 检查，禁止失败或缺失状态进入发布流程。
3. 生成依赖约束/锁定文件，固定 Python 和浏览器测试环境。
4. 在四个矩阵任务全部通过后，重新做一次从干净环境开始的审计。

## 7. 建议的验收标准

发布前至少满足以下条件：

- `python -m unittest discover -s tests -v` 通过，或项目明确迁移到 pytest 并删除重复入口。
- `python -m pytest -q` 不再出现 import-file mismatch，且所有当前产品测试可收集。
- `python -m compileall -q invest integrations tools tests` 通过。
- `import invest.server`、创建 `PaperLedger`、加载 desktop runtime 和 stockstats 特征的 smoke test 在干净环境通过。
- backup 导出的数据库和 manifest 按同一总量规则受限，导入恢复测试通过。
- Ubuntu/Windows、Python 3.11/3.12 的 GitHub Actions 全部通过。
- 主分支保护要求上述检查，治理文档中的 SHA、运行 ID 和测试数量与实际一致。
- 审计重新确认没有真实凭据、未授权外联、公开 token 输入或券商下单路径。

## 8. 审计限制

本次审计基于当前主分支代码、仓库文档、GitHub Actions 记录和本地可复现测试。没有使用真实 Tushare 或其他市场数据凭据，没有执行真实交易，也没有验证外部 provider 的线上可用性。第三方可选依赖未全部安装，因此对未安装 provider 的运行时行为以代码和 CI 证据为准。报告中的风险等级表示工程和发布风险，不构成投资建议或生产环境安全认证。
