"""Deterministic, cash-only daily-bar research and paper execution model.

This is an explicitly conservative educational model, not a broker interface.
Financial balances use Decimal cents; JSON results contain ordinary numbers.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP

from .data import verify_dataset_identity


ENGINE_VERSION = "invest-cash-mainboard-v1"
CENT = Decimal("0.01")
DEFAULT_PARAMETERS = {
    "initial_cash": 100000,
    "fast": 5,
    "slow": 20,
    "commission_rate": 0.0003,
    "min_commission": 5,
    "stamp_tax_rate": 0.0005,
    "transfer_fee_rate": 0.00001,
    "slippage_bps": 5,
    "cost_model_acknowledged": False,
}


def _decimal(value, name="数值") -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{name}必须是有限数值")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(f"{name}必须是有限数值") from None
    if not result.is_finite() or abs(result) > Decimal("1e18") or (result and result.adjusted() < -18):
        raise ValueError(f"{name}必须是有限且合理的数值")
    return result


def _money(value) -> Decimal:
    return _decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def _integer(value, name, minimum=0, maximum=10**12) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name}必须是 {minimum}–{maximum} 范围内的整数")
    return value


def _day(value, name="日期") -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError(f"{name}必须为 YYYY-MM-DD")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{name}无效") from None
    return value


def _symbol(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(
        r"(?:(?:600|601|603|605)\d{3}\.SH|(?:000|001|002|003)\d{3}\.SZ)", value
    ):
        raise ValueError("仅支持沪深主板普通股票代码；ETF、科创板、创业板和北交所尚未支持")
    return value


def validate_parameters(params: dict, *, require_strategy: bool = False) -> dict:
    """Normalize a fixed, user-acknowledged illustrative cost scenario."""
    if not isinstance(params, dict):
        raise ValueError("参数必须是对象")
    result = {**DEFAULT_PARAMETERS, **params}
    if result.get("cost_model_acknowledged") is not True:
        raise ValueError("请确认固定演示费率；它不是券商实际费率或自动还原的历史费率")
    cash = _decimal(result["initial_cash"], "初始资金")
    if not Decimal("0.01") <= cash <= Decimal("1000000000") or cash != _money(cash):
        raise ValueError("初始资金须为 0.01–10亿元，最多两位小数")
    result["initial_cash"] = float(cash)
    for key, upper in (
        ("commission_rate", "0.02"), ("stamp_tax_rate", "0.02"),
        ("transfer_fee_rate", "0.02"), ("min_commission", "1000"),
        ("slippage_bps", "1000"),
    ):
        value = _decimal(result[key], key)
        if value < 0 or value > Decimal(upper):
            raise ValueError(f"{key}超出允许范围 0–{upper}")
        if key == "min_commission" and value != _money(value):
            raise ValueError("最低佣金最多两位小数")
        result[key] = float(value)
    if require_strategy:
        result["symbol"] = _symbol(result.get("symbol"))
        result["fast"] = _integer(result["fast"], "短均线", 1, 499)
        result["slow"] = _integer(result["slow"], "长均线", 2, 500)
        if result["fast"] >= result["slow"]:
            raise ValueError("短均线周期必须小于长均线周期")
        for key in ("start_date", "end_date"):
            if result.get(key) not in (None, ""):
                result[key] = _day(result[key], key)
            else:
                result[key] = None
        if result["start_date"] and result["end_date"] and result["start_date"] > result["end_date"]:
            raise ValueError("开始日期不能晚于结束日期")
    return result


def validate_execution_bar(bar: dict) -> None:
    """Fail closed on unknown daily execution facts; no board-limit guessing."""
    if not isinstance(bar, dict):
        raise ValueError("行情记录必须是对象")
    _symbol(bar.get("symbol"))
    _day(bar.get("date"))
    prices = {}
    for key in ("open", "high", "low", "close", "up_limit", "down_limit"):
        value = _decimal(bar.get(key), key)
        if value <= 0 or value > Decimal("1000000") or value != _money(value):
            raise ValueError(f"{key}缺失或不是有效的分位原始价格")
        prices[key] = value
    if not (prices["low"] <= prices["open"] <= prices["high"] and
            prices["low"] <= prices["close"] <= prices["high"]):
        raise ValueError("OHLC高低价格范围不一致")
    if not (prices["down_limit"] <= prices["low"] <= prices["high"] <= prices["up_limit"]):
        raise ValueError("行情超出已声明的当日涨跌停范围")
    volume = _decimal(bar.get("volume_shares"), "成交股数")
    if volume < 0 or volume > Decimal("1000000000000") or volume != volume.to_integral_value():
        raise ValueError("成交量必须是非负整数股数")
    if type(bar.get("suspended")) is not bool:
        raise ValueError("停牌状态未知，禁止执行")
    if bar.get("corporate_action") is not False:
        raise ValueError("公司行动未知或已发生，当前模型不支持执行")
    if _decimal(bar.get("adj_factor"), "复权因子") <= 0:
        raise ValueError("复权因子必须明确且为正数")


def validate_market_window(dataset: dict, symbol: str, start_date=None, end_date=None) -> list[dict]:
    """Validate inclusive symbol history, official/declarative calendar and actions.

    Identity/provenance hashes must additionally be checked by persistent ledgers.
    The supplied dataset is never mutated. Bars outside this window are unused.
    """
    _symbol(symbol)
    if not isinstance(dataset, dict):
        raise ValueError("数据集必须是对象")
    verify_dataset_identity(dataset)
    meta = dataset.get("meta", {})
    for key, expected in (("currency", "CNY"), ("price_basis", "raw"), ("volume_unit", "shares")):
        if meta.get(key) != expected:
            raise ValueError("仅支持已明确声明人民币、原始价格和股数单位的数据")
    if not isinstance(meta.get("source"), str) or not meta["source"].strip():
        raise ValueError("缺少数据来源")
    if not isinstance(meta.get("calendar_source"), str) or not meta["calendar_source"].strip():
        raise ValueError("缺少交易日历来源")
    if start_date is not None:
        _day(start_date, "开始日期")
    if end_date is not None:
        _day(end_date, "结束日期")
    if start_date and end_date and start_date > end_date:
        raise ValueError("开始日期不能晚于结束日期")
    calendar = dataset.get("calendar")
    if not isinstance(calendar, list) or not calendar:
        raise ValueError("缺少明确交易日历，禁止回测/模拟成交")
    days = [_day(day, "交易日历日期") for day in calendar]
    if days != sorted(set(days)):
        raise ValueError("交易日历必须递增且无重复")
    raw = dataset.get("bars")
    if not isinstance(raw, list):
        raise ValueError("缺少行情记录")
    rows = []
    for bar in raw:
        if not isinstance(bar, dict):
            raise ValueError("行情记录格式无效")
        if bar.get("symbol") == symbol:
            day = _day(bar.get("date"))
            if (start_date is None or day >= start_date) and (end_date is None or day <= end_date):
                rows.append(bar)
    if not rows:
        raise ValueError("所选股票和日期范围没有行情")
    row_days = [bar["date"] for bar in rows]
    if row_days != sorted(set(row_days)):
        raise ValueError("行情日期必须递增且无重复")
    expected = [day for day in days if (start_date or row_days[0]) <= day <= (end_date or row_days[-1])]
    if expected != row_days:
        raise ValueError("行情与交易日历不一致或缺交易日；停牌日也必须显式提供记录")
    factor = None
    for bar in rows:
        validate_execution_bar(bar)
        current = _decimal(bar["adj_factor"])
        if factor is None:
            factor = current
        elif factor != current:
            raise ValueError("区间存在复权因子变化，当前模型不能模拟公司行动")
    return rows


def _fees(price: Decimal, quantity: int, side: str, params: dict) -> dict:
    gross = _money(price * quantity)
    commission = _money(max(gross * _decimal(params["commission_rate"]), _decimal(params["min_commission"])))
    stamp = _money(gross * _decimal(params["stamp_tax_rate"])) if side == "SELL" else Decimal("0.00")
    transfer = _money(gross * _decimal(params["transfer_fee_rate"]))
    return {"gross": gross, "commission": commission, "stamp_tax": stamp,
            "transfer_fee": transfer, "fees": commission + stamp + transfer}


def _execution_price(bar: dict, side: str, params: dict) -> Decimal:
    if bar["suspended"]:
        raise ValueError("停牌，当日订单失效")
    if _decimal(bar["volume_shares"]) == 0:
        raise ValueError("零成交量，当日订单失效")
    opening = _decimal(bar["open"])
    if side == "BUY" and opening >= _decimal(bar["up_limit"]):
        raise ValueError("开盘涨停，买入订单失效")
    if side == "SELL" and opening <= _decimal(bar["down_limit"]):
        raise ValueError("开盘跌停，卖出订单失效")
    adjustment = _decimal(params["slippage_bps"]) / 10000
    price = (opening * (1 + adjustment if side == "BUY" else 1 - adjustment)).quantize(
        CENT, rounding=ROUND_CEILING if side == "BUY" else ROUND_FLOOR
    )
    if not max(_decimal(bar["low"]), _decimal(bar["down_limit"])) <= price <= min(
        _decimal(bar["high"]), _decimal(bar["up_limit"])
    ):
        raise ValueError("滑点后价格超出当日OHLC或涨跌停范围，订单失效")
    return price


def execute_order(bar: dict, side: str, quantity: int, cash, available_shares: int, params: dict) -> dict:
    """Execute one day order; caller supplies T+1-eligible sell inventory.

    Returns Decimal monetary fields. Every fee component is rounded to cents
    using ROUND_HALF_UP; price slippage rounds against the trader to the tick.
    """
    normalized = validate_parameters(params)
    validate_execution_bar(bar)
    if side not in ("BUY", "SELL"):
        raise ValueError("买卖方向必须为 BUY 或 SELL")
    quantity = _integer(quantity, "股数", 1)
    available_shares = _integer(available_shares, "T+1可卖股数", 0)
    balance = _decimal(cash, "现金")
    if balance < 0 or balance != _money(balance):
        raise ValueError("现金必须非负且精确到分")
    if side == "BUY" and quantity % 100:
        raise ValueError("买入股数必须是100股的整数倍")
    if side == "SELL" and quantity > available_shares:
        raise ValueError("超过T+1可卖股数或持仓不足")
    if side == "SELL" and quantity % 100 and quantity != available_shares:
        raise ValueError("零股只能一次卖出全部可卖零股持仓")
    price = _execution_price(bar, side, normalized)
    if quantity > _decimal(bar["volume_shares"]):
        raise ValueError("订单股数超过当日总成交股数，订单失效")
    result = _fees(price, quantity, side, normalized)
    cash_after = balance - result["gross"] - result["fees"] if side == "BUY" else balance + result["gross"] - result["fees"]
    if cash_after < 0:
        raise ValueError("现金不足以支付成交金额和全部费用")
    return {**result, "price": price, "quantity": quantity, "side": side,
            "date": bar["date"], "cash_after": _money(cash_after)}


def _buy_quantity(bar: dict, cash: Decimal, params: dict) -> int:
    price = _execution_price(bar, "BUY", params)
    low, high = 0, int(cash // (price * 100))
    while low < high:
        middle = (low + high + 1) // 2
        fees = _fees(price, middle * 100, "BUY", params)
        if fees["gross"] + fees["fees"] <= cash:
            low = middle
        else:
            high = middle - 1
    return low * 100


def _drawdown(values: list[Decimal], initial: Decimal | None = None) -> float:
    if not values:
        return 0.0
    peak = initial if initial is not None else values[0]
    maximum = Decimal(0)
    for value in values:
        peak = max(peak, value)
        if peak > 0:
            maximum = max(maximum, (peak - value) / peak)
    return float(maximum)


def _json_money(result: dict) -> dict:
    return {key: float(value) if isinstance(value, Decimal) else value for key, value in result.items()}


def backtest(dataset: dict, params: dict) -> dict:
    """Daily MA target; signal at t close, day-order at next session open."""
    p = validate_parameters(params, require_strategy=True)
    symbol = p["symbol"]
    if not isinstance(dataset, dict) or not isinstance(dataset.get("bars"), list):
        raise ValueError("数据集格式无效")
    verify_dataset_identity(dataset)
    raw = [bar for bar in dataset["bars"] if isinstance(bar, dict) and bar.get("symbol") == symbol]
    if not raw:
        raise ValueError("所选股票没有行情")
    dates = [_day(bar.get("date")) for bar in raw]
    if dates != sorted(set(dates)):
        raise ValueError("行情日期必须递增且无重复")
    end = p["end_date"] or dates[-1]
    within = [bar for bar in raw if bar["date"] <= end]
    requested = p["start_date"] or dates[0]
    first = next((i for i, bar in enumerate(within) if bar["date"] >= requested), len(within))
    evaluation_start = max(first, p["slow"])
    if evaluation_start >= len(within):
        raise ValueError("所选区间及前置数据不足：至少需要长均线周期的预热记录和1个执行日")
    start = within[evaluation_start - p["slow"]]["date"]
    rows = validate_market_window(dataset, symbol, start, end)
    slow = p["slow"]
    initial = _money(p["initial_cash"])
    cash = benchmark_cash = initial
    shares = benchmark_shares = 0
    benchmark_bought = False
    trades, rejected, benchmark_trades, benchmark_rejected, curve = [], [], [], [], []
    values = []
    total_fees = benchmark_fees = Decimal("0.00")
    closes = [_decimal(bar["close"]) for bar in rows]

    for i in range(slow, len(rows)):
        bar = rows[i]
        fast_mean = sum(closes[i - p["fast"]:i]) / p["fast"]
        slow_mean = sum(closes[i - slow:i]) / slow
        side = "BUY" if fast_mean > slow_mean else "SELL"
        reason = "前一交易日短均线高于长均线，目标持有" if side == "BUY" else "前一交易日短均线不高于长均线，目标现金"
        if side == "BUY" or shares:
            try:
                quantity = _buy_quantity(bar, cash, p) if side == "BUY" else shares
                if quantity == 0:
                    if not shares:
                        raise ValueError("现金不足以买入100股并支付费用")
                else:
                    fill = execute_order(bar, side, quantity, cash, shares, p)
                    cash = fill["cash_after"]
                    shares += quantity if side == "BUY" else -quantity
                    total_fees += fill["fees"]
                    trades.append(_json_money({**fill, "signal_date": rows[i - 1]["date"], "reason": reason}))
            except ValueError as exc:
                rejected.append({"date": bar["date"], "signal_date": rows[i - 1]["date"], "side": side, "reason": str(exc)})

        if not benchmark_bought:
            try:
                quantity = _buy_quantity(bar, benchmark_cash, p)
                if quantity == 0:
                    raise ValueError("基准现金不足以买入100股并支付费用")
                fill = execute_order(bar, "BUY", quantity, benchmark_cash, 0, p)
                benchmark_cash = fill["cash_after"]
                benchmark_shares = quantity
                benchmark_bought = True
                benchmark_fees += fill["fees"]
                benchmark_trades.append(_json_money({**fill, "signal_date": rows[i - 1]["date"], "reason": "同期间买入持有基准"}))
            except ValueError as exc:
                benchmark_rejected.append({"date": bar["date"], "side": "BUY", "reason": str(exc)})
        equity = _money(cash + shares * closes[i])
        benchmark_equity = _money(benchmark_cash + benchmark_shares * closes[i])
        values.append(equity)
        curve.append({"date": bar["date"], "equity": float(equity), "benchmark_equity": float(benchmark_equity), "cash": float(cash), "shares": shares})

    fingerprint = hashlib.sha256(json.dumps({"dataset_id": dataset.get("id"), "parameters": p, "engine": ENGINE_VERSION}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {
        "dataset_id": dataset.get("id"), "symbol": symbol, "parameters": p,
        "engine_version": ENGINE_VERSION, "fingerprint": fingerprint,
        "source_kind": dataset.get("meta", {}).get("source_kind"),
        "evaluation_start": curve[0]["date"], "evaluation_end": curve[-1]["date"],
        "warmup_start": rows[0]["date"],
        "assumptions": [
            "仅沪深主板普通股票，人民币现金账户、只做多；买入100股整手，下一交易日才可卖。",
            "短/长均线使用截至前一交易日收盘的原始价格；每天重新计算目标，下一交易日开盘提交一日订单，失败不自动延续旧信号。",
            "使用区间前已有数据预热；数据不足时推迟评价起日，策略与买入持有基准使用完全相同评价日期及初始资金。",
            "买入持有基准在首个评价日尝试买入，失败则每天重试；首次成功后持有至期末，不再补仓。",
            "固定费率仅为明确确认的演示情景；不自动还原历史费率，不代表任何券商报价。",
            "佣金、卖出印花税及双边过户费分别四舍五入到分；滑点按买入向上、卖出向下取分。",
            "开盘涨停禁止买入、开盘跌停禁止卖出；停牌、零量和超出当日总成交量的订单全部拒绝，不部分成交。",
            "滑点后价格必须在当天OHLC及明确涨跌停价内；日线不能还原盘口、排队和真实流动性，未使用成交参与率模型。",
            "同一交易日只有一次目标交易，持仓最早次日出售；期末按原始收盘价计值，不强制卖出或预扣未发生的卖出费用。",
            "已知公司行动、复权因子变化或关键交易信息缺失会阻止执行；当前不支持股息、送转或配股。",
        ],
        "metrics": {
            "total_return": float(values[-1] / initial - 1),
            "benchmark_return": float(benchmark_equity / initial - 1),
            "max_drawdown": _drawdown(values, initial),
            "final_equity": float(values[-1]), "cash": float(cash), "shares": shares,
            "total_fees": float(total_fees), "benchmark_total_fees": float(benchmark_fees),
        },
        "curve": curve, "trades": trades, "rejected_orders": rejected,
        "benchmark_trades": benchmark_trades, "benchmark_rejected_orders": benchmark_rejected,
        "warnings": [
            "演示/历史回测不表示未来收益，不包含选股过程的幸存者偏差校正。",
            "全部数据须在当时可获得；本模型只保证均线计算不读取未来价格，不能证明数据源具备历史时点版本。",
        ] + (["本结果使用确定性合成数据，不是真实市场表现。"] if dataset.get("meta", {}).get("source_kind") == "demo" else []),
    }


def research(dataset: dict) -> dict:
    """Arithmetic raw-price summaries, without ratings or trading advice."""
    if not isinstance(dataset, dict) or not isinstance(dataset.get("bars"), list):
        raise ValueError("数据集格式无效")
    verify_dataset_identity(dataset)
    groups = {}
    for bar in dataset["bars"]:
        if not isinstance(bar, dict):
            raise ValueError("行情记录格式无效")
        symbol = _symbol(bar.get("symbol"))
        _day(bar.get("date"))
        close = _decimal(bar.get("close"), "收盘价")
        if close < CENT or close > Decimal("1000000"):
            raise ValueError("收盘价须在0.01–1000000元范围内")
        groups.setdefault(symbol, []).append(bar)
    summaries = []
    for symbol, rows in sorted(groups.items()):
        dates = [row["date"] for row in rows]
        if dates != sorted(set(dates)):
            raise ValueError("研究行情必须按日期排序且无重复")
        closes = [_decimal(row["close"]) for row in rows]
        returns = [float(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
        last = closes[-1]
        warnings = []
        if len(closes) < 21:
            warnings.append("不足21个收盘价，20交易日收益/波动率显示为空")
        if any(row.get("corporate_action") is not False for row in rows) or len({str(row.get("adj_factor")) for row in rows}) != 1:
            warnings.append("公司行动信息不完整或复权因子变化；原始价格涨跌不能代表投资总回报")
        try:
            validate_market_window(dataset, symbol)
        except ValueError as exc:
            warnings.append(f"执行就绪检查未通过：{exc}")
        trend = "数据不足"
        if len(closes) >= 20:
            short = sum(closes[-5:]) / 5
            long = sum(closes[-20:]) / 20
            trend = "5日均线高于20日均线" if short > long else "5日均线低于20日均线" if short < long else "5日均线等于20日均线"
        summaries.append({
            "symbol": symbol, "bars": len(rows), "as_of": dates[-1],
            "last_close": float(last),
            "return_20d": float(last / closes[-21] - 1) if len(closes) >= 21 else None,
            "volatility_20d": statistics.stdev(returns[-20:]) * math.sqrt(252) if len(returns) >= 20 else None,
            "max_drawdown": _drawdown(closes), "trend": trend,
            "facts": [f"截至 {dates[-1]}，共 {len(rows)} 条已导入收盘价。", "20日收益使用21个收盘价；波动率为20个日简单收益样本标准差乘√252。"],
            "counterarguments": ["均线只描述历史走势，未提供上涨概率或买卖建议。", "原始价格未计现金分红，样本范围与数据可得时间可能影响结论。"],
            "warnings": warnings,
        })
    return {"as_of": max((item["as_of"] for item in summaries), default=None), "symbols": summaries,
            "dataset_id": dataset.get("id"), "source_kind": dataset.get("meta", {}).get("source_kind"),
            "limitations": ["仅计算已导入数据的历史统计，不是基本面估值或证券推荐。", "原始价格变化不等于含分红再投资的总收益。", "合成演示数据不能用于真实投资判断。"]}
