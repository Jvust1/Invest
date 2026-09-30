import unittest
import pandas as pd
from invest import moving_average_signal, run_backtest

class PipelineContractTests(unittest.TestCase):
    def test_signal_and_backtest_have_same_index(self):
        prices = pd.Series(
            [100, 101, 99, 102, 104, 103, 106],
            index=pd.date_range("2026-01-01", periods=7, freq="D"),
        )
        result = run_backtest(prices, moving_average_signal(prices, 2, 3), fee_bps=5)
        self.assertEqual(result.index.tolist(), prices.index.tolist())
        self.assertEqual(len(result), len(prices))
        self.assertTrue((result["equity"] > 0).all())

    def test_negative_fee_is_rejected(self):
        with self.assertRaises(ValueError):
            run_backtest(pd.Series([1.0, 1.1]), pd.Series([0, 1]), fee_bps=-1)

if __name__ == "__main__":
    unittest.main()
