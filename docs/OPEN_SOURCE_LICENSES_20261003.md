# 高星与专业开源依赖：来源与许可核验（2026-10-03）

本页为 Invest 可选依赖的工程筛查记录，不是法律鉴定、投资建议或实时行情授权。客户端日期为 2026-10-03（Asia/Shanghai）；每次请求的实际 UTC 时间、URL、响应哈希及错误记录见 [机器可读证据](OPEN_SOURCE_EVIDENCE_20261003.json)。

## 接入原则

- 采用 **可选 Python 包依赖 + Invest 自有适配器**，不整仓复制、不把第三方源码改名据为己有；本文件不声明适配器已通过运行验收。
- 上游 LICENSE/NOTICE 及 wheel、二进制、传递依赖的许可义务继续有效；实际再分发前按交付形态复核，不把单一 GitHub 许可证标签扩展为所有组件的许可。
- **软件许可证 ≠ 行情、交易所、券商、API、训练数据的使用权**。数据来源、订阅条款、再分发权限需单独审查。
- 星数只反映观测时的人气，不能证明质量、安全、近期维护或收益。arch、ffn 为专业库，星数低于一万，未伪称为万星项目。
- 本快照固定默认分支 commit 仅用于溯源；不代表某个已安装版本必然由该 commit 构建。安装版本锁与测试报告另行核验。

## 实测概览

11 个仓库的身份、默认分支 commit 及该 commit 对应的许可文件均已通过 GitHub API 实取；11 个均未归档。许可解码字节均验证了 Git blob SHA-1，并计算 SHA-256。

| 上游 | 实测 Stars | GitHub 原始 SPDX | 文本工程判断 | 默认分支 commit | 最后推送 UTC |
|---|---:|---|---|---|---|
| [pola-rs/polars](https://github.com/pola-rs/polars) | 39,911 | `MIT` | MIT | [7a89bb7d5491](https://github.com/pola-rs/polars/commit/7a89bb7d5491e0ec34982d6d3af8f66f8f0c3272) | 2026-10-02T16:06:07Z |
| [duckdb/duckdb](https://github.com/duckdb/duckdb) | 41,872 | `MIT` | MIT | [20b5e848c64c](https://github.com/duckdb/duckdb/commit/20b5e848c64c5c096994cdd33f1d661eb5e41b6b) | 2026-10-02T15:58:51Z |
| [apache/arrow](https://github.com/apache/arrow) | 17,167 | `Apache-2.0` | Apache-2.0 with bundled third-party license notices | [676dd43c5fef](https://github.com/apache/arrow/commit/676dd43c5fef2dbb3c42e7b03b43ca6f952bd405) | 2026-10-02T13:16:47Z |
| [statsmodels/statsmodels](https://github.com/statsmodels/statsmodels) | 11,669 | `BSD-3-Clause` | BSD-3-Clause | [38965b6f33cf](https://github.com/statsmodels/statsmodels/commit/38965b6f33cff021b1232b537dbec0b532258b62) | 2026-10-02T15:11:44Z |
| [bashtage/arch](https://github.com/bashtage/arch) | 1,583 | `NOASSERTION` | Custom observed permissive text; SPDX not asserted | [88ffcf87042e](https://github.com/bashtage/arch/commit/88ffcf87042ed5d4adf48bac41b144bc90b287a2) | 2026-09-27T08:00:31Z |
| [scipy/scipy](https://github.com/scipy/scipy) | 15,071 | `BSD-3-Clause` | BSD-3-Clause | [0a50dfe076cb](https://github.com/scipy/scipy/commit/0a50dfe076cb866f93fdb05f3d78f51b6a64040a) | 2026-10-02T12:07:09Z |
| [bukosabino/ta](https://github.com/bukosabino/ta) | 5,228 | `MIT` | MIT | [a890410710a6](https://github.com/bukosabino/ta/commit/a890410710a6e483c9ba08da7f3dd5089e4b9dff) | 2026-03-18T13:04:55Z |
| [pmorissette/ffn](https://github.com/pmorissette/ffn) | 2,679 | `MIT` | MIT | [1312e9712331](https://github.com/pmorissette/ffn/commit/1312e971233198c8d5a72daf79259e61b88ed0d4) | 2026-10-01T21:29:17Z |
| [networkx/networkx](https://github.com/networkx/networkx) | 17,307 | `NOASSERTION` | Text explicitly states BSD-3-Clause | [31b74e96903d](https://github.com/networkx/networkx/commit/31b74e96903d7f873b30c8ff36d71a4c9252b107) | 2026-10-02T01:20:09Z |
| [plotly/plotly.py](https://github.com/plotly/plotly.py) | 18,817 | `MIT` | MIT | [d586d225b857](https://github.com/plotly/plotly.py/commit/d586d225b8577fa3a4ff8954bdd47ef3b9cc0c07) | 2026-10-01T07:39:55Z |
| [scikit-learn/scikit-learn](https://github.com/scikit-learn/scikit-learn) | 67,451 | `BSD-3-Clause` | BSD-3-Clause | [2cc5fc985667](https://github.com/scikit-learn/scikit-learn/commit/2cc5fc9856675eb112bbd6640404027195741710) | 2026-10-02T13:23:25Z |

## 许可文件与注意事项

### pola-rs/polars
- 许可原文：[LICENSE](https://github.com/pola-rs/polars/blob/7a89bb7d5491e0ec34982d6d3af8f66f8f0c3272/LICENSE)（固定 commit）。
- 文件 SHA-256：`8296022372dc83cc8ef234b3d4889ef8f8b1779754a78bebf13d2c5178a6b4c4`；1,145 字节。
- 工程筛查：Original copyright and permission notices must be retained in copies or substantial portions; includes Ritchie Vink and NVIDIA notices.

### duckdb/duckdb
- 许可原文：[LICENSE](https://github.com/duckdb/duckdb/blob/20b5e848c64c5c096994cdd33f1d661eb5e41b6b/LICENSE)（固定 commit）。
- 文件 SHA-256：`075c33400ffcb0c586dd106a029d3e733e9da3693f8fcb9cebfc651c8a2f14e3`；1,072 字节。
- 工程筛查：Original copyright and permission notices must be retained in copies or substantial portions.

### apache/arrow
- 许可原文：[LICENSE.txt](https://github.com/apache/arrow/blob/676dd43c5fef2dbb3c42e7b03b43ca6f952bd405/LICENSE.txt)（固定 commit）。
- 文件 SHA-256：`cd03925a27219d326d622609fbcae6567279af8b8885c33d5969a9e4ef5d7525`；110,383 字节。
- 工程筛查：Top-level text contains Apache-2.0 plus a large collection of third-party notices; do not relabel every bundled component Apache-only. Preserve the distribution-specific LICENSE and NOTICE files; inspect actual wheel/binary contents before redistribution.

### statsmodels/statsmodels
- 许可原文：[LICENSE.txt](https://github.com/statsmodels/statsmodels/blob/38965b6f33cff021b1232b537dbec0b532258b62/LICENSE.txt)（固定 commit）。
- 文件 SHA-256：`1ca78e1dec9dcebc55f3b96a862317f23e76422c5fc943568d955aad1f6b5fad`；1,636 字节。
- 工程筛查：Retain copyright, conditions and disclaimer for source/binary redistribution; no unauthorized contributor endorsement.

### bashtage/arch
- 许可原文：[LICENSE.md](https://github.com/bashtage/arch/blob/88ffcf87042ed5d4adf48bac41b144bc90b287a2/LICENSE.md)（固定 commit）。
- 文件 SHA-256：`c6e622bd89db4e13315f4e91605ff96fcbb9012d78ee74e429855870b203eed6`；1,660 字节。
- 工程筛查：GitHub returns NOASSERTION. The observed file grants use/copy/modification/distribution with source and binary notice-retention and non-endorsement conditions. Manual license review remains required; no replacement SPDX guess is made.

### scipy/scipy
- 许可原文：[LICENSE.txt](https://github.com/scipy/scipy/blob/0a50dfe076cb866f93fdb05f3d78f51b6a64040a/LICENSE.txt)（固定 commit）。
- 文件 SHA-256：`221e59f5e910fd7f94e44f0dac77436a11338c285c6346232e4a850a50da0e94`；1,531 字节。
- 工程筛查：Retain copyright, conditions and disclaimer; no unauthorized endorsement. Built distributions may include separately licensed numerical libraries; inspect distribution notices.

### bukosabino/ta
- 许可原文：[LICENSE](https://github.com/bukosabino/ta/blob/a890410710a6e483c9ba08da7f3dd5089e4b9dff/LICENSE)（固定 commit）。
- 文件 SHA-256：`f4be1f16528123c4f41c55b91d52b7c07c12022f6acd75a7c4b3e461434600f0`；1,096 字节。
- 工程筛查：Original copyright and permission notices must be retained in copies or substantial portions; data-provider and trading rights are separate.

### pmorissette/ffn
- 许可原文：[LICENSE](https://github.com/pmorissette/ffn/blob/1312e971233198c8d5a72daf79259e61b88ed0d4/LICENSE)（固定 commit）。
- 文件 SHA-256：`8711471566d722d55eca3f09196f342b2ee2960616e68127ec2a17b39ff99949`；1,086 字节。
- 工程筛查：Original copyright and permission notices must be retained in copies or substantial portions; do not infer data-source permission from the software license.

### networkx/networkx
- 许可原文：[LICENSE.txt](https://github.com/networkx/networkx/blob/31b74e96903d7f873b30c8ff36d71a4c9252b107/LICENSE.txt)（固定 commit）。
- 文件 SHA-256：`6025f323ea29dc2f0ee0abd9523bf910186f55b0e148e6ebf646c55566278e2e`；1,763 字节。
- 工程筛查：GitHub returns NOASSERTION; the observed top-level text explicitly identifies 3-clause BSD and contains those conditions. Preserve both the raw GitHub label and this text assessment; retain notices and avoid unauthorized endorsement.

### plotly/plotly.py
- 许可原文：[LICENSE.txt](https://github.com/plotly/plotly.py/blob/d586d225b8577fa3a4ff8954bdd47ef3b9cc0c07/LICENSE.txt)（固定 commit）。
- 文件 SHA-256：`ba712274f8336a5f0828c8e2bf639ab8a632c623800a35f96c8b0a67b5f2ab40`；1,086 字节。
- 工程筛查：Original copyright and permission notices must be retained; hosted services, integrations and data access are separate from this repository license.

### scikit-learn/scikit-learn
- 许可原文：[COPYING](https://github.com/scikit-learn/scikit-learn/blob/2cc5fc9856675eb112bbd6640404027195741710/COPYING)（固定 commit）。
- 文件 SHA-256：`50d6a9d340f19ab355609917993114daf5f47e3161067bcf34955bbd05cd9cb0`；1,532 字节。
- 工程筛查：Retain copyright, conditions and disclaimer for source/binary redistribution; no unauthorized endorsement. Models and training data need separate provenance review.

## 需要特别保留的边界

- **arch：** GitHub 原始标签为 `NOASSERTION`。已读原文包含较宽松的使用、修改与分发授予，同时要求源/二进制保留版权、条款和免责声明，并限制未经许可的背书；这里不擅自替换为某个 SPDX，保留人工许可复核事项。
- **NetworkX：** GitHub 同样返回 `NOASSERTION`，但原文明确声明 3-clause BSD 并列出对应条件。保留 GitHub 原值与文本判断两个字段，不混为一谈。
- **Arrow：** `LICENSE.txt` 为 110,383 字节，包含 Apache-2.0 与多个第三方许可/通知；GPLv2 字样出现于 LLVM 例外条款上下文，不能据此直接把 Arrow 宣称为 GPL，也不能据单一 API 标签忽略第三方条款。已单独读取并哈希固定 commit 的 NOTICE.txt，详见 JSON。
- **维护风险：** `ta` 本次最后推送时间为 2026-03-18，未归档不等于活跃维护。安装前仍需检查当前发布版本、依赖兼容性及安全公告。

## 实际安装版本：与默认分支证据分离

另见 [本机发行包证据](OPEN_SOURCE_RUNTIME_20261003.json)。通过 `importlib.metadata` 读取实际运行时的 METADATA、WHEEL、INSTALLER、RECORD，不导入上游运行时代码、不下载或安装软件；逐个读取对应许可证/通知文件并记录相对路径、字节数、SHA-256，且校验 RECORD 中已有的文件哈希。

| 发行包 | 本机实际版本 | Requires-Python |
|---|---|---|
| polars | 1.44.2 | >=3.10 |
| duckdb | 1.5.6 | >=3.10.0 |
| pyarrow | 25.0.1 | >=3.10 |
| statsmodels | 0.15.0 | >=3.10 |
| arch | 8.0.0 | >=3.10 |
| scipy | 1.18.1 | >=3.12 |
| ta | 0.11.0 | 元数据未声明 |
| ffn | 1.2.2 | >=3.9 |
| networkx | 3.7 | !=3.14.1,>=3.12 |
| plotly | 7.1.0 | >=3.8 |
| scikit-learn | 1.9.1 | >=3.11 |

- **不混同来源：** 这 11 个包均未带 `direct_url.json`，本证据不能确立下载索引、原始 wheel 压缩包哈希或构建 commit。METADATA 的项目链接也不构成来源真实性证明。这里的运行时为 Python 3.12，不宣称同一组版本适用于 Python 3.11。
- **许可原文存在差异：** duckdb、pyarrow、statsmodels、arch、scipy、scikit-learn 的已安装顶层许可文件 SHA-256 与先前默认分支快照不同，已如实标记；没有为了对齐而覆盖任何一方。polars、ffn、networkx、plotly 的对应文件字节一致，也只能说明许可文件一致，不能证明构建来源 commit 一致。
- **arch 的两种元数据：** 已安装 8.0.0 的 METADATA 声明 `License-Expression: NCSA`；此前 GitHub 默认分支 API 则给出 `NOASSERTION`。两者均按实际来源保留，不相互替换。
- **ta 的缺口：** 0.11.0 的 RECORD 未列出独立 LICENSE/NOTICE 文件；保留其许可元数据并明确标记缺失，不把元数据标签冒充完整许可正文。若要再分发该包，需另行补齐该具体版本的许可材料。
- **范围限制：** 该证据不是环境全量 SBOM，也不是签名来源证明；RECORD 一致性是本地字节与本地记录的一致性，不是发布者真实性保证。传递依赖与具体二进制交付仍需单独核验。

## 已观察结果与未声称事项

元数据收集使用公开 GitHub API，最多 3 路并行；主体 33 次请求均成功。最初浏览工具无法打开 API URL 的错误已记录，改用真实 HTTP 请求后完成。另有 4 次许可证原文独立复读与 Arrow NOTICE 请求均成功，合计 37 次 HTTP 请求。本审查没有安装依赖、运行未知上游代码、改动账户权限、连接券商或执行交易，也没有作全依赖链或法律合规的最终保证。
