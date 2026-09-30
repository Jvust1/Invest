"""FinRL data and observation bridge."""
from __future__ import annotations

import numpy as np
import pandas as pd

_REQUIRED = {"open", "high", "low", "close", "volume"}

def to_finrl_frame(history: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Convert indexed OHLCV data to FinRL's date/tic long-table schema."""
    missing = _REQUIRED.difference(history.columns)
    if missing:
        raise ValueError(f"history is missing columns: {sorted(missing)}")
    frame = history.copy()
    frame.index = pd.to_datetime(frame.index)
    frame.index.name = "date"
    frame["tic"] = ticker
    return frame.reset_index()[["date", "tic", "open", "high", "low", "close", "volume"]].sort_values(["date", "tic"])

def finrl_observation(frame: pd.DataFrame, fields=("close", "volume")) -> np.ndarray:
    """Create one row per date with deterministic ticker/field column ordering."""
    required = {"date", "tic", *fields}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"frame is missing columns: {sorted(missing)}")
    data = frame.copy()
    data["date"] = pd.to_datetime(data["date"])
    data = data.sort_values(["date", "tic"])
    matrices = []
    for field in fields:
        matrices.append(data.pivot(index="date", columns="tic", values=field).sort_index(axis=1))
    return pd.concat(matrices, axis=1).sort_index().to_numpy(dtype=float)
