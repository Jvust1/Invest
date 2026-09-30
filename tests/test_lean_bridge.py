import unittest

from invest.lean_bridge import LeanResultAdapter, compare_with_invest


class LeanBridgeTests(unittest.TestCase):
    def test_normalize_statistics_percentages_and_charts(self):
        snapshot = LeanResultAdapter().normalize(
            {
                "Statistics": {
                    "Total Return": "12.50%",
                    "Sharpe Ratio": "1.25",
                    "Drawdown": "8.00%",
                    "Total Fees": "$12.34",
                },
                "Charts": {"Strategy Equity": {}, "Benchmark": {}},
            }
        )
        self.assertAlmostEqual(snapshot.metrics["total_return"], 0.125)
        self.assertAlmostEqual(snapshot.metrics["sharpe"], 1.25)
        self.assertAlmostEqual(snapshot.metrics["max_drawdown"], 0.08)
        self.assertEqual(snapshot.chart_names, ("Benchmark", "Strategy Equity"))

    def test_compare_only_overlapping_metrics(self):
        snapshot = LeanResultAdapter().normalize(
            {"Statistics": {"Sharpe Ratio": "1.00", "Total Return": "10%"}}
        )
        result = compare_with_invest(
            {"sharpe": 1.0, "total_return": 0.11, "other": 3.0},
            snapshot,
            tolerance=0.02,
        )
        self.assertEqual(result["overlap_count"], 2)
        self.assertTrue(result["metrics"]["sharpe"]["within_tolerance"])
        self.assertTrue(result["metrics"]["total_return"]["within_tolerance"])


if __name__ == "__main__":
    unittest.main()
