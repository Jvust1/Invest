"""Bridge a verified fixed-allocation replay into the standard risk report."""
from __future__ import annotations

from decimal import Decimal

from .bt_replay import compare_allocation_replay
from .risk_metrics import compare_risk_metrics


RETURN_CONVENTION = {
    "first_observation": "(equity_after_entry / initial_capital) - 1",
    "subsequent_observations": "(equity_t / equity_t_minus_1) - 1",
    "entry_fee_treatment": "included_in_first_observation_return",
    "external_cash_flows": "none",
    "return_type": "simple_daily_noncumulative",
}


def _daily_returns(curve, initial_capital):
    previous = Decimal(initial_capital)
    if previous <= 0:
        raise ValueError("初始资金必须大于零")
    rows = []
    for item in curve:
        if not isinstance(item, dict) or "date" not in item or "equity_cny" not in item:
            raise ValueError("净值曲线字段不完整")
        equity = Decimal(item["equity_cny"])
        if not equity.is_finite() or equity <= 0:
            raise ValueError("风险报告要求每日净值为有限正数")
        value = equity / previous - Decimal(1)
        if not Decimal("-1") < value <= Decimal("10"):
            raise ValueError("由净值推导的日收益超出允许范围")
        rows.append({"date": item["date"], "return": str(value.normalize())})
        previous = equity
    return rows


def compare_allocation_risk_report(history: dict, sizing_request: dict, *, as_of: str) -> dict:
    """Run accounting replay, derive fee-aware returns, then cross-check risk metrics.

    Risk metrics are not produced unless Invest and bt agree on every supplied
    observation. The first return is measured against pre-trade initial capital,
    so entry fees remain visible as performance drag instead of disappearing.
    """
    replay = compare_allocation_replay(history, sizing_request, as_of=as_of)
    if replay["comparison_status"] != "AGREE":
        raise ValueError("Invest 与 bt 净值回放存在分歧；拒绝继续生成风险报告")
    if replay["history_sessions"] < 30:
        raise ValueError("风险报告至少需要30个共同净值观测")

    initial_capital = Decimal(replay["allocation"]["cash_cny"])
    daily_returns = _daily_returns(replay["invest_curve"], initial_capital)
    entry_fees = sum((Decimal(row["entry_fees_cny"])
                      for row in replay["allocation"]["candidates"]), Decimal(0))
    expected_first = -entry_fees / initial_capital
    observed_first = Decimal(daily_returns[0]["return"])
    if observed_first != expected_first:
        raise ValueError("首日收益未完整反映入场费用")

    risk_history = {
        "data_scope": "PUBLIC_RESEARCH_ONLY",
        "source": replay["history_source"],
        "daily_returns": daily_returns,
    }
    risk = compare_risk_metrics(risk_history, as_of=as_of)
    return {
        "schema": "invest-allocation-risk-report-v1",
        "status": "SCENARIO_ONLY",
        "data_scope": "PUBLIC_RESEARCH_ONLY",
        "as_of": as_of,
        "return_convention": RETURN_CONVENTION.copy(),
        "initial_capital_cny": str(initial_capital),
        "entry_fees_cny": str(entry_fees),
        "first_observation_return": daily_returns[0]["return"],
        "daily_returns": daily_returns,
        "replay": replay,
        "risk_metrics": risk,
        "limitations": [
            "风险报告只在固定首日配置的 Invest/bt 账务回放逐日一致后生成；不验证信号、成交或后续调仓。",
            "首日收益显式包含入场费用；期末没有强制卖出，因此未发生的卖出税费不进入本报告。",
            "所有输入仍为 PUBLIC_RESEARCH_ONLY / SCENARIO_ONLY；未验证真实行情授权、公司行动、停复牌或样本外表现。",
        ],
    }
