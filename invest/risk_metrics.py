"""Two independent performance-metric readings of explicit daily returns.

No price download, strategy selection, allocation, or order path is provided.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math


_METRICS = ("annual_volatility", "max_drawdown", "sharpe_zero_rf")
_TOLERANCE = {"annual_volatility": 1e-8, "max_drawdown": 1e-8,
              "sharpe_zero_rf": 1e-8}


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


def _input(history, as_of):
    end = _day(as_of)
    if end > date.today().isoformat():
        raise ValueError("研究截止日期不得晚于今天")
    if not isinstance(history, dict) or set(history) != {"data_scope", "source", "daily_returns"}:
        raise ValueError("历史输入仅接受 data_scope/source/daily_returns")
    if history["data_scope"] != "PUBLIC_RESEARCH_ONLY":
        raise ValueError("仅接受 PUBLIC_RESEARCH_ONLY 输入")
    source = history["source"]
    if not isinstance(source, str) or not source.strip() or len(source) > 300:
        raise ValueError("须声明有效历史数据来源")
    rows = history["daily_returns"]
    if not isinstance(rows, list) or not 30 <= len(rows) <= 5000:
        raise ValueError("须提供30至5000个日收益观测")
    previous = ""
    days, values, canonical_rows = [], [], []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"date", "return"}:
            raise ValueError("每行须仅含 date/return")
        day = _day(row["date"])
        if day <= previous or day > end:
            raise ValueError("日期须严格递增且不晚于研究截止日期")
        previous = day
        raw = row["return"]
        if isinstance(raw, bool) or not isinstance(raw, (str, int, float)):
            raise ValueError("日收益须为有限简单收益")
        try:
            parsed = Decimal(str(raw))
        except InvalidOperation as exc:
            raise ValueError("日收益须为有限简单收益") from exc
        if not parsed.is_finite() or not Decimal("-1") < parsed <= Decimal("10"):
            raise ValueError("日收益超出允许范围")
        value = float(parsed)
        if not math.isfinite(value) or (parsed != 0 and value == 0):
            raise ValueError("日收益超出浮点计算范围")
        days.append(day)
        values.append(value)
        canonical_rows.append({"date": day, "return": str(parsed.normalize())})
    canonical = {"data_scope": "PUBLIC_RESEARCH_ONLY", "source": source.strip(),
                 "daily_returns": canonical_rows}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=False,
                                       separators=(",", ":")).encode("utf-8")).hexdigest()
    return days, values, source.strip(), digest


def _series(days, values):
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("缺少 pandas；请安装 risk-metrics 额外依赖") from exc
    return pd.Series(values, index=pd.to_datetime(days, format="%Y-%m-%d"), dtype=float)


def _from_quantstats(days, values, sharpe_defined):
    try:
        import quantstats as qs
        from importlib.metadata import version
    except ImportError as exc:
        raise RuntimeError("缺少 QuantStats；请安装 risk-metrics 额外依赖") from exc
    stats = qs.stats
    series = _series(days, values)
    return {"version": version("quantstats"), "metrics": {
        "annual_volatility": stats.volatility(series, periods=252, annualize=True),
        "max_drawdown": stats.max_drawdown(series),
        "sharpe_zero_rf": stats.sharpe(series, rf=0.0, periods=252,
                                      annualize=True, smart=False) if sharpe_defined else None,
    }}


def _from_empyrical(days, values, sharpe_defined):
    try:
        import empyrical
        from importlib.metadata import version
    except ImportError as exc:
        raise RuntimeError("缺少 Empyrical Reloaded；请安装 risk-metrics 额外依赖") from exc
    series = _series(days, values)
    return {"version": version("empyrical-reloaded"), "metrics": {
        "annual_volatility": empyrical.annual_volatility(series, period="daily", annualization=252),
        "max_drawdown": empyrical.max_drawdown(series),
        "sharpe_zero_rf": empyrical.sharpe_ratio(series, risk_free=0.0,
                                                 period="daily", annualization=252)
                          if sharpe_defined else None,
    }}


def compare_risk_metrics(history: dict, *, as_of: str) -> dict:
    """Cross-check three metrics without selecting a preferred engine.

    This is an in-sample calculation on caller-supplied, noncumulative simple
    daily returns. A constant stream has no defined Sharpe ratio.
    """
    days, values, source, digest = _input(history, as_of)
    sharpe_defined = min(values) != max(values)
    raw = {"quantstats": _from_quantstats(days.copy(), values.copy(), sharpe_defined),
           "empyrical_reloaded": _from_empyrical(days.copy(), values.copy(), sharpe_defined)}
    backends = {}
    for name, result in raw.items():
        if not isinstance(result, dict) or set(result) != {"version", "metrics"} or not isinstance(result["version"], str) or not result["version"] or not isinstance(result["metrics"], dict) or set(result["metrics"]) != set(_METRICS):
            raise ValueError(f"{name} 返回不完整的指标集合")
        metrics = {}
        for metric in _METRICS:
            value = result["metrics"][metric]
            if metric == "sharpe_zero_rf" and not sharpe_defined:
                if value is not None:
                    raise ValueError(f"{name} 在零波动样本返回了 Sharpe 值")
                metrics[metric] = None
            else:
                if isinstance(value, bool) or value is None:
                    raise ValueError(f"{name} 的 {metric} 非有限数值")
                try:
                    number = float(value)
                except (TypeError, ValueError, OverflowError) as exc:
                    raise ValueError(f"{name} 的 {metric} 非有限数值") from exc
                if not math.isfinite(number):
                    raise ValueError(f"{name} 的 {metric} 非有限数值")
                metrics[metric] = number
        backends[name] = {"version": result["version"], "metrics": metrics}
    comparison = {}
    for metric in _METRICS:
        left = backends["quantstats"]["metrics"][metric]
        right = backends["empyrical_reloaded"]["metrics"][metric]
        gap = abs(left - right) if left is not None and right is not None else None
        comparison[metric] = {"absolute_gap": gap, "absolute_tolerance": _TOLERANCE[metric],
                              "status": "UNDEFINED" if gap is None else
                              "AGREE" if gap <= _TOLERANCE[metric] else "DISAGREE"}
    return {"schema": "invest-risk-metrics-crosscheck-v1", "status": "SCENARIO_ONLY",
            "data_scope": "PUBLIC_RESEARCH_ONLY", "as_of": as_of,
            "history_source": source, "history_sha256": digest,
            "history_sessions": len(values), "history_start": days[0], "history_end": days[-1],
            "assumptions": {"return_type": "simple_daily_noncumulative",
                            "periods_per_year": 252, "risk_free_rate": 0.0,
                            "volatility_ddof": 1},
            "backends": backends, "comparison": comparison,
            "comparison_status": "DISAGREE" if any(x["status"] == "DISAGREE" for x in comparison.values())
                                 else "PARTIAL_UNDEFINED" if not sharpe_defined else "AGREE",
            "limitations": ["仅对输入样本进行指标交叉核验；未验证数据授权、完整性或样本外绩效。",
                            "252 日年化和零无风险利率是显式研究假设，不代表未来收益或可交易结论。"]}
