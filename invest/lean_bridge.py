"""QuantConnect LEAN result adapter for Invest cross-checks.

Upstream: QuantConnect/Lean @
570a11a12fbf579664010021881810c7ce968797 (Apache-2.0).

LEAN remains an external engine. Invest only imports completed backtest
statistics/charts into its own neutral comparison schema.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


_STAT_KEYS = {
    "Total Return": "total_return",
    "Annualized Return": "annualized_return",
    "Annual Standard Deviation": "annualized_volatility",
    "Sharpe Ratio": "sharpe",
    "Drawdown": "max_drawdown",
    "Total Fees": "total_fees",
}


def _number(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text:
        return None
    pct = text.endswith("%")
    if pct:
        text = text[:-1].strip()
    for symbol in ("$", "¥", "￥"):
        text = text.replace(symbol, "")
    try:
        result = float(text)
    except ValueError:
        return None
    return result / 100.0 if pct else result


@dataclass(frozen=True)
class LeanBacktestSnapshot:
    metrics: dict[str, float]
    raw_statistics: dict[str, Any]
    chart_names: tuple[str, ...]


class LeanResultAdapter:
    """Normalize LEAN BacktestResult-like mappings without importing LEAN."""

    name = "quantconnect-lean"

    def normalize(self, payload: Mapping[str, Any]) -> LeanBacktestSnapshot:
        if not isinstance(payload, Mapping):
            raise TypeError("payload must be a mapping")
        stats_raw = (
            payload.get("Statistics")
            or payload.get("statistics")
            or {}
        )
        if not isinstance(stats_raw, Mapping):
            raise ValueError("LEAN result statistics must be a mapping")

        metrics: dict[str, float] = {}
        for upstream, target in _STAT_KEYS.items():
            value = _number(stats_raw.get(upstream))
            if value is not None:
                metrics[target] = value

        charts = payload.get("Charts") or payload.get("charts") or {}
        if isinstance(charts, Mapping):
            chart_names = tuple(sorted(str(key) for key in charts))
        else:
            chart_names = ()

        return LeanBacktestSnapshot(
            metrics=metrics,
            raw_statistics=dict(stats_raw),
            chart_names=chart_names,
        )


def compare_with_invest(
    invest_summary: Mapping[str, float],
    lean_snapshot: LeanBacktestSnapshot,
    *,
    tolerance: float = 1e-6,
) -> dict[str, Any]:
    """Compare overlapping normalized metrics without declaring an engine winner."""
    if tolerance < 0:
        raise ValueError("tolerance cannot be negative")
    rows: dict[str, Any] = {}
    for key in sorted(set(invest_summary) & set(lean_snapshot.metrics)):
        left = float(invest_summary[key])
        right = float(lean_snapshot.metrics[key])
        delta = left - right
        rows[key] = {
            "invest": left,
            "lean": right,
            "delta": delta,
            "within_tolerance": abs(delta) <= tolerance,
        }
    return {
        "backend": "quantconnect-lean",
        "overlap_count": len(rows),
        "metrics": rows,
    }
