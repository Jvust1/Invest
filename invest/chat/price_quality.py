"""Bounded, offline quality checks for explicitly supplied historical OHLC bars.

This module never fetches a source URL, reads a path, writes a file, or supplies a
fallback for a failed market-data request. A source is a declaration, not proof.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import math
import re
import statistics
from typing import Any


SHANGHAI = timezone(timedelta(hours=8))
ADJUSTMENTS = frozenset({
    "unknown", "unadjusted", "split_adjusted", "total_return_adjusted",
    "forward_adjusted", "backward_adjusted",
})
PRICE_MIN = 1e-8
PRICE_MAX = 1e12
VOLUME_MAX = 1e18
WEALTH_RELATIVE_TOLERANCE = 1e-10


def _day(value: Any, label: str) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError(f"{label} must be canonical YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{label} must be a valid calendar date") from None
    if parsed > datetime.now(SHANGHAI).date():
        raise ValueError(f"{label} must not be in the future (Asia/Shanghai)")
    return parsed


def _number(value: Any, label: str, *, lower: float, upper: float) -> float:
    # JSON numbers only: bool, numeric strings, Decimal, and NaN are not quotes.
    if type(value) not in (int, float):
        raise ValueError(f"{label} must be a JSON number, not boolean or text")
    # Check the original integer before conversion (1e18 + 1 rounds to 1e18 as
    # a float and must not bypass the volume upper bound).
    if not lower <= value <= upper:
        raise ValueError(f"{label} must be finite and within [{lower}, {upper}]")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{label} is outside numeric bounds") from None
    if not math.isfinite(result) or not lower <= result <= upper:
        raise ValueError(f"{label} must be finite and within [{lower}, {upper}]")
    return result


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False,
                         separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _check_wealth_reconstruction(rows: list[dict[str, Any]], returns: list[float]) -> None:
    """Reject cancellation loss before using return-based wealth/risk formulas.

    Subtracting one from a very small price ratio, then adding it back, can
    invent wealth despite all values remaining finite. Check *every* NAV point,
    not just the endpoint: opposite errors can cancel at the endpoint while
    corrupting intervening peaks/drawdowns. Zero absolute tolerance protects
    tiny but valid relative prices from being treated as approximately zero.
    """
    wealth = 1.0
    first_close = rows[0]["close"]
    for row, simple_return in zip(rows[1:], returns):
        wealth *= 1 + simple_return
        price_nav = row["close"] / first_close
        if not math.isfinite(wealth) or not math.isclose(
                wealth, price_nav, rel_tol=WEALTH_RELATIVE_TOLERANCE, abs_tol=0.0):
            raise ValueError("return-based wealth diverges from the supplied price path")


def analyze_price_series(
    symbol: str,
    bars: list[dict],
    currency: str,
    source: str,
    as_of: str,
    adjustment: str = "unknown",
    max_staleness_days: int = 7,
) -> dict[str, Any]:
    """Describe caller-supplied data; do not independently verify it or trade.

    ``symbol`` is an ASCII label of 1-40 letters/digits or ``._:/^=-`` (first
    character a letter, digit, or ``^``), not a validated exchange identifier.
    ``currency`` is three uppercase ASCII letters, not verified legal tender.
    ``source`` is 1-300 printable Unicode characters with no surrounding spaces;
    it can name a provider, document, or URL, but is never dereferenced.
    Each of 1-5000 bars contains only date/open/high/low/close and optional volume.
    Prices are JSON numbers in [1e-8, 1e12]; volume is in [0, 1e18], with its unit
    deliberately unverified. Dates are increasing canonical days, <= as_of, and
    not future Shanghai dates. Staleness is measured in calendar days (0-3660).
    ``adjustment`` is one of ADJUSTMENTS and is only a caller declaration.

    Hashes use canonical UTF-8 JSON after numeric normalization to float. Historical
    risk requires at least two close-to-close returns and assumes 252 observations
    per year; it does not certify trading-day completeness or investment results.
    Risk is omitted if reconstructed wealth differs from the relative price at
    any bar by more than 1e-10 relative tolerance (zero absolute tolerance).
    """
    if not isinstance(symbol, str) or not re.fullmatch(r"[A-Za-z0-9^][A-Za-z0-9._:/^=\-]{0,39}", symbol):
        raise ValueError("symbol must be a 1-40 character ASCII market label")
    if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
        raise ValueError("currency must be three uppercase ASCII letters")
    if (not isinstance(source, str) or not 1 <= len(source) <= 300
            or source != source.strip() or not source.isprintable()):
        raise ValueError("source must be 1-300 printable characters without surrounding whitespace")
    if not isinstance(adjustment, str) or adjustment not in ADJUSTMENTS:
        raise ValueError("adjustment must be one of: " + ", ".join(sorted(ADJUSTMENTS)))
    if type(max_staleness_days) is not int or not 0 <= max_staleness_days <= 3660:
        raise ValueError("max_staleness_days must be an integer from 0 to 3660")
    cutoff = _day(as_of, "as_of")
    if not isinstance(bars, list) or not 1 <= len(bars) <= 5000:
        raise ValueError("bars must contain 1-5000 observations")

    rows: list[dict[str, Any]] = []
    days: list[date] = []
    required = {"date", "open", "high", "low", "close"}
    volume_count = 0
    for index, bar in enumerate(bars):
        if (not isinstance(bar, dict) or not required <= set(bar)
                or set(bar) - required - {"volume"}):
            raise ValueError(f"bar {index} requires only date/open/high/low/close and optional volume")
        current = _day(bar["date"], f"bar {index} date")
        if current > cutoff or (days and current <= days[-1]):
            raise ValueError("bar dates must be strictly increasing and <= as_of")
        row: dict[str, Any] = {"date": current.isoformat()}
        for field in ("open", "high", "low", "close"):
            row[field] = _number(bar[field], f"bar {index} {field}", lower=PRICE_MIN, upper=PRICE_MAX)
        if not row["low"] <= min(row["open"], row["close"]) <= max(row["open"], row["close"]) <= row["high"]:
            raise ValueError(f"bar {index} must satisfy low <= open/close <= high")
        if "volume" in bar:
            row["volume"] = _number(bar["volume"], f"bar {index} volume", lower=0, upper=VOLUME_MAX)
            volume_count += 1
        rows.append(row)
        days.append(current)

    warnings: list[dict[str, str]] = []

    def warn(code: str, message: str) -> None:
        warnings.append({"code": code, "message": message})

    age = (cutoff - days[-1]).days
    if age > max_staleness_days:
        warn("STALE_DATA", "Latest observation exceeds the declared calendar-day staleness threshold.")
    gaps = [(later - earlier).days for earlier, later in zip(days, days[1:])]
    gap_count = sum(gap > 1 for gap in gaps)
    if gap_count:
        warn("CALENDAR_GAPS", "Calendar gaps are not proof of missing trading days; holidays and suspensions were not checked.")
    if adjustment == "unknown":
        warn("ADJUSTMENT_UNKNOWN", "Split/dividend adjustment is unknown; price changes may not be investment returns.")
    elif adjustment == "unadjusted":
        warn("UNADJUSTED_PRICES", "Unadjusted prices may include split/dividend effects and are not total returns.")
    else:
        warn("ADJUSTMENT_UNVERIFIED", "The caller's adjustment declaration and corporate-action treatment were not verified.")
    warn("LICENSE_UNVERIFIED", "A source label does not verify permission, redistribution rights, or a market-data license.")
    warn("SOURCE_UNVERIFIED", "Data and source are caller supplied; no independent source, timestamp, or currency verification occurred.")
    if volume_count:
        warn("VOLUME_UNIT_UNVERIFIED", "Volume units and trading-volume accuracy are unverified; volume is not a liquidity guarantee.")
    if 0 < volume_count < len(rows):
        warn("PARTIAL_VOLUME", "Volume is present for only part of the supplied series.")

    returns = [later["close"] / earlier["close"] - 1
               for earlier, later in zip(rows, rows[1:])]
    risk = None
    risk_status = "INSUFFICIENT_RETURNS"
    if len(returns) >= 2:
        # Lazy import keeps service free to expose this module as a tool wrapper.
        from .service import _metrics
        try:
            _check_wealth_reconstruction(rows, returns)
            risk = _metrics(returns, 252)
        except (ValueError, OverflowError, ZeroDivisionError):
            risk_status = "NUMERIC_RANGE_EXCEEDED"
            warn("RISK_NUMERIC_RANGE", "Finite input prices produced numerically unstable risk statistics; no estimate is reported.")
        else:
            if all(value is None or math.isfinite(value) for value in risk.values()):
                risk_status = "DESCRIPTIVE_ONLY"
            else:
                risk = None
                risk_status = "NUMERIC_RANGE_EXCEEDED"
                warn("RISK_NUMERIC_RANGE", "Derived risk statistics are non-finite; no estimate is reported.")
    else:
        warn("INSUFFICIENT_RETURNS", "At least three bars (two returns) are required for the historical-risk summary.")
    if returns:
        warn("ANNUALIZATION_ASSUMPTION", "Risk uses 252 supplied observations per year, not a verified exchange calendar; irregular spacing can distort annualization.")

    metadata = {"symbol": symbol, "currency": currency, "source": source,
                "as_of": as_of, "adjustment": adjustment,
                "max_staleness_days": max_staleness_days}
    return {
        "schema": "invest-caller-price-quality-v1", "status": "CALLER_SUPPLIED",
        **metadata, "observations": len(rows),
        "start_date": rows[0]["date"], "end_date": rows[-1]["date"],
        "latest_observation": rows[-1]["date"], "days_since_latest": age,
        "stale": age > max_staleness_days,
        "data_sha256": _digest(rows), "request_sha256": _digest({**metadata, "bars": rows}),
        "data_hash_encoding": "UTF-8 canonical JSON; sorted keys; normalized float prices/volume",
        "calendar_gaps": {"count": gap_count, "max_gap_days": max(gaps, default=0),
                          "exchange_calendar_checked": False},
        "volume_observations": volume_count,
        "close_to_close": {
            "observations": len(returns),
            "total_price_return": rows[-1]["close"] / rows[0]["close"] - 1 if returns else None,
            "latest_return": returns[-1] if returns else None,
            "minimum_return": min(returns) if returns else None,
            "maximum_return": max(returns) if returns else None,
            "mean_return": statistics.mean(returns) if returns else None,
            "is_total_return_verified": False,
        },
        "historical_risk": {"status": risk_status, "annualization": 252, "metrics": risk,
                            "engine": "native-reference-formulas", "initial_wealth_in_drawdown": True},
        "independently_verified": False, "real_time": False,
        "executable_quote": False, "execution_authorized": False,
        "automatic_orders_supported": False, "implicit_fallback": False,
        "warnings": warnings,
        "limitations": [
            "Input shape checks do not establish authenticity, completeness, adjustment correctness, or predictive value.",
            "Historical in-sample descriptive statistics are not forecasts or evidence of a profitable strategy.",
            "Zero risk-free/target rates; undefined Sharpe/Sortino are null, not zero.",
            "No orders, live quotes, FX conversion, fees, slippage, tax, exchange calendar or point-in-time verification.",
        ],
    }
