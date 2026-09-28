import copy
import unittest
from decimal import Decimal
from invest.allocation import size_allocation


def scenario():
    return {"cash_cny": "500.00", "reserve_cny": "100.00", "as_of": "2026-09-28",
        "data_scope": "PUBLIC_RESEARCH_ONLY", "max_entry_fee_fraction": "0.05",
        "candidates": [{"symbol": "DEMO.ETF", "target_weight": "1", "price_cny": "1.90",
            "quote_date": "2026-09-25", "quote_source": "explicit test quote", "rule_date": "2026-09-25",
            "rule_source": "explicit test rule", "buy_lot_shares": 100, "max_buy_shares": 300,
            "commission_rate": "0.0003", "min_commission_cny": "5.00",
            "transfer_fee_rate": "0", "sell_tax_rate": "0"}]}


class AllocationTests(unittest.TestCase):
    def test_two_lots_preserve_cash_and_charge_minimum_once(self):
        result = size_allocation(scenario())
        self.assertEqual(result["candidates"][0]["quantity_shares"], 200)
        self.assertEqual(result["spent_cny"], "385.00")
        self.assertEqual(result["remaining_cash_cny"], "115.00")
        self.assertEqual(result["candidates"][0]["entry_fees_cny"], "5.00")
        self.assertEqual(result["status"], "SCENARIO_ONLY")

    def test_impossible_lot_keeps_all_cash(self):
        case = scenario()
        case["candidates"][0]["price_cny"] = "6.00"
        result = size_allocation(case)
        self.assertEqual(result["spent_cny"], "0")
        self.assertEqual(result["remaining_cash_cny"], "500.00")

    def test_fee_threshold_and_liquidity_can_block(self):
        case = scenario()
        case["max_entry_fee_fraction"] = "0.01"
        self.assertEqual(size_allocation(case)["spent_cny"], "0")
        case = scenario()
        case["candidates"][0]["max_buy_shares"] = 99
        self.assertEqual(size_allocation(case)["spent_cny"], "0")

    def test_multiasset_never_overspends_or_breaks_lots(self):
        case = scenario()
        first = case["candidates"][0]
        first["target_weight"] = "0.5"
        second = copy.deepcopy(first)
        second["symbol"] = "OTHER.ETF"
        second["price_cny"] = "1.50"
        case["candidates"].append(second)
        result = size_allocation(case)
        self.assertLessEqual(sum(Decimal(a["total_cash_required_cny"]) for a in result["candidates"]), Decimal("400"))
        self.assertTrue(all(a["quantity_shares"] % a["buy_lot_shares"] == 0 for a in result["candidates"]))
        self.assertGreaterEqual(Decimal(result["remaining_cash_cny"]), Decimal("100"))

    def test_missing_invalid_or_future_market_facts_fail_closed(self):
        for key, value in [("price_cny", "NaN"), ("buy_lot_shares", 0),
            ("min_commission_cny", None), ("quote_date", "2026-09-29"), ("rule_source", "")]:
            with self.subTest(key=key):
                case = scenario()
                case["candidates"][0][key] = value
                with self.assertRaises(ValueError):
                    size_allocation(case)

    def test_no_execution_scope_or_duplicate_symbol(self):
        case = scenario()
        case["data_scope"] = "EXECUTION_READY"
        with self.assertRaises(ValueError):
            size_allocation(case)
        case = scenario()
        case["candidates"].append(copy.deepcopy(case["candidates"][0]))
        with self.assertRaises(ValueError):
            size_allocation(case)


if __name__ == "__main__":
    unittest.main()
