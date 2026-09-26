# 工作台API合同 v1

所有接口仅接受本机Host；跨站Origin/Fetch-Site被拒绝。POST只接受JSON、唯一Content-Length、最大2MiB以及 `/api/config` 返回的 `X-Invest-CSRF`。错误不会静默写入成功记录。

| 方法与路径 | 输入 | 输出 |
|---|---|---|
| GET /api/workbench/status | 无 | 能力清单与未通过的现实验收，不返回秘密 |
| GET /api/workbench/documents?kind=study | kind：study/receipt/review/facts | 最近100份摘要；上限明确返回 |
| GET /api/workbench/document?id=... | 文档SHA256 ID | 完整不可变记录，可下载JSON |
| POST /api/workbench/receipt | dataset_id，可选declaration | 再验证后的来源/执行回执 |
| POST /api/workbench/study | dataset_id、specification | 完整探索性比较，不打开holdout |
| POST /api/workbench/reviews | name、initial_cash、client_key、manual_record_acknowledged=true | 人工复盘账户文档 |
| GET /api/workbench/review?id=... | 账户文档ID | 配置、状态、完整事件链与链头 |
| POST /api/workbench/event | review_id、event_key、event | 验证追加后的状态与链 |
| POST /api/workbench/facts | enabled=true、bundle | 独立PIT事实包 |
| POST /api/workbench/as-of | enabled、bundle_id、symbol、as_of | 查询时点可见的事实；关闭时不读取包 |
| POST /api/private-backup | confirm_private_export=true | 含私人状态的完整ZIP |

## 有界实验

```json
{"dataset_id":"<64位数据ID>","specification":{"symbol":"600000.SH","initial_cash":100000,"cost_model_acknowledged":true,"candidates":[{"name":"MA 5/20","fast":5,"slow":20},{"name":"MA 10/30","fast":10,"slow":30}]}}
```

允许1–3个候选。每个候选×三段×三种成本；默认18项，最大27项。一个服务器同时只允许一个新比较任务，正在运行时返回409。失败解除任务锁，并保留原记录。相同结果按内容去重。

## 人工事件

```json
{"review_id":"<64位账户ID>","event_key":"由客户端生成并在失败重试时复用的唯一键","event":{"type":"DEPOSIT","occurred_at":"2024-01-02T16:00:00+08:00","source":"本人核对的历史记录","amount":"1000.00"}}
```

事件公共字段严格为type/occurred_at/source加上该类型规定的字段，未知字段拒绝，避免默默保存账户密码等额外内容。金额传字符串可避免客户端浮点误差，最多到分。发生时间规范化为UTC；沪深交易日的T+1比较使用UTC+08:00日期。

MARK示例：`{"type":"MARK","occurred_at":"2024-01-03T16:00:00+08:00","source":"自有估值记录","prices":{"600000.SH":"10.50"}}`。

## PIT事实包

```json
{"source_name":"人工合成示例","source_text":"虚构利润首次为10，后来修订为8。","license_note":"人工合成，不是真实公告","facts":[{"symbol":"600000.SH","metric":"net_profit","period_end":"2023-12-31","available_at":"2024-03-01T16:00:00+08:00","revision":1,"value":"10","unit":"CNY million"},{"symbol":"600000.SH","metric":"net_profit","period_end":"2023-12-31","available_at":"2024-05-01T16:00:00+08:00","revision":2,"value":"8","unit":"CNY million"}]}
```

2024-04-01查询只能得到版本1，2024-06-01可见版本2。时区必须明确，任何“事后知道”的修订不会自动改写过去的查询。

## 持久化与兼容

新表为growth_documents/growth_events，均在原state.sqlite；不修改旧表的数据。文档ID取规范化kind+payload的SHA256，外层服务器记录时间不进入业务身份。事件链包含时间记录和上一哈希。每次读回校验内容身份。

核心服务器和API没有执行任意用户Python插件、导入任意路径、向任意URL发起请求或券商交易的入口。PIT扩展是严格数据合同，而不是远程代码插件。
