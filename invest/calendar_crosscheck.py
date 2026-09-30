"""Independent Shanghai exchange session comparison for public research.

Session calendars say nothing about security-specific suspension or execution.
"""
from __future__ import annotations

from datetime import date
from importlib.metadata import version


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


def _exchange_sessions(start, end):
    try:
        import exchange_calendars as xcals
    except ImportError as exc:
        raise RuntimeError("缺少 exchange_calendars 可选依赖") from exc
    calendar = xcals.get_calendar("XSHG", start=start, end=end)
    return {timestamp.date().isoformat() for timestamp in calendar.sessions}, version("exchange_calendars")


def _pandas_sessions(start, end):
    try:
        import pandas_market_calendars as mcal
    except ImportError as exc:
        raise RuntimeError("缺少 pandas_market_calendars 可选依赖") from exc
    calendar = mcal.get_calendar("SSE")
    return {timestamp.date().isoformat() for timestamp in calendar.valid_days(start, end)}, version("pandas_market_calendars")


def crosscheck_shanghai_sessions(*, start: str, end: str, as_of: str,
                                 observed_dates: list[str], data_scope: str) -> dict:
    """Compare two declared exchange calendars and supplied observation dates."""
    start, end, as_of = _day(start), _day(end), _day(as_of)
    if not start <= end <= as_of or (date.fromisoformat(end) - date.fromisoformat(start)).days > 366:
        raise ValueError("日期区间不得倒序、超过方案日或超过366天")
    if data_scope != "PUBLIC_RESEARCH_ONLY":
        raise ValueError("只接受 PUBLIC_RESEARCH_ONLY 输入")
    if not isinstance(observed_dates, list) or len(observed_dates) > 367:
        raise ValueError("观测日期须为列表")
    observed = [_day(day) for day in observed_dates]
    if observed != sorted(set(observed)) or any(day < start or day > end for day in observed):
        raise ValueError("观测日期须递增、无重复并位于请求区间")
    first, first_version = _exchange_sessions(start, end)
    second, second_version = _pandas_sessions(start, end)
    if not first or not second:
        status = "NO_COMMON_CALENDAR_COVERAGE"
    elif first != second:
        status = "CALENDAR_DISAGREEMENT"
    elif set(observed) - first:
        status = "OBSERVATIONS_OUTSIDE_SESSIONS"
    elif first - set(observed):
        status = "OBSERVATIONS_INCOMPLETE"
    else:
        status = "MATCHED_SESSIONS"
    return {"schema": "invest-shanghai-calendar-crosscheck-v1",
        "status": status, "data_scope": data_scope, "exchange": "Shanghai",
        "start": start, "end": end, "as_of": as_of,
        "libraries": {"exchange_calendars": {"calendar": "XSHG", "version": first_version},
                      "pandas_market_calendars": {"calendar": "SSE", "version": second_version}},
        "exchange_calendars_only": sorted(first - second),
        "pandas_market_calendars_only": sorted(second - first),
        "observed_outside_both": sorted(set(observed) - first - second),
        "observed_outside_first": sorted(set(observed) - first),
        "observed_outside_second": sorted(set(observed) - second),
        "unobserved_joint_sessions": sorted((first & second) - set(observed)),
        "observed_count": len(observed), "first_session_count": len(first),
        "second_session_count": len(second),
        "limitations": ["日历一致不证明个券当日未停牌或存在可成交盘口。",
            "缺失观测日不能据此推定停牌；需另行核对数据来源、公司行动和规则有效期。",
            "公开数据仍只用于描述性研究，不能升级为正式执行行情。"]}
