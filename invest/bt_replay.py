"""Independent bt cash/position/valuation replay of an initial allocation.

This checks portfolio accounting on explicit research inputs. It does not test
signal generation, fills, market eligibility or an execution backtest contract.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json

from .allocation import size_allocation

CENT = Decimal("0.01")
TOLERANCE = Decimal("0.000001")


def _day(value):
    if not isinstance(value, str):
        raise ValueError("日期须为 YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("日期无效") from exc
    if parsed.isoformat() != value:
        raise ValueError("日期须为 YYYY-MM-DD")
    return value


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("金额须为有限数值")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("金额须为有限数值") from exc
    if not number.is_finite() or abs(number) > Decimal("1000000000000000000"):
        raise ValueError("金额须为有限且范围有效的数值")
    return number


def _history(history, allocation, as_of):
    end = _day(as_of)
    if end > date.today().isoformat():
        raise ValueError("研究截止日不得晚于今天")
    fields = {"data_scope", "source", "price_basis", "daily_prices"}
    if not isinstance(history, dict) or set(history) != fields:
        raise ValueError("历史输入字段不完整或包含未知字段")
    if history["data_scope"] != "PUBLIC_RESEARCH_ONLY":
        raise ValueError("仅接受 PUBLIC_RESEARCH_ONLY")
    source = history["source"]
    if not isinstance(source, str) or not source.strip() or len(source) > 300:
        raise ValueError("历史价格须声明来源")
    if history["price_basis"] != "UNADJUSTED_NO_CORPORATE_ACTIONS":
        raise ValueError("当前仅支持明确声明无公司行动的原始价格情景")
    rows = history["daily_prices"]
    if not isinstance(rows, list) or not 2 <= len(rows) <= 5000:
        raise ValueError("须有2至5000个共同价格观测日")
    symbols = [c["symbol"] for c in allocation["candidates"]]
    days, prices, normalized = [], [], []
    previous = ""
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"date", "prices_cny"}:
            raise ValueError("每日价格字段无效")
        day = _day(row["date"])
        if day <= previous or day > end:
            raise ValueError("观测日期须严格递增且不晚于截止日")
        previous = day
        values = row["prices_cny"]
        if not isinstance(values, dict) or set(values) != set(symbols):
            raise ValueError("每日价格须覆盖全部候选资产，不能缺列、填充或增加资产")
        parsed = {s: _number(values[s]) for s in symbols}
        if any(p <= 0 or p > Decimal("1000000000") or p != p.quantize(CENT) for p in parsed.values()):
            raise ValueError("价格须为正数且精确到分")
        days.append(day)
        prices.append(parsed)
        normalized.append({"date": day, "prices_cny": {s: str(parsed[s].quantize(CENT)) for s in symbols}})
    if days[0] != allocation["as_of"] or any(c["quote_date"] != days[0] for c in allocation["candidates"]):
        raise ValueError("配置日、全部报价日与首个观测日须一致；不能将未来配置回填到历史")
    if any(prices[0][c["symbol"]] != Decimal(c["quote_cny"]) for c in allocation["candidates"]):
        raise ValueError("首日价格必须与离散配置报价一致")
    canonical = {"data_scope": history["data_scope"], "source": source.strip(),
                 "price_basis": history["price_basis"], "daily_prices": normalized}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    return days, prices, source.strip(), digest


def _run_bt(days, prices, cash, trades):
    try:
        import bt
        import pandas as pd
        from importlib.metadata import version
    except ImportError as exc:
        raise RuntimeError("缺少 bt；请安装 backtest-bt 可选依赖") from exc

    # This independent fee callback does not reuse allocation._fees or its
    # computed fee totals. Each fixed entry is submitted once, in full.
    def commission_for(trade):
        def commission(q, p):
            gross = (Decimal(str(abs(q))) * Decimal(str(p))).quantize(CENT, rounding=ROUND_HALF_UP)
            commission_fee = max(gross * Decimal(trade["commission_rate"]),
                                 Decimal(trade["min_commission_cny"])).quantize(CENT, rounding=ROUND_HALF_UP)
            transfer_fee = (gross * Decimal(trade["transfer_fee_rate"])).quantize(CENT, rounding=ROUND_HALF_UP)
            return float(commission_fee + transfer_fee)
        return commission

    class EnterOnce(bt.Algo):
        def __call__(self, target):
            for trade in trades:
                if trade["quantity_shares"]:
                    # bt's fee hook has q/p only. Set the applicable schedule
                    # immediately before this symbol's one initial transaction.
                    target.set_commissions(commission_for(trade))
                    target[trade["symbol"]].transact(trade["quantity_shares"], update=False)
            target.root.update(target.now)
            return True

    symbols = [t["symbol"] for t in trades]
    frame = pd.DataFrame([{s: float(row[s]) for s in symbols} for row in prices],
                         index=pd.to_datetime(days, format="%Y-%m-%d"))
    strategy = bt.Strategy("invest_fixed_entry", [bt.algos.RunOnce(), EnterOnce()],
                           children=[bt.Security(s) for s in symbols])
    run = bt.Backtest(strategy, frame, initial_capital=float(cash),
                      integer_positions=True, progress_bar=False)
    run.run()
    replay = run.strategy
    positions = replay.positions
    # Select only supplied observations; bt prepends a bootstrap date that is
    # not an actual market observation and must not appear in our output.
    curve = [{"date": day, "cash_cny": float(replay.cash.loc[stamp]),
              "equity_cny": float(replay.values.loc[stamp]),
              "fees_cny": float(replay.fees.loc[stamp]),
              "positions": {s: float(positions.loc[stamp, s]) for s in symbols}}
             for day, stamp in zip(days, frame.index)]
    return {"version": version("bt"), "curve": curve}


def compare_allocation_replay(history: dict, sizing_request: dict, *, as_of: str) -> dict:
    """Compare Invest's fixed-holdings ledger with a real bt replay.

    The initial allocation is sized once at the first observation's prices.
    There are no subsequent orders, external cash flows or corporate actions.
    """
    allocation = size_allocation(sizing_request)
    days, prices, source, digest = _history(history, allocation, as_of)
    by_symbol = {c["symbol"]: c for c in sizing_request["candidates"]}
    trades = [{"symbol": c["symbol"], "quantity_shares": c["quantity_shares"],
               **{key: str(by_symbol[c["symbol"]][key]) for key in
                  ("commission_rate", "min_commission_cny", "transfer_fee_rate")}}
              for c in allocation["candidates"]]
    positions = {c["symbol"]: c["quantity_shares"] for c in allocation["candidates"]}
    cash = Decimal(allocation["remaining_cash_cny"])
    entry_fees = sum((Decimal(c["entry_fees_cny"]) for c in allocation["candidates"]), Decimal(0))
    reference = [{"date": day, "cash_cny": str(cash),
                  "equity_cny": str((cash + sum((row[s] * positions[s] for s in positions),
                                               Decimal(0))).quantize(CENT)),
                  "fees_cny": str(entry_fees if i == 0 else Decimal(0)),
                  "positions": positions.copy()}
                 for i, (day, row) in enumerate(zip(days, prices))]
    result = _run_bt(days, prices, Decimal(allocation["cash_cny"]), trades)
    if not isinstance(result, dict) or not isinstance(result.get("version"), str) or not result["version"]:
        raise ValueError("bt 未返回版本")
    curve = result.get("curve")
    if not isinstance(curve, list) or len(curve) != len(days):
        raise ValueError("bt 观测数量与输入不符")
    comparisons, normalized = [], []
    for expected, observed in zip(reference, curve):
        if not isinstance(observed, dict) or set(observed) != set(expected) or observed["date"] != expected["date"]:
            raise ValueError("bt 返回日期或字段不匹配")
        holdings = observed["positions"]
        if not isinstance(holdings, dict) or set(holdings) != set(positions):
            raise ValueError("bt 返回持仓资产不匹配")
        parsed_positions = {s: _number(holdings[s]) for s in positions}
        if any(q < 0 or q != q.to_integral_value() for q in parsed_positions.values()):
            raise ValueError("bt 返回非整数或负持仓")
        gaps, row = {}, {"date": observed["date"], "positions": {s: int(q) for s, q in parsed_positions.items()}}
        for field in ("cash_cny", "equity_cny", "fees_cny"):
            value = _number(observed[field])
            row[field] = str(value)
            gaps[field] = abs(Decimal(expected[field]) - value)
        positions_match = row["positions"] == positions
        status = "AGREE" if positions_match and all(g <= TOLERANCE for g in gaps.values()) else "DISAGREE"
        comparisons.append({"date": observed["date"], "status": status,
                            "absolute_gaps": {k: str(v) for k, v in gaps.items()},
                            "positions_match": positions_match})
        normalized.append(row)
    return {"schema": "invest-bt-allocation-replay-v1", "status": "SCENARIO_ONLY",
            "data_scope": "PUBLIC_RESEARCH_ONLY", "as_of": as_of,
            "history_source": source, "history_sha256": digest, "history_sessions": len(days),
            "allocation": allocation, "backend": "bt", "backend_version": result["version"],
            "invest_curve": reference, "bt_curve": normalized, "comparison": comparisons,
            "absolute_tolerance_cny": str(TOLERANCE),
            "comparison_status": "AGREE" if all(c["status"] == "AGREE" for c in comparisons) else "DISAGREE",
            "limitations": ["固定首日数量的账务与估值复核；不验证信号生成、成交、后续调仓或策略有效性。",
                            "报价、费用、交易日与无公司行动均按输入情景；未独立核实授权、数据完整性或真实市场规则。",
                            "期末按最后价格估值，无强制卖出、股息、利息、外部现金流或未发生的卖出税费。"]}
