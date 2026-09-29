"""Runs real optional upstreams in the dedicated risk-metrics CI job."""
import importlib.util
import math
import unittest

from invest.risk_metrics import compare_risk_metrics
from test_risk_metrics import fixture


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("quantstats", "empyrical")),
                     "both optional risk metrics packages required")
class RealRiskMetricsIntegrationTests(unittest.TestCase):
    def test_two_real_upstreams_on_same_daily_simple_returns(self):
        result = compare_risk_metrics(fixture(), as_of="2025-04-01")
        self.assertEqual(result["schema"], "invest-risk-metrics-crosscheck-v2")
        self.assertEqual(result["history_sessions"], 40)
        self.assertEqual(set(result["backends"]), {"quantstats", "empyrical_reloaded"})
        self.assertTrue(all(x["version"] != "test" for x in result["backends"].values()))
        self.assertTrue(all(math.isfinite(value)
                            for backend in result["backends"].values()
                            for value in backend["metrics"].values()))
        self.assertEqual(result["comparison_status"], "AGREE")
        self.assertTrue(all(item["status"] == "AGREE"
                            for item in result["comparison"].values()))


if __name__ == "__main__":
    unittest.main()
