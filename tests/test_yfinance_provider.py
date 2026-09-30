import pandas as pd

from invest.providers.yfinance_ohlcv import normalize_yfinance_ohlcv

def test_normalize_yfinance_ohlcv():
    data = pd.DataFrame(
        {"Open": [1], "High": [2], "Low": [0.5], "Close": [1.5], "Volume": [100]},
        index=pd.DatetimeIndex(["2024-01-01"]),
    )
    frame = normalize_yfinance_ohlcv(data)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert frame.iloc[0]["close"] == 1.5
