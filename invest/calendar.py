"""Trading-session helpers with an optional exchange-calendar backend."""
from __future__ import annotations
import pandas as pd

def trading_sessions(start, end, calendar: str = "SSE") -> pd.DatetimeIndex:
    """Return exchange sessions, falling back to business days when optional deps are absent."""
    try:
        import pandas_market_calendars as mcal
        schedule = mcal.get_calendar(calendar).schedule(start_date=start, end_date=end)
        return pd.DatetimeIndex(schedule.index).tz_localize(None)
    except (ImportError, ModuleNotFoundError, ValueError):
        return pd.bdate_range(start=start, end=end)
