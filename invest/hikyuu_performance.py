"""Optional Hikyuu performance snapshot adapter.

Upstream: fasiondog/hikyuu @
daeb2c792a2095178fd5af051eda76d1b23e96c6 (Apache-2.0).

This adapter is research-only. It reads TradeManager.get_performance() output
and normalizes selected metrics; it does not create orders or execution paths.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


_NORMALIZED_KEYS = {
    "Account CAGR %": "account_cagr_pct",
    "Account Avg Annual Return %": "account_avg_annual_return_pct",
    "Closed Trade Account Return %": "closed_trade_account_return_pct",
    "Open Position Account Return %": "open_position_account_return_pct",
    "Win Rate %": "win_rate_pct",
    "Profit Factor": "profit_factor",
    "Avg Win / Avg Loss Ratio": "avg_win_loss_ratio",
    "Total Closed Trades": "total_closed_trades",
    "Number of Winning Trades": "winning_trades",
    "Number of Losing Trades": "losing_trades",
    "Current Total Assets": "current_total_assets",
    "Cash Balance": "cash_balance",
}


@dataclass(frozen=True)
class HikyuuPerformanceSnapshot:
    metrics: dict[str, float]
    normalized: dict[str, float]


class HikyuuPerformanceAdapter:
    """Read a Hikyuu TradeManager performance object into stable dictionaries."""

    name = "hikyuu-performance"

    def __init__(self, module: Any | None = None) -> None:
        if module is None:
            try:
                import hikyuu as module
            except ImportError as exc:
                raise RuntimeError(
                    "Hikyuu is optional; install the independent-hikyuu extra"
                ) from exc
        self._module = module

    def snapshot(
        self,
        trade_manager: Any,
        *,
        datetime: Any | None = None,
        ktype: Any | None = None,
        ext: bool = False,
    ) -> HikyuuPerformanceSnapshot:
        getter = getattr(trade_manager, "get_performance", None)
        if not callable(getter):
            raise TypeError("trade_manager must provide get_performance()")

        kwargs: dict[str, Any] = {"ext": bool(ext)}
        if datetime is not None:
            kwargs["datetime"] = datetime
        if ktype is not None:
            kwargs["ktype"] = ktype

        performance = getter(**kwargs)
        to_dict = getattr(performance, "to_dict", None)
        if not callable(to_dict):
            raise TypeError("Hikyuu Performance must provide to_dict()")
        raw = to_dict()
        if not isinstance(raw, Mapping):
            raise TypeError("Hikyuu Performance.to_dict() must return a mapping")

        metrics: dict[str, float] = {}
        for key, value in raw.items():
            if isinstance(value, bool):
                continue
            try:
                number = float(value)
            except (TypeError, ValueError, OverflowError):
                continue
            if math.isfinite(number):
                metrics[str(key)] = number

        normalized = {
            target: metrics[source]
            for source, target in _NORMALIZED_KEYS.items()
            if source in metrics
        }
        return HikyuuPerformanceSnapshot(metrics=metrics, normalized=normalized)


def create_hikyuu_performance_adapter() -> HikyuuPerformanceAdapter:
    return HikyuuPerformanceAdapter()
