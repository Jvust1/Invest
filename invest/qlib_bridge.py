"""Small Qlib interoperability bridge; Qlib remains an optional dependency."""
from __future__ import annotations
import pandas as pd

def to_qlib_frame(history: pd.DataFrame, instrument: str = "unknown") -> pd.DataFrame:
    """Convert OHLCV rows into Qlib's (instrument, datetime) index shape."""
    required = {"open", "high", "low", "close", "volume"}
    missing = required.difference(history.columns)
    if missing:
        raise ValueError(f"history is missing columns: {sorted(missing)}")
    frame = history.copy()
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "datetime"
    frame["instrument"] = instrument
    frame = frame.reset_index().set_index(["instrument", "datetime"]).sort_index()
    return frame[["open", "high", "low", "close", "volume"]]

def load_qlib_features(instruments, fields, start_time, end_time, provider_uri=None):
    """Read features through Qlib's data API when pyqlib is installed."""
    try:
        import qlib
        from qlib.data import D
    except (ImportError, ModuleNotFoundError) as exc:
        raise RuntimeError("Qlib is optional; install the 'qlib' extra to load features") from exc
    if provider_uri:
        from qlib.config import REG_CN
        qlib.init(provider_uri=provider_uri, region=REG_CN)
    return D.features(instruments, fields, start_time, end_time)
