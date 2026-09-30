import unittest
import numpy as np
import pandas as pd

from invest import (
    add_stockstats_features,
    minimum_variance_weights,
    risk_report,
)

class HighStarAdapterTests(unittest.TestCase):
    def setUp(self):
        index = pd.date_range("2026-01-01", periods=40, freq="D")
        base = np.linspace(100, 120, len(index))
        self.prices = pd.DataFrame({
            "AAA": base,
            "BBB": base[::-1] + 140,
            "CCC": base * 0.8 + 20,
        }, index=index)
        self.ohlcv = pd.DataFrame({
            "open": base,
            "high": base + 1,
            "low": base - 1,
            "close": base + np.sin(np.arange(len(index))),
            "volume": np.arange(len(index)) + 100,
        }, index=index)

    def test_inverse_variance_allocation_is_normalized(self):
        weights = minimum_variance_weights(self.prices)
        self.assertAlmostEqual(sum(weights.values()), 1.0, places=6)
        self.assertEqual(set(weights), set(self.prices.columns))

    def test_risk_report_has_core_metrics(self):
        report = risk_report(self.prices["AAA"].pct_change().dropna())
        self.assertEqual(set(report), {
            "total_return", "annualized_return", "annualized_volatility",
            "max_drawdown", "sharpe", "sortino"
        })

    def test_stockstats_features_are_added(self):
        features = add_stockstats_features(self.ohlcv)
        self.assertIn("rsi_14", features)
        self.assertIn("macd", features)
        self.assertIn("boll", features)

if __name__ == "__main__":
    unittest.main()
