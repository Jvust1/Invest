import unittest
import pandas as pd
from invest import moving_average_signal, run_backtest, performance_summary

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

    def test_slice_summary_never_includes_prior_training_equity(self):
        result = pd.DataFrame({'strategy_return': [0.5, 0.1, -0.1],
                               'equity': [1.5, 1.65, 1.485]})
        summary = performance_summary(result.iloc[1:])
        self.assertAlmostEqual(summary['total_return'], -0.01)
        self.assertAlmostEqual(summary['max_drawdown'], -0.1)

    def test_summary_counts_initial_loss_and_bankruptcy(self):
        for returns, expected in [([-0.1, 0.0], -0.1), ([-1.0, 0.0], -1.0)]:
            with self.subTest(returns=returns):
                summary = performance_summary(pd.DataFrame({'strategy_return': returns}))
                self.assertAlmostEqual(summary['total_return'], expected)
                self.assertAlmostEqual(summary['max_drawdown'], expected)

    def test_summary_rejects_unknown_or_impossible_returns(self):
        for value in [float('nan'), float('inf'), -1.01]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                performance_summary(pd.DataFrame({'strategy_return': [value]}))

    def test_sharpe_uses_arithmetic_returns_not_compounded_cagr(self):
        summary = performance_summary(pd.DataFrame({'strategy_return': [0.1, -0.05]}), periods_per_year=2)
        self.assertAlmostEqual(summary['sharpe'], 1/3)
        self.assertAlmostEqual(summary['annualized_return'], 0.045)

if __name__ == "__main__":
    unittest.main()
