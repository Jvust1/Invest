import pandas as pd
import pytest
from invest import optimize_weights

def test_unified_optimizer_inverse_variance_engine():
    returns = pd.DataFrame({"a": [0.01, -0.01, 0.02], "b": [0.02, 0.01, -0.01]})
    weights = optimize_weights(returns, engine="inverse_variance")
    assert set(weights) == {"a", "b"}
    assert abs(sum(weights.values()) - 1.0) < 1e-9

def test_unified_optimizer_rejects_unknown_engine():
    with pytest.raises(ValueError):
        optimize_weights(pd.DataFrame({"a": [0.01, 0.02]}), engine="unknown")
