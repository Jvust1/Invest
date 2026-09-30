import numpy as np
import pandas as pd

from invest.finrl_bridge import finrl_observation, to_finrl_frame
from invest.vnpy_bridge import to_vnpy_records

def sample_frame():
    index = pd.date_range("2026-01-01", periods=2)
    return pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [0, 1], "close": [1.5, 2.5], "volume": [10, 20]}, index=index)

def test_vnpy_records_preserve_ohlcv():
    records = to_vnpy_records(sample_frame(), "000001")
    assert records[0]["symbol"] == "000001"
    assert records[1]["close_price"] == 2.5

def test_finrl_schema_and_observation():
    frame = to_finrl_frame(sample_frame(), "000001")
    assert list(frame.columns) == ["date", "tic", "open", "high", "low", "close", "volume"]
    obs = finrl_observation(frame, fields=("close", "volume"))
    assert obs.shape == (2, 2)
    assert np.allclose(obs[:, 0], [1.5, 2.5])
