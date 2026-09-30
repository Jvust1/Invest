"""Optional minimum-variance candidate generation for public research scenarios.

This module never loads prices, chooses securities or submits trades. Historical
returns and market facts are provided explicitly; optimizer output goes through
Invest's separate small-capital sizing layer.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import hashlib
import json

from .allocation import size_allocation


def _day(value):
    if not isinstance(value, str):
        raise ValueError("历史日期须为 YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("历史日期无效") from exc
    if parsed.isoformat() != value:
        raise ValueError("历史日期须为 YYYY-MM-DD")
    return value


def _return(value):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError("历史收益须为有限数值")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise ValueError("历史收益须为有限数值") from exc
    if not result.is_finite() or not Decimal("-1") < result <= Decimal("10"):
        raise ValueError("历史简单收益超出允许范围")
    return result


def _history(history, symbols, as_of, quote_dates):
    if not isinstance(history, dict) or history.get("data_scope") != "PUBLIC_RESEARCH_ONLY":
        raise ValueError("优化器只接受 PUBLIC_RESEARCH_ONLY 历史输入")
    source = history.get("source")
    if not isinstance(source, str) or not source.strip() or len(source) > 300:
        raise ValueError("历史数据须声明来源")
    rows = history.get("daily_returns")
    if not isinstance(rows, list) or not 30 <= len(rows) <= 5000:
        raise ValueError("历史样本须为30至5000个共同观测日")
    previous = ""
    values = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("历史行须为对象")
        day = _day(row.get("date"))
        if day <= previous or day > as_of or day > min(quote_dates):
            raise ValueError("历史日期须严格递增，且不得晚于方案或报价日期")
        previous = day
        returns = row.get("returns")
        if not isinstance(returns, dict) or set(returns) != set(symbols):
            raise ValueError("每个观测日须含与候选资产完全一致的收益列")
        values.append([float(_return(returns[symbol])) for symbol in symbols])
    canonical = json.dumps(history, sort_keys=True, ensure_ascii=False,
                           separators=(",", ":"), allow_nan=False)
    return values, hashlib.sha256(canonical.encode()).hexdigest(), previous, source.strip()


def _weights_from_pypfopt(symbols, values):
    try:
        import pandas as pd
        from pypfopt import EfficientFrontier
        from importlib.metadata import version
    except ImportError as exc:
        raise RuntimeError("缺少可选依赖 PyPortfolioOpt；请安装 optimization 额外依赖") from exc
    frame = pd.DataFrame(values, columns=symbols)
    covariance = frame.cov()
    if covariance.isna().to_numpy().any():
        raise ValueError("历史协方差包含缺失值")
    expected = pd.Series(0.0, index=symbols)
    try:
        optimizer = EfficientFrontier(expected, covariance, weight_bounds=(0, 1))
        raw = optimizer.min_volatility()
    except Exception as exc:
        raise ValueError("最小方差优化失败；无权重输出") from exc
    return raw, version("PyPortfolioOpt")



def _weights_from_riskfolio(symbols, values):
    try:
        import pandas as pd
        import riskfolio as rp
        from importlib.metadata import version
    except ImportError as exc:
        raise RuntimeError("缺少可选依赖 Riskfolio-Lib；请安装 optimization-riskfolio 额外依赖") from exc
    try:
        portfolio = rp.Portfolio(returns=pd.DataFrame(values, columns=symbols), sht=False)
        portfolio.assets_stats(method_mu="hist", method_cov="hist")
        result = portfolio.optimization(model="Classic", rm="MV", obj="MinRisk", rf=0, l=0, hist=True)
        if result is None or result.shape != (len(symbols), 1) or set(result.index) != set(symbols):
            raise ValueError("Riskfolio-Lib 未返回完整单列权重")
        raw = {symbol: result.loc[symbol].iloc[0] for symbol in symbols}
    except Exception as exc:
        raise ValueError("Riskfolio-Lib 最小方差优化失败；无权重输出") from exc
    return raw, version("riskfolio-lib")


def _weights_from_skfolio(symbols, values):
    try:
        import pandas as pd
        from skfolio import RiskMeasure
        from skfolio.optimization import MeanRisk, ObjectiveFunction
        from importlib.metadata import version
    except ImportError as exc:
        raise RuntimeError("缺少可选依赖 skfolio；请安装 optimization-skfolio 额外依赖") from exc
    try:
        model = MeanRisk(objective_function=ObjectiveFunction.MINIMIZE_RISK,
                         risk_measure=RiskMeasure.VARIANCE,
                         min_weights=0, max_weights=1, raise_on_failure=True)
        model.fit(pd.DataFrame(values, columns=symbols))
        if model.weights_ is None or getattr(model.weights_, "shape", None) != (len(symbols),):
            raise ValueError("skfolio 未返回一维完整权重")
        raw = dict(zip(symbols, model.weights_))
    except Exception as exc:
        raise ValueError("skfolio 最小方差优化失败；无权重输出") from exc
    return raw, version("skfolio")


_BACKENDS = {
    "pypfopt": ("PyPortfolioOpt", "_weights_from_pypfopt"),
    "riskfolio": ("Riskfolio-Lib", "_weights_from_riskfolio"),
    "skfolio": ("skfolio", "_weights_from_skfolio"),
}

def min_variance_scenario(history: dict, sizing_request: dict, *, backend: str = "pypfopt") -> dict:
    """Fit minimum-variance weights and size them with explicit CNY constraints.

    No fallback to a second optimizer or equal weights occurs on failure.
    Input is a single common historical window; this is in-sample research,
    not predictive validation or execution-grade market evidence.
    """
    if not isinstance(sizing_request, dict) or sizing_request.get("data_scope") != "PUBLIC_RESEARCH_ONLY":
        raise ValueError("配置请求须为 PUBLIC_RESEARCH_ONLY")
    as_of = _day(sizing_request.get("as_of"))
    candidates = sizing_request.get("candidates")
    if not isinstance(candidates, list) or not 2 <= len(candidates) <= 20:
        raise ValueError("最小方差需要2至20个候选资产")
    symbols = [candidate.get("symbol") for candidate in candidates if isinstance(candidate, dict)]
    if len(symbols) != len(candidates) or any(not isinstance(s, str) or not s for s in symbols) or len(set(symbols)) != len(symbols):
        raise ValueError("候选资产代码缺失或重复")
    quote_dates = [_day(candidate.get("quote_date")) for candidate in candidates]
    values, history_sha, last_day, source = _history(history, symbols, as_of, quote_dates)
    if backend not in _BACKENDS:
        raise ValueError("未知优化后端；必须显式选择 pypfopt/riskfolio/skfolio")
    backend_name, adapter_name = _BACKENDS[backend]
    raw, package_version = globals()[adapter_name](symbols, values)
    if not hasattr(raw, "keys") or set(raw) != set(symbols):
        raise ValueError("优化器权重资产集合与输入不一致")
    weights = {}
    for symbol in symbols:
        value = Decimal(str(raw[symbol]))
        if not value.is_finite() or value < Decimal("-0.0000001") or value > Decimal("1.0000001"):
            raise ValueError("优化器产生非法或负权重")
        weights[symbol] = max(Decimal(0), min(Decimal(1), value))
    total = sum(weights.values(), Decimal(0))
    if abs(total - 1) > Decimal("0.0001"):
        raise ValueError("优化器权重合计不为1")
    # Solver float tolerance is recorded and corrected only inside 0.0001.
    normalized = {symbol: weights[symbol] / total for symbol in symbols}
    candidate_request = {**sizing_request, "candidates": [
        {**candidate, "target_weight": str(normalized[candidate["symbol"]])}
        for candidate in candidates
    ]}
    sizing = size_allocation(candidate_request)
    return {"schema": "invest-min-variance-scenario-v1", "status": "SCENARIO_ONLY",
        "data_scope": "PUBLIC_RESEARCH_ONLY", "objective": "minimum_variance_long_only",
        "backend": backend_name, "backend_version": package_version,
        "history_source": source, "history_sha256": history_sha,
        "history_sessions": len(values), "history_end": last_day,
        "raw_weight_sum": str(total),
        "weights": {symbol: str(normalized[symbol]) for symbol in symbols},
        "allocation": sizing,
        "limitations": ["仅基于输入的历史样本拟合最小方差权重，未做样本外或前向验证。",
            "优化权重不代表真实可买数量；最终股数仍由明确输入的价格、整手、费用和现金约束决定。",
            "没有核实行情许可、报价实时性、规则有效期、停牌、公司行动或实际盘口。"]}



def compare_min_variance_backends(history: dict, sizing_request: dict,
                                  *, backends=("pypfopt", "riskfolio", "skfolio")) -> dict:
    """Run each explicitly selected backend; differences are evidence, not votes.

    A missing or failing backend fails the comparison. No winning portfolio is
    selected and no fallback result is silently substituted.
    """
    if not isinstance(backends, (tuple, list)) or len(backends) < 2 or len(set(backends)) != len(backends):
        raise ValueError("交叉比较须显式选择至少两个不同后端")
    if any(backend not in _BACKENDS for backend in backends):
        raise ValueError("交叉比较包含未知后端")
    results = [min_variance_scenario(history, sizing_request, backend=backend)
               for backend in backends]
    symbols = list(results[0]["weights"])
    gaps = {}
    for i, left in enumerate(results):
        for right in results[i + 1:]:
            pair = left["backend"] + " vs " + right["backend"]
            gaps[pair] = {
                "max_absolute_weight_gap": str(max(
                    abs(Decimal(left["weights"][s]) - Decimal(right["weights"][s]))
                    for s in symbols)),
                "remaining_cash_gap_cny": str(abs(
                    Decimal(left["allocation"]["remaining_cash_cny"])
                    - Decimal(right["allocation"]["remaining_cash_cny"]))),
            }
    return {"schema": "invest-min-variance-crosscheck-v1", "status": "SCENARIO_ONLY",
        "data_scope": "PUBLIC_RESEARCH_ONLY", "results": results, "pairwise_gaps": gaps,
        "interpretation": "后端分歧只作为复核线索，不选择获胜模型或生成交易指令。"}
