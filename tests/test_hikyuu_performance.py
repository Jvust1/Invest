import unittest

from invest.hikyuu_performance import HikyuuPerformanceAdapter


class FakePerformance:
    def to_dict(self):
        return {
            "Account CAGR %": 12.5,
            "Win Rate %": 58.0,
            "Profit Factor": 1.42,
            "Current Total Assets": 512.3,
            "ignored": "text",
            "bad": float("nan"),
        }


class FakeTradeManager:
    def __init__(self):
        self.kwargs = None

    def get_performance(self, **kwargs):
        self.kwargs = kwargs
        return FakePerformance()


class HikyuuPerformanceAdapterTests(unittest.TestCase):
    def test_snapshot_normalizes_selected_metrics(self):
        tm = FakeTradeManager()
        result = HikyuuPerformanceAdapter(module=object()).snapshot(
            tm,
            datetime="2026-09-30",
            ktype="DAY",
            ext=False,
        )
        self.assertEqual(tm.kwargs["datetime"], "2026-09-30")
        self.assertEqual(tm.kwargs["ktype"], "DAY")
        self.assertFalse(tm.kwargs["ext"])
        self.assertEqual(result.normalized["account_cagr_pct"], 12.5)
        self.assertEqual(result.normalized["win_rate_pct"], 58.0)
        self.assertEqual(result.normalized["profit_factor"], 1.42)
        self.assertNotIn("bad", result.metrics)
        self.assertNotIn("ignored", result.metrics)

    def test_missing_trade_manager_contract_fails_closed(self):
        with self.assertRaises(TypeError):
            HikyuuPerformanceAdapter(module=object()).snapshot(object())


if __name__ == "__main__":
    unittest.main()
