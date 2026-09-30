"""Deterministic small-CNY allocation feasibility, using explicit scenario inputs.

This module makes no provider call and submits no order. Public quotes yield
PUBLIC_RESEARCH_ONLY scenarios, never execution-authorized instructions.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import hashlib
import json
from datetime import date

CENT = Decimal("0.01")


def _decimal(value, label, *, nonnegative=True):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{label}必须是有限数值")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError(f"{label}必须是有限数值") from exc
    if not result.is_finite() or abs(result) > Decimal("1000000000") or (nonnegative and result < 0):
        raise ValueError(f"{label}范围无效")
    return result


def _money(value, label):
    result = _decimal(value, label)
    if result != result.quantize(CENT):
        raise ValueError(f"{label}必须精确到分")
    return result


def _date(value, label):
    if not isinstance(value, str):
        raise ValueError(f"{label}必须为 YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}必须为有效日期") from exc
    if parsed.isoformat() != value:
        raise ValueError(f"{label}必须为 YYYY-MM-DD")
    return value


def _text(value, label):
    if not isinstance(value, str) or not value.strip() or len(value) > 300:
        raise ValueError(f"{label}必须为非空文本且不超过300字符")
    return value.strip()


def _integer(value, label):
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 100000000:
        raise ValueError(f"{label}必须为正整数")
    return value


def _cent(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _fees(gross, rate, minimum, transfer_rate):
    commission = _cent(max(gross * rate, minimum))
    transfer = _cent(gross * transfer_rate)
    return commission, transfer


def size_allocation(request: dict) -> dict:
    """Size a candidate scenario; no implicit exchange rules, fees, or quote source.

    The caller supplies a total budget, a cash reserve, and candidates with
    weight, quote, lot, liquidity cap, fee schedule and rule provenance. The
    deterministic greedy objective reduces squared target-notional error one
    lot at a time. It is not an optimizer or a prediction of fills.
    """
    if not isinstance(request, dict):
        raise ValueError("配置请求必须为对象")
    cash = _money(request.get("cash_cny"), "现金")
    reserve = _money(request.get("reserve_cny"), "保留现金")
    if cash <= 0 or reserve > cash:
        raise ValueError("现金必须大于零且保留现金不得超额")
    max_fee_fraction = _decimal(request.get("max_entry_fee_fraction"), "买入费用比例上限")
    if max_fee_fraction > 1:
        raise ValueError("买入费用比例上限不得超过1")
    candidates = request.get("candidates")
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 20:
        raise ValueError("须提供1至20个候选资产")
    as_of = _date(request.get("as_of"), "方案日期")
    source_scope = request.get("data_scope")
    if source_scope != "PUBLIC_RESEARCH_ONLY":
        raise ValueError("当前原型只接受 PUBLIC_RESEARCH_ONLY 数据")
    budget = cash - reserve
    assets = []
    symbols = set()
    for item in candidates:
        if not isinstance(item, dict):
            raise ValueError("候选资产必须为对象")
        symbol = _text(item.get("symbol"), "资产代码")
        if symbol in symbols:
            raise ValueError("候选资产代码重复")
        symbols.add(symbol)
        price = _money(item.get("price_cny"), "报价")
        if price <= 0:
            raise ValueError("报价必须大于零")
        quote_date = _date(item.get("quote_date"), "报价日期")
        rule_date = _date(item.get("rule_date"), "规则核验日期")
        if quote_date > as_of or rule_date > as_of:
            raise ValueError("报价或规则核验日期不能晚于方案日期")
        weight = _decimal(item.get("target_weight"), "目标权重")
        if weight > 1:
            raise ValueError("目标权重不得超过1")
        lot = _integer(item.get("buy_lot_shares"), "最小买入股数")
        liquidity = item.get("max_buy_shares")
        if isinstance(liquidity, bool) or not isinstance(liquidity, int) or not 0 <= liquidity <= 100000000:
            raise ValueError("流动性上限须为非负整数股")
        rate = _decimal(item.get("commission_rate"), "佣金比例")
        minimum = _money(item.get("min_commission_cny"), "最低佣金")
        transfer = _decimal(item.get("transfer_fee_rate"), "买入过户费率")
        sell_tax = _decimal(item.get("sell_tax_rate"), "卖出税率")
        if any(x > 1 for x in (rate, transfer, sell_tax)):
            raise ValueError("费率不得超过1")
        assets.append(dict(symbol=symbol, price=price, quote_date=quote_date,
            quote_source=_text(item.get("quote_source"), "报价来源"),
            rule_date=rule_date, rule_source=_text(item.get("rule_source"), "规则来源"),
            weight=weight, lot=lot, liquidity=liquidity, rate=rate,
            minimum=minimum, transfer=transfer, sell_tax=sell_tax,
            quantity=0, cost=Decimal(0), fees=Decimal(0)))
    if sum((a["weight"] for a in assets), Decimal(0)) > 1:
        raise ValueError("目标权重合计不得超过1")

    # Full portfolio quote/lot/fees and liquidity are checked before selecting
    # each increment. A global net budget check prevents double spending.
    spent = Decimal(0)
    for _step in range(10000):
        best = None
        for a in assets:
            next_quantity = a["quantity"] + a["lot"]
            if next_quantity > a["liquidity"]:
                continue
            gross = _cent(a["price"] * next_quantity)
            commission, transfer = _fees(gross, a["rate"], a["minimum"], a["transfer"])
            next_fee = commission + transfer
            next_cost = gross + next_fee
            delta = next_cost - a["cost"]
            if spent + delta > budget or next_fee > gross * max_fee_fraction:
                continue
            target = budget * a["weight"]
            before = (target - a["price"] * a["quantity"]) ** 2
            after = (target - a["price"] * next_quantity) ** 2
            gain = before - after
            if gain <= 0:
                continue
            score = (gain / delta, gain, a["symbol"])
            if best is None or score[:2] > best[0][:2] or (score[:2] == best[0][:2] and score[2] < best[0][2]):
                best = (score, a, next_quantity, next_cost, next_fee)
        if best is None:
            break
        _, chosen, quantity, cost, fees = best
        spent += cost - chosen["cost"]
        chosen.update(quantity=quantity, cost=cost, fees=fees)
    else:
        raise ValueError("候选配置迭代超过10000步；请缩小输入资金或提高交易单位")

    rows = []
    for a in assets:
        gross = _cent(a["price"] * a["quantity"])
        if a["quantity"]:
            reason = "候选数量满足输入的整手、费用、流动性和现金约束"
        elif a["weight"] == 0:
            reason = "目标权重为零"
        elif a["liquidity"] < a["lot"]:
            reason = "输入的流动性上限不足一手"
        elif a["price"] * a["lot"] > budget:
            reason = "一手报价已超过可用资金"
        else:
            reason = "最小佣金、现金或目标权重约束下不配置；详见输入假设"
        rows.append({"symbol": a["symbol"], "quantity_shares": a["quantity"],
            "target_weight": str(a["weight"]), "quote_cny": str(a["price"]),
            "quote_date": a["quote_date"], "quote_source": a["quote_source"],
            "rule_date": a["rule_date"], "rule_source": a["rule_source"],
            "buy_lot_shares": a["lot"], "max_buy_shares": a["liquidity"],
            "gross_cny": str(gross), "entry_fees_cny": str(a["fees"]),
            "total_cash_required_cny": str(a["cost"]), "reason": reason})
    canonical = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return {"schema": "invest-allocation-scenario-v1", "data_scope": source_scope,
        "status": "SCENARIO_ONLY", "as_of": as_of,
        "input_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "cash_cny": str(cash), "reserved_cny": str(reserve),
        "spent_cny": str(spent), "remaining_cash_cny": str(cash - spent),
        "candidates": rows,
        "limitations": ["报价与交易规则仅按输入情景计算，未核实实时可成交性、停牌、公司行动或历史有效规则。",
            "流动性上限是输入假设，不代表实际盘口可成交量。",
            "卖出税费率已要求明确输入，但本结果仅计算买入现金；未来卖出成本和收益未估算。",
            "未验证数据许可或券商费率，不能据此生成真实订单或承诺收益。"]}
