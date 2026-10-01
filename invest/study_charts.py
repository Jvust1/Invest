"""Offline rendering of immutable study cases with Matplotlib's actual Agg canvas.

No provider, backtest, pyplot, GUI, TeX, URL, or caller-controlled output path.
The PNG is a derivative view; the saved JSON record remains authoritative.
"""
from __future__ import annotations

from datetime import date
from importlib import metadata
import io
import math
import re
import threading

from .workspace import canonical, digest

TESTED_MATPLOTLIB_VERSION = "3.10.8"
MAX_POINTS = 10000
MAX_RECORD_BYTES = 8 * 1024 * 1024 + 4096
_RENDER_LOCK = threading.Lock()
_MODES = {
    "invest-exploratory-study-v1": "EXPLORATORY_CHRONOLOGICAL_SLICES",
    "invest-walk-forward-study-v1": "EXPLORATORY_WALK_FORWARD",
}


class ChartDependencyError(RuntimeError):
    """Optional validated renderer is absent or has a different version."""


class ChartBusyError(RuntimeError):
    """At most one memory-bounded render may execute in this process."""


def _money(value, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError("chart values must be finite JSON numbers")
    if not (.01 <= value <= 1e9 if positive else 0 <= value <= 1e16):
        raise ValueError("chart values are outside the bounded nonnegative range")
    return float(value)


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def drawdowns(values, initial):
    """Fractions below the running peak, including initial capital before day one."""
    peak = initial
    output = []
    for value in values:
        peak = max(peak, value)
        output.append(value / peak - 1)
    return output


def prepare_chart(record, case_index):
    """Validate identity and curve semantics before importing the optional SDK."""
    if type(case_index) is not int or case_index < 0:
        raise ValueError("case must be a zero-based nonnegative integer")
    if not isinstance(record, dict) or record.get("kind") != "study":
        raise ValueError("a saved study record is required")
    payload = record.get("payload")
    if not isinstance(payload, dict) or record.get("id") != digest({"kind": "study", "payload": payload}):
        raise ValueError("study content identity mismatch")
    if len(canonical(record).encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("study exceeds the 8 MiB archive limit")
    protocol = payload.get("protocol")
    if (payload.get("schema") not in _MODES or not isinstance(protocol, dict)
            or protocol.get("schema") != payload["schema"]
            or protocol.get("mode") != _MODES[payload["schema"]]
            or protocol.get("frozen_holdout_opened") is not False
            or payload.get("protocol_id") != digest(protocol)
            or not all(_hash(protocol.get(k)) for k in ("dataset_id", "code_identity"))):
        raise ValueError("unsupported or inconsistent exploratory study protocol")
    cases = payload.get("results")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 27 or case_index >= len(cases):
        raise ValueError("case is outside the saved study")
    case = cases[case_index]
    if not isinstance(case, dict) or case.get("status") != "PASS":
        raise ValueError("failed study cases have no validated curve to render")
    result = case.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("parameters"), dict):
        raise ValueError("saved case has no valid engine result")
    parameters = result["parameters"]
    from .engine import validate_parameters
    normalized_parameters = validate_parameters(parameters, require_strategy=True)
    initial = _money(normalized_parameters["initial_cash"], positive=True)
    # The study stores the original cash declaration; the engine also accepts
    # exact decimal strings. Normalize that declaration through its existing contract.
    protocol_cash = validate_parameters({"initial_cash": protocol.get("initial_cash"),
                                       "cost_model_acknowledged": True})["initial_cash"]
    if (initial != protocol_cash
            or result.get("dataset_id") != protocol["dataset_id"]
            or result.get("symbol") != protocol.get("symbol")
            or parameters.get("symbol") != protocol.get("symbol")
            or not isinstance(result.get("symbol"), str)
            or re.fullmatch(r"[0-9]{6}\.(SH|SZ)", result["symbol"]) is None
            or result.get("source_kind") != payload.get("source_kind")
            or result.get("fingerprint") != digest({"dataset_id": result["dataset_id"],
                "parameters": parameters, "engine": result.get("engine_version")})):
        raise ValueError("case input identity does not match its study")
    curve = result.get("curve")
    if not isinstance(curve, list) or not 1 <= len(curve) <= MAX_POINTS:
        raise ValueError("chart requires 1–10000 saved observations")
    dates, equity, benchmark, cash = [], [], [], []
    for point in curve:
        if not isinstance(point, dict) or not isinstance(point.get("date"), str):
            raise ValueError("invalid curve observation")
        day = date.fromisoformat(point["date"])
        if day.isoformat() != point["date"] or (dates and day <= dates[-1]):
            raise ValueError("curve dates must be unique and strictly chronological")
        dates.append(day)
        equity.append(_money(point.get("equity")))
        benchmark.append(_money(point.get("benchmark_equity")))
        cash.append(_money(point.get("cash")))
        if cash[-1] > equity[-1] + .01:
            raise ValueError("uninvested cash exceeds total equity")
    if (result.get("evaluation_start") != dates[0].isoformat()
            or result.get("evaluation_end") != dates[-1].isoformat()):
        raise ValueError("curve coverage differs from the declared evaluation period")
    declines = drawdowns(equity, initial)
    benchmark_declines = drawdowns(benchmark, initial)
    metrics = result.get("metrics")
    expected = {"final_equity": equity[-1], "total_return": equity[-1] / initial - 1,
                "benchmark_return": benchmark[-1] / initial - 1, "max_drawdown": -min(declines)}
    if not isinstance(metrics, dict):
        raise ValueError("case metrics missing")
    for key, value in expected.items():
        actual = metrics.get(key)
        if (type(actual) not in (int, float) or not math.isfinite(actual)
                or not math.isclose(actual, value, rel_tol=1e-10, abs_tol=1e-10)):
            raise ValueError("saved metric disagrees with the chart: " + key)
    descriptor = {k: case.get(k) for k in ("period", "candidate", "cost")}
    identity = {"study_id": record["id"], "protocol_id": payload["protocol_id"],
                "dataset_id": protocol["dataset_id"], "code_identity": protocol["code_identity"],
                "schema": payload["schema"], "mode": protocol["mode"], "case_index": case_index,
                "case": descriptor, "engine_fingerprint": result["fingerprint"],
                "source_kind": payload.get("source_kind"), "initial_cash_cny": initial,
                "strategy": {key: normalized_parameters[key] for key in ("fast", "slow")},
                "demonstration_costs": {key: normalized_parameters[key] for key in
                    ("commission_rate", "min_commission", "stamp_tax_rate", "transfer_fee_rate", "slippage_bps")},
                "curve_sha256": digest(curve), "renderer": "matplotlib==" + TESTED_MATPLOTLIB_VERSION,
                "frozen_holdout_opened": False,
                "scope": "exploratory derivative; not real-market or investment-validity evidence"}
    return {"dates": dates, "equity": equity, "benchmark": benchmark, "cash": cash,
            "drawdown": declines, "benchmark_drawdown": benchmark_declines,
            "initial": initial, "symbol": result["symbol"], "identity": identity}


def render_study_png(record, case_index):
    data = prepare_chart(record, case_index)
    try:
        version = metadata.version("matplotlib")
    except metadata.PackageNotFoundError:
        raise ChartDependencyError("图表需要可选依赖：安装 Invest 的 charts 扩展（Matplotlib 3.10.8）") from None
    if version != TESTED_MATPLOTLIB_VERSION:
        raise ChartDependencyError("图表需要已验证版本 Matplotlib 3.10.8；请安装 Invest 的 charts 扩展")
    if not _RENDER_LOCK.acquire(blocking=False):
        raise ChartBusyError("已有图表正在生成，请稍后重试")
    try:
        try:
            from matplotlib.backends.backend_agg import FigureCanvasAgg
            from matplotlib.figure import Figure
            from matplotlib.text import Text
        except ImportError:
            raise ChartDependencyError("Matplotlib 图表依赖无法载入，请重新安装 charts 扩展") from None
        # No pyplot, matplotlib.use(), rc mutation, user-selected backend or output path.
        figure = Figure(figsize=(10, 7), dpi=120, facecolor="#f7f9fc", layout="none")
        canvas = FigureCanvasAgg(figure)
        top = figure.add_axes((.09, .43, .87, .36))
        bottom = figure.add_axes((.09, .20, .87, .17))
        x = list(range(len(data["dates"])))
        for key, label, color, style in (("equity", "Strategy", "#155e75", "-"),
                ("benchmark", "Buy and hold", "#c05621", "-"),
                ("cash", "Uninvested cash", "#64748b", ":")):
            top.plot(x, [v / data["initial"] * 100 for v in data[key]],
                     label=label, color=color, linestyle=style, linewidth=1.7)
        top.axhline(100, label="Initial cash baseline", color="#94a3b8", linestyle="--", linewidth=1)
        top.set_ylabel("Value / initial capital (100)")
        top.legend(loc="upper left", fontsize=8, ncol=2)
        for key, label, color in (("drawdown", "Strategy", "#155e75"),
                ("benchmark_drawdown", "Buy and hold", "#c05621")):
            bottom.plot(x, [v * 100 for v in data[key]], color=color, label=label, linewidth=1.5)
        bottom.axhline(0, color="#94a3b8", linewidth=.7)
        bottom.set_ylim(min(-.1, min(data["drawdown"] + data["benchmark_drawdown"]) * 100) * 1.08, 0)
        bottom.set_ylabel("Drawdown (%)")
        ticks = sorted({round(i * (len(x) - 1) / 4) for i in range(5)})
        for axes in (top, bottom):
            axes.set_facecolor("white")
            axes.grid(axis="y", color="#e2e8f0", linewidth=.7)
            axes.set_xticks(ticks, [data["dates"][i].isoformat() for i in ticks], fontsize=8)
            axes.ticklabel_format(axis="y", style="sci", scilimits=(-3, 5), useOffset=False, useMathText=False)
            for spine in axes.spines.values():
                spine.set_edgecolor("#cbd5e1")
        bottom.set_xlabel("Observed sessions (equal spacing; no missing sessions invented)", fontsize=9)
        identity = data["identity"]
        synthetic = identity["source_kind"] == "demo"
        label = "SYNTHETIC DEMO" if synthetic else "DECLARED DATA / NOT INDEPENDENTLY VERIFIED"
        figure.text(.09, .94, "Invest | saved research case " + str(case_index + 1), fontsize=18, weight="bold", color="#123047")
        figure.text(.09, .895, f"{data['symbol']}   |   {data['dates'][0]} to {data['dates'][-1]}   |   Initial CNY {data['initial']:,.2f}", fontsize=10)
        figure.text(.09, .85, label + "  /  EXPLORATORY ONLY", fontsize=10, weight="bold", color="#9a3412")
        strategy, costs = identity["strategy"], identity["demonstration_costs"]
        study_type = "Rolling window" if identity["mode"] == "EXPLORATORY_WALK_FORWARD" else "Chronological slice"
        figure.text(.09, .815, f"{study_type} | MA {strategy['fast']}/{strategy['slow']} | Commission {costs['commission_rate']*100:g}% (min CNY {costs['min_commission']:g}) | Tax {costs['stamp_tax_rate']*100:g}% | Transfer {costs['transfer_fee_rate']*100:g}% | Slippage {costs['slippage_bps']:g} bps", fontsize=8)
        figure.text(.09, .125, "Drawdown includes initial capital. Costs are saved demonstration assumptions. No forced terminal sale.", fontsize=8)
        figure.text(.09, .098, "Frozen holdout unopened. Arithmetic evidence is not market validation or a forecast.", fontsize=8)
        figure.text(.09, .063, f"Study {identity['study_id'][:16]}   |   Protocol {identity['protocol_id'][:16]}   |   Case {case_index} (zero-based)", fontsize=8)
        figure.text(.09, .038, f"Dataset {identity['dataset_id'][:16]}   |   Curve {identity['curve_sha256'][:16]}   |   Full identity in PNG metadata", fontsize=8)
        # Explicitly disable inherited TeX and math parsing on every text artist.
        # No study free text is drawn; descriptors are preserved as inert JSON metadata.
        for text in figure.findobj(match=Text):
            text.set_usetex(False)
            text.set_parse_math(False)
            text.set_fontfamily("DejaVu Sans")
        output = io.BytesIO()
        canvas.print_png(output, metadata={"Software": "Invest / Matplotlib " + version,
            "Description": canonical(identity), "Disclaimer": label + "; exploratory only; not investment advice"})
        return output.getvalue()
    finally:
        _RENDER_LOCK.release()
