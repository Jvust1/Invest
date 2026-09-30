import pandas as pd

from invest.calendar import exchange_sessions
from invest.skfolio_adapter import skfolio_weights

def test_exchange_sessions_have_sorted_dates():
    sessions = exchange_sessions("2026-01-01", "2026-01-10")
    assert len(sessions) >= 5
    assert sessions.is_monotonic_increasing

def test_skfolio_weights_fallback_is_normalized():
    returns = pd.DataFrame({"a": [0.01, -0.01, 0.02], "b": [0.02, 0.01, -0.01]})
    weights = skfolio_weights(returns)
    assert set(weights) == {"a", "b"}
    assert abs(sum(weights.values()) - 1.0) < 1e-9
