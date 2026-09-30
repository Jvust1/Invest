import pandas as pd

from invest.providers.ccxt_ohlcv import normalize_ccxt_ohlcv

def test_normalize_ccxt_ohlcv():
    frame = normalize_ccxt_ohlcv([[1704067200000, 1, 2, 0.5, 1.5, 100]])
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.index[0] == pd.Timestamp("2024-01-01")
    assert frame.iloc[0]["close"] == 1.5
