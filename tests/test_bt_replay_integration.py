"""Real bt accounting; synthetic prices are not market performance evidence."""
import copy
import importlib.util
import unittest
import warnings

from invest.bt_replay import compare_allocation_replay
from test_bt_replay import fixture


@unittest.skipUnless(importlib.util.find_spec("bt"), "bt optional dependency absent")
class RealBtReplayTests(unittest.TestCase):
    def setUp(self):
        import pandas as pd
        context = warnings.catch_warnings()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        warnings.simplefilter("error", pd.errors.ChainedAssignmentError)

    def test_real_bt_minimum_commission_and_cent_rounded_transfer_fee(self):
        history, request = fixture()
        result = compare_allocation_replay(history, request, as_of="2025-01-06")
        self.assertEqual(result["backend_version"], "1.2.3")
        self.assertEqual(result["comparison_status"], "AGREE")
        self.assertAlmostEqual(float(result["bt_curve"][0]["cash_cny"]), 114.99, places=6)
        self.assertAlmostEqual(float(result["bt_curve"][-1]["equity_cny"]), 474.99, places=6)
        self.assertEqual(result["bt_curve"][0]["positions"], {"DEMO.ETF": 200})
        self.assertEqual(len(result["bt_curve"]), 3)

    def test_real_bt_all_cash_when_one_lot_is_unaffordable(self):
        history, request = fixture()
        request["reserve_cny"] = "400.00"
        result = compare_allocation_replay(history, request, as_of="2025-01-06")
        self.assertEqual(result["comparison_status"], "AGREE")
        self.assertTrue(all(float(r["cash_cny"]) == 500 for r in result["bt_curve"]))
        self.assertTrue(all(float(r["fees_cny"]) == 0 for r in result["bt_curve"]))

    def test_real_bt_two_assets_with_different_fee_schedules(self):
        history, request = fixture()
        first = request["candidates"][0]
        first["target_weight"] = "0.5"
        second = copy.deepcopy(first)
        second.update(symbol="OTHER.ETF", target_weight="0.5", price_cny="1.50",
                      min_commission_cny="2.00", transfer_fee_rate="0.0001")
        request["candidates"].append(second)
        for row, price in zip(history["daily_prices"], ("1.50", "1.60", "1.40")):
            row["prices_cny"]["OTHER.ETF"] = price
        result = compare_allocation_replay(history, request, as_of="2025-01-06")
        self.assertEqual(result["comparison_status"], "AGREE")
        self.assertAlmostEqual(float(result["bt_curve"][0]["cash_cny"]), 152.98, places=6)
        self.assertAlmostEqual(float(result["bt_curve"][0]["fees_cny"]), 7.02, places=6)
        self.assertEqual(result["bt_curve"][0]["positions"], {"DEMO.ETF": 100, "OTHER.ETF": 100})


if __name__ == "__main__":
    unittest.main()
