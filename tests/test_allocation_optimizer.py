import copy
import sys
import types
import unittest
from unittest.mock import patch

from invest.allocation_optimizer import min_variance_scenario
from test_allocation import scenario


def inputs():
    sizing = scenario()
    sizing["candidates"][0]["target_weight"] = "0"
    second = copy.deepcopy(sizing["candidates"][0])
    second["symbol"] = "SECOND.ETF"
    second["target_weight"] = "0"
    second["price_cny"] = "2.10"
    sizing["candidates"].append(second)
    history = {"data_scope": "PUBLIC_RESEARCH_ONLY", "source": "synthetic optimizer contract sample",
        "daily_returns": [{"date": f"2026-08-{d:02d}",
            "returns": {"DEMO.ETF": "0.01" if d % 2 else "-0.01",
                        "SECOND.ETF": "0.02" if d % 3 else "-0.02"}}
            for d in range(1, 31)]}
    return history, sizing


class OptimizerBridgeTests(unittest.TestCase):
    def test_weight_provenance_and_sizing_contract(self):
        history, sizing = inputs()
        with patch("invest.allocation_optimizer._weights_from_pypfopt", return_value=(
            {"DEMO.ETF": 0.6, "SECOND.ETF": 0.4}, "contract-stub")):
            result = min_variance_scenario(history, sizing)
        self.assertEqual(result["weights"], {"DEMO.ETF": "0.6", "SECOND.ETF": "0.4"})
        self.assertEqual(result["history_sessions"], 30)
        self.assertEqual(result["history_end"], "2026-08-30")
        self.assertEqual(result["allocation"]["status"], "SCENARIO_ONLY")
        self.assertGreaterEqual(float(result["allocation"]["remaining_cash_cny"]), 100)
        self.assertEqual(len(result["history_sha256"]), 64)

    def test_future_data_and_misaligned_columns_rejected_before_backend(self):
        history, sizing = inputs()
        history["daily_returns"][-1]["date"] = "2026-09-29"
        with patch("invest.allocation_optimizer._weights_from_pypfopt") as backend:
            with self.assertRaises(ValueError):
                min_variance_scenario(history, sizing)
            backend.assert_not_called()
        history, sizing = inputs()
        del history["daily_returns"][0]["returns"]["SECOND.ETF"]
        with self.assertRaises(ValueError):
            min_variance_scenario(history, sizing)

    def test_solver_failure_and_bad_weights_fail_closed(self):
        history, sizing = inputs()
        with patch("invest.allocation_optimizer._weights_from_pypfopt", side_effect=ValueError("solver")):
            with self.assertRaises(ValueError):
                min_variance_scenario(history, sizing)
        with patch("invest.allocation_optimizer._weights_from_pypfopt", return_value=(
            {"DEMO.ETF": 1.1, "SECOND.ETF": -0.1}, "contract-stub")):
            with self.assertRaises(ValueError):
                min_variance_scenario(history, sizing)

    def test_missing_optional_dependency_is_explicit(self):
        from invest.allocation_optimizer import _weights_from_pypfopt
        with patch.dict(sys.modules, {"pypfopt": None}):
            with self.assertRaisesRegex(RuntimeError, "PyPortfolioOpt"):
                _weights_from_pypfopt(["A", "B"], [[0.01, 0.02]] * 30)


if __name__ == "__main__":
    unittest.main()
