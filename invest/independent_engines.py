"""Isolated synthetic-data contracts for independent backtest engines."""
from __future__ import annotations

from importlib.metadata import version


def hikyuu_synthetic_contract() -> dict:
    """Exercise temporary in-memory bars and an explicit ETF fee primitive."""
    try:
        import hikyuu as hku
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("缺少 Hikyuu；请安装 independent-hikyuu 额外依赖") from exc

    frame = pd.DataFrame({
        "datetime": pd.to_datetime(["2025-01-02", "2025-01-03", "2025-01-06"]),
        "open": [1.90, 1.92, 1.88],
        "high": [1.91, 1.94, 1.90],
        "low": [1.89, 1.91, 1.86],
        "close": [1.90, 1.93, 1.87],
        "amount": [190000.0, 193000.0, 187000.0],
        "volume": [100000.0, 100000.0, 100000.0],
    })
    stock = hku.Stock("TMP", "000001", "Invest synthetic")
    stock.set_kdata_from_df(frame)
    kdata = stock.get_kdata(hku.Query(0, len(frame)))
    if len(kdata) != len(frame):
        raise ValueError("Hikyuu 临时 K 线注入数量不一致")
    closes = [float(row.close) for row in kdata]
    if closes != [1.90, 1.93, 1.87]:
        raise ValueError("Hikyuu 临时 K 线读取值不一致")

    fee_model = hku.TC_FixedETF(commission=0.00025, lowest_commission=5.0)
    buy_cost = fee_model.get_buy_cost(hku.Datetime("2025-01-02"), stock, 1.90, 200)
    if abs(float(buy_cost.commission) - 5.0) > 1e-12:
        raise ValueError("Hikyuu ETF 最低佣金合同变化")
    if abs(float(buy_cost.total) - 5.0) > 1e-12:
        raise ValueError("Hikyuu ETF 买入总费用合同变化")
    return {
        "schema": "invest-hikyuu-synthetic-contract-v1",
        "status": "SCENARIO_ONLY",
        "backend": "hikyuu",
        "backend_version": version("hikyuu"),
        "bar_source": "in_memory_dataframe",
        "sessions": len(kdata),
        "close_values": closes,
        "fee_probe": {
            "asset_class": "ETF",
            "price_cny": 1.90,
            "quantity_shares": 200,
            "commission_rate": 0.00025,
            "minimum_commission_cny": 5.0,
            "backend_commission_cny": float(buy_cost.commission),
            "backend_total_cost_cny": float(buy_cost.total),
        },
        "limitations": [
            "只验证临时内存 K 线和费用原语；没有调用 Hikyuu 行情下载、实盘代理或用户本地数据库。Hikyuu 首次初始化可能自行拉取其 hub 策略仓库，这是框架初始化副作用，不是行情输入。",
            "未把 Hikyuu 的系统信号/成交时序等价为 Invest；事件驱动策略回放仍是后续 gate。",
        ],
    }


def zipline_synthetic_contract() -> dict:
    """Exercise Shanghai calendar lookup and isolated CSV bundle registration."""
    try:
        import pandas as pd
        from zipline.data.bundles import bundles, register, unregister
        from zipline.data.bundles.csvdir import csvdir_equities
        from zipline.utils.calendar_utils import get_calendar
    except ImportError as exc:
        raise RuntimeError("缺少 Zipline Reloaded；请安装 independent-zipline 额外依赖") from exc

    calendar = get_calendar("XSHG")
    sessions = calendar.sessions_in_range(pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-10"))
    if len(sessions) < 5:
        raise ValueError("Zipline XSHG 日历返回异常")
    name = "invest-synthetic-contract"
    if name in bundles:
        unregister(name)
    register(
        name,
        csvdir_equities(["daily"], "/tmp/invest-synthetic-contract"),
        calendar_name="XSHG",
        start_session=sessions[0],
        end_session=sessions[-1],
    )
    try:
        if name not in bundles:
            raise ValueError("Zipline 合成 bundle 未注册")
        bundle = bundles[name]
        registered_calendar = getattr(bundle, "calendar_name", None)
        if registered_calendar != "XSHG":
            raise ValueError("Zipline 合成 bundle 日历绑定异常")
    finally:
        unregister(name)

    return {
        "schema": "invest-zipline-synthetic-contract-v1",
        "status": "SCENARIO_ONLY",
        "backend": "zipline-reloaded",
        "backend_version": version("zipline-reloaded"),
        "calendar": "XSHG",
        "session_count_probe": len(sessions),
        "bundle_registration": "REGISTERED_AND_REMOVED_WITHOUT_INGEST",
        "execution_model": "NOT_YET_BOUND_TO_INVEST_FEES_OR_LOT_RULES",
        "limitations": [
            "本合同只验证 XSHG 日历与自定义 CSV bundle 注册生命周期；尚未 ingest 或运行事件驱动策略。",
            "Zipline 默认佣金/滑点模型不等同于 Invest 的 A 股/ETF 最低佣金、税费、整手和费用取整规则，必须单独适配后才能比较成交结果。",
        ],
    }
