import pandas as pd

from invest.calendar import trading_sessions
from invest.qlib_bridge import to_qlib_frame
from invest.riskfolio_adapter import riskfolio_weights

def test_trading_sessions_have_sorted_dates():
    sessions = trading_sessions("2026-01-01", "2026-01-10")
    assert len(sessions) >= 5
    assert sessions.is_monotonic_increasing

def test_to_qlib_frame_has_multiindex():
    index = pd.date_range("2026-01-01", periods=2)
    frame = pd.DataFrame({"open": [1, 2], "high": [2, 3], "low": [0, 1], "close": [1.5, 2.5], "volume": [10, 20]}, index=index)
    out = to_qlib_frame(frame, "000001.SZ")
    assert out.index.names == ["instrument", "datetime"]
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]

def test_riskfolio_weights_fallback_is_normalized():
    returns = pd.DataFrame({"a": [0.01, -0.01, 0.02], "b": [0.02, 0.01, -0.01]})
    weights = riskfolio_weights(returns)
    assert set(weights) == {"a", "b"}
    assert abs(sum(weights.values()) - 1.0) < 1e-9
