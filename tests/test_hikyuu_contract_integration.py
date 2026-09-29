"""Real Hikyuu synthetic in-memory data and fee primitive contract."""
import importlib.util
import unittest

from invest.independent_engines import hikyuu_synthetic_contract


@unittest.skipUnless(importlib.util.find_spec("hikyuu"), "Hikyuu optional dependency required")
class HikyuuContractIntegrationTests(unittest.TestCase):
    def test_temporary_bars_and_etf_minimum_commission(self):
        result = hikyuu_synthetic_contract()
        self.assertEqual(result["backend"], "hikyuu")
        self.assertEqual(result["backend_version"], "2.8.2")
        self.assertEqual(result["sessions"], 3)
        self.assertEqual(result["close_values"], [1.90, 1.93, 1.87])
        self.assertAlmostEqual(result["fee_probe"]["backend_total_cost_cny"], 5.0, places=12)


if __name__ == "__main__":
    unittest.main()
