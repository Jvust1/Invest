"""Actual optional-upstream contract. Runs in the dedicated optimization CI job."""
import importlib.util
import unittest
from decimal import Decimal

from invest.allocation_optimizer import min_variance_scenario
from test_allocation_optimizer import inputs


@unittest.skipUnless(importlib.util.find_spec("pypfopt"), "PyPortfolioOpt optional dependency absent")
class PyPortfolioOptIntegrationTests(unittest.TestCase):
    def test_real_min_variance_solver_to_discrete_cash(self):
        history, sizing = inputs()
        result = min_variance_scenario(history, sizing)
        self.assertEqual(result["backend"], "PyPortfolioOpt")
        self.assertEqual(result["history_sessions"], 30)
        self.assertAlmostEqual(sum(float(w) for w in result["weights"].values()), 1.0, places=8)
        self.assertTrue(all(Decimal(w) >= 0 for w in result["weights"].values()))
        self.assertGreaterEqual(Decimal(result["allocation"]["remaining_cash_cny"]), Decimal("100"))
        self.assertEqual(result["allocation"]["data_scope"], "PUBLIC_RESEARCH_ONLY")


if __name__ == "__main__":
    unittest.main()
