"""Real bt + QuantStats + Empyrical contract on synthetic 40-session inputs."""
from datetime import date, timedelta
import importlib.util
import unittest
import warnings

from invest.replay_risk import compare_allocation_risk_report
from test_bt_replay import fixture


_REQUIRED = ("bt", "quantstats", "empyrical")


def extended_fixture():
    _, request = fixture()
    days = []
    day = date(2025, 1, 2)
    while len(days) < 40:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    pattern = ("1.90", "1.92", "1.88", "1.95", "1.91")
    history = {
        "data_scope": "PUBLIC_RESEARCH_ONLY",
        "source": "synthetic 40-session replay fixture",
        "price_basis": "UNADJUSTED_NO_CORPORATE_ACTIONS",
        "daily_prices": [
            {"date": d, "prices_cny": {"DEMO.ETF": pattern[i % len(pattern)]}}
            for i, d in enumerate(days)
        ],
    }
    return history, request, days[-1]


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in _REQUIRED),
                     "bt, QuantStats and Empyrical optional dependencies required")
class RealReplayRiskIntegrationTests(unittest.TestCase):
    def setUp(self):
        import pandas as pd
        context = warnings.catch_warnings()
        context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        warnings.simplefilter("error", pd.errors.ChainedAssignmentError)

    def test_real_three_library_fee_aware_risk_report(self):
        history, request, as_of = extended_fixture()
        result = compare_allocation_risk_report(history, request, as_of=as_of)
        self.assertEqual(result["replay"]["comparison_status"], "AGREE")
        self.assertEqual(result["risk_metrics"]["history_sessions"], 40)
        self.assertEqual(result["risk_metrics"]["comparison_status"], "AGREE")
        self.assertAlmostEqual(float(result["first_observation_return"]), -0.01002, places=10)
        self.assertEqual(set(result["risk_metrics"]["comparison"]), {
            "cumulative_return", "annualized_return", "annual_volatility",
            "max_drawdown", "sharpe_zero_rf", "sortino_zero_target"})

    def test_real_all_cash_report_has_zero_risk_and_undefined_ratios(self):
        history, request, as_of = extended_fixture()
        request["reserve_cny"] = "500.00"
        result = compare_allocation_risk_report(history, request, as_of=as_of)
        risk = result["risk_metrics"]
        self.assertEqual(risk["comparison_status"], "PARTIAL_UNDEFINED")
        for backend in risk["backends"].values():
            self.assertAlmostEqual(backend["metrics"]["cumulative_return"], 0.0, places=12)
            self.assertAlmostEqual(backend["metrics"]["annualized_return"], 0.0, places=12)
            self.assertAlmostEqual(backend["metrics"]["annual_volatility"], 0.0, places=12)
            self.assertAlmostEqual(backend["metrics"]["max_drawdown"], 0.0, places=12)
            self.assertIsNone(backend["metrics"]["sharpe_zero_rf"])
            self.assertIsNone(backend["metrics"]["sortino_zero_target"])


if __name__ == "__main__":
    unittest.main()
