import unittest

import pandas as pd

from invest.research_pipeline import run_a_share_research_bundle


class Provider:
    def history(self, **kwargs):
        idx = pd.date_range("2026-01-01", periods=8)
        return pd.DataFrame(
            {
                "high": [10,11,12,13,14,15,16,17],
                "low": [8,9,10,11,12,13,14,15],
                "close": [9,10,11,12,13,14,15,16],
            },
            index=idx,
        )


class Features:
    def transform(self, frame):
        result = frame.copy()
        result["ta_rsi_14"] = 50.0
        return result


class ResearchBundleTests(unittest.TestCase):
    def test_provider_features_and_backtest_are_fused(self):
        bundle = run_a_share_research_bundle(
            Provider(), "000001", feature_engineer=Features(), fast=2, slow=3
        )
        self.assertIn("ta_rsi_14", bundle.market.columns)
        self.assertIn("equity", bundle.backtest.columns)
        self.assertIn("max_drawdown", bundle.summary)

    def test_bad_feature_engineer_fails_closed(self):
        with self.assertRaises(TypeError):
            run_a_share_research_bundle(
                Provider(), "000001", feature_engineer=object(), fast=2, slow=3
            )


if __name__ == "__main__":
    unittest.main()
