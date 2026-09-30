# 上海市场双日历核验

`invest.calendar_crosscheck.crosscheck_shanghai_sessions` 对同一区间调用 `exchange_calendars` 的 `XSHG` 与 `pandas_market_calendars` 的 `SSE`，保留各自的版本、日期差集和输入观测日期。调用方显式给出 `start`、`end`、`as_of`、递增无重复的 `observed_dates`、`data_scope="PUBLIC_RESEARCH_ONLY"`。日期范围至多 366 天且不得越过方案日。

状态包含 `MATCHED_SESSIONS`、`CALENDAR_DISAGREEMENT`、`OBSERVATIONS_INCOMPLETE`、`OBSERVATIONS_OUTSIDE_SESSIONS` 与 `NO_COMMON_CALENDAR_COVERAGE`。两个日历不同会明确返回差异，不能由一个覆盖另一个；缺失行情观测只显示缺口，不能据此推定个券停牌。即使日历一致，也未核实证券停牌、实际盘口、公司行动、交易规则有效期、行情许可或可执行性。

安装可选依赖：`python -m pip install '.[calendars]'`。真实库合同测试在 Ubuntu/Python 3.11 运行；主测试矩阵使用独立桩验证分歧和缺日行为，无需安装日历依赖。

接口依据：[exchange_calendars 项目说明](https://github.com/gerrymanoim/exchange_calendars) 与 [pandas_market_calendars SSE 列表](https://pandas-market-calendars.readthedocs.io/en/latest/calendars.html)。这两个日历是独立软件结果，不能替代交易所的正式历史公告或证券级交易状态。
