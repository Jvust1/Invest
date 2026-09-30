"""Dependency-free integrity and accounting-difference tests."""
import copy
import unittest
from unittest.mock import patch

from invest.bt_replay import compare_allocation_replay


def fixture():
    request = {"cash_cny": "500.00", "reserve_cny": "100.00", "as_of": "2025-01-02",
               "data_scope": "PUBLIC_RESEARCH_ONLY", "max_entry_fee_fraction": "0.05",
               "candidates": [{"symbol": "DEMO.ETF", "target_weight": "1", "price_cny": "1.90",
                   "quote_date": "2025-01-02", "quote_source": "synthetic fixture",
                   "rule_date": "2025-01-02", "rule_source": "explicit test assumptions",
                   "buy_lot_shares": 100, "max_buy_shares": 300,
                   "commission_rate": "0.0003", "min_commission_cny": "5.00",
                   "transfer_fee_rate": "0.00002", "sell_tax_rate": "0"}]}
    history = {"data_scope": "PUBLIC_RESEARCH_ONLY", "source": "synthetic fixture",
               "price_basis": "UNADJUSTED_NO_CORPORATE_ACTIONS", "daily_prices": [
                   {"date": "2025-01-02", "prices_cny": {"DEMO.ETF": "1.90"}},
                   {"date": "2025-01-03", "prices_cny": {"DEMO.ETF": "2.00"}},
                   {"date": "2025-01-06", "prices_cny": {"DEMO.ETF": "1.80"}}]}
    return history, request


def known_replay():
    return {"version": "mock", "curve": [
        {"date": day, "cash_cny": "114.99", "equity_cny": equity,
         "fees_cny": fee, "positions": {"DEMO.ETF": 200}}
        for day, equity, fee in [("2025-01-02", "494.99", "5.01"),
                                 ("2025-01-03", "514.99", "0"),
                                 ("2025-01-06", "474.99", "0")]]}


class BtReplayContractTests(unittest.TestCase):
    @patch("invest.bt_replay._run_bt", return_value=None)
    def test_known_500_cny_cash_fees_and_holdings(self, backend):
        backend.return_value = known_replay()
        history, request = fixture()
        result = compare_allocation_replay(history, request, as_of="2025-01-06")
        self.assertEqual(result["comparison_status"], "AGREE")
        self.assertEqual(result["invest_curve"][-1]["equity_cny"], "474.99")
        self.assertEqual(result["invest_curve"][0]["fees_cny"], "5.01")
        self.assertEqual(len(result["history_sha256"]), 64)
        self.assertEqual(backend.call_args.args[3][0]["quantity_shares"], 200)
        self.assertEqual(result["status"], "SCENARIO_ONLY")

    @patch("invest.bt_replay._run_bt")
    def test_each_cash_equity_fee_and_position_difference_is_retained(self, backend):
        history, request = fixture()
        for field, wrong in [("cash_cny", "119.99"), ("equity_cny", "500"),
                             ("fees_cny", "0"), ("positions", {"DEMO.ETF": 199})]:
            with self.subTest(field=field):
                changed = known_replay()
                changed["curve"][0][field] = wrong
                backend.return_value = changed
                result = compare_allocation_replay(history, request, as_of="2025-01-06")
                self.assertEqual(result["comparison_status"], "DISAGREE")
                self.assertEqual(result["comparison"][0]["status"], "DISAGREE")
                self.assertEqual(result["comparison"][1]["status"], "AGREE")

    @patch("invest.bt_replay._run_bt")
    def test_bad_history_is_rejected_before_backend(self, backend):
        for change in (lambda h: h["daily_prices"][0]["prices_cny"].update({"DEMO.ETF": "1.91"}),
                       lambda h: h["daily_prices"][1]["prices_cny"].clear(),
                       lambda h: h["daily_prices"].reverse(),
                       lambda h: h["daily_prices"].append(copy.deepcopy(h["daily_prices"][-1])),
                       lambda h: h.update(price_basis="ADJUSTED"),
                       lambda h: h.update(data_scope="EXECUTION_READY"),
                       lambda h: h["daily_prices"][1]["prices_cny"].update({"DEMO.ETF": "NaN"})):
            history, request = fixture()
            change(history)
            with self.assertRaises(ValueError):
                compare_allocation_replay(history, request, as_of="2025-01-06")
        backend.assert_not_called()

    @patch("invest.bt_replay._run_bt")
    def test_future_allocation_or_observation_is_not_backfilled(self, backend):
        history, request = fixture()
        request["as_of"] = "2025-01-03"
        with self.assertRaises(ValueError):
            compare_allocation_replay(history, request, as_of="2025-01-06")
        history, request = fixture()
        with self.assertRaises(ValueError):
            compare_allocation_replay(history, request, as_of="2025-01-03")
        backend.assert_not_called()

    @patch("invest.bt_replay._run_bt", side_effect=RuntimeError("missing bt"))
    def test_missing_backend_does_not_return_reference_as_success(self, backend):
        history, request = fixture()
        with self.assertRaisesRegex(RuntimeError, "missing bt"):
            compare_allocation_replay(history, request, as_of="2025-01-06")

    @patch("invest.bt_replay._run_bt")
    def test_malformed_backend_fails_closed(self, backend):
        history, request = fixture()
        for change in (lambda r: r["curve"].pop(),
                       lambda r: r["curve"][0].update(cash_cny=float("nan")),
                       lambda r: r["curve"][0].update(positions={"DEMO.ETF": 1.5}),
                       lambda r: r["curve"][0].update(date="2025-01-01")):
            result = known_replay()
            change(result)
            backend.return_value = result
            with self.assertRaises(ValueError):
                compare_allocation_replay(history, request, as_of="2025-01-06")


if __name__ == "__main__":
    unittest.main()
