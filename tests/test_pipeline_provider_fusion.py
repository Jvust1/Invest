import unittest
import pandas as pd

from invest.pipeline import run_a_share_sma_backtest


class FakeProvider:
    def __init__(self):
        self.calls = []

    def history(self, **kwargs):
        self.calls.append(kwargs)
        idx = pd.date_range("2026-01-01", periods=80, freq="D")
        values = [10 + i * 0.05 for i in range(80)]
        return pd.DataFrame({"close": values}, index=idx)


class PipelineProviderFusionTests(unittest.TestCase):
    def test_injected_provider_runs_end_to_end_without_network(self):
        provider = FakeProvider()
        result, summary = run_a_share_sma_backtest(
            "600000",
            start_date="20260101",
            end_date="20260331",
            fast=5,
            slow=20,
            provider="akshare",
            provider_instance=provider,
        )
        self.assertEqual(provider.calls[0]["symbol"], "600000")
        self.assertIn("equity", result.columns)
        self.assertIn("total_return", summary)

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(ValueError):
            run_a_share_sma_backtest("600000", provider="unknown")


if __name__ == "__main__":
    unittest.main()
