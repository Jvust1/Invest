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


@unittest.skipUnless(importlib.util.find_spec("riskfolio"), "Riskfolio-Lib optional dependency absent")
class RiskfolioIntegrationTests(unittest.TestCase):
    def test_real_min_variance_solver_to_discrete_cash(self):
        history, sizing = inputs()
        result = min_variance_scenario(history, sizing, backend="riskfolio")
        self.assertEqual(result["backend"], "Riskfolio-Lib")
        self.assertAlmostEqual(sum(float(w) for w in result["weights"].values()), 1.0, places=8)
        self.assertTrue(all(Decimal(w) >= 0 for w in result["weights"].values()))
        self.assertGreaterEqual(Decimal(result["allocation"]["remaining_cash_cny"]), Decimal("100"))


@unittest.skipUnless(importlib.util.find_spec("skfolio"), "skfolio optional dependency absent")
class SkfolioIntegrationTests(unittest.TestCase):
    def test_real_min_variance_solver_to_discrete_cash(self):
        history, sizing = inputs()
        result = min_variance_scenario(history, sizing, backend="skfolio")
        self.assertEqual(result["backend"], "skfolio")
        self.assertAlmostEqual(sum(float(w) for w in result["weights"].values()), 1.0, places=8)
        self.assertTrue(all(Decimal(w) >= 0 for w in result["weights"].values()))
        self.assertGreaterEqual(Decimal(result["allocation"]["remaining_cash_cny"]), Decimal("100"))


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("pypfopt", "riskfolio", "skfolio")),
                     "all three optional optimizers required")
class CrossBackendIntegrationTests(unittest.TestCase):
    def test_three_real_backends_on_identical_history(self):
        from invest.allocation_optimizer import compare_min_variance_backends
        history, sizing = inputs()
        result = compare_min_variance_backends(history, sizing)
        self.assertEqual(len(result["results"]), 3)
        self.assertEqual(len(result["pairwise_gaps"]), 3)
        self.assertEqual(len({r["history_sha256"] for r in result["results"]}), 1)
        self.assertTrue(all(r["status"] == "SCENARIO_ONLY" for r in result["results"]))
        self.assertTrue(all(Decimal(g["max_absolute_weight_gap"]) >= 0
                            for g in result["pairwise_gaps"].values()))


if __name__ == "__main__":
    unittest.main()
