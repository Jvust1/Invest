"""Input integrity and disagreement tests independent of optional backends."""
from datetime import date, timedelta
import unittest
from unittest.mock import patch

from invest.risk_metrics import compare_risk_metrics


def fixture(constant=False):
    days = []
    day = date(2025, 1, 2)
    while len(days) < 40:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    return {"data_scope": "PUBLIC_RESEARCH_ONLY", "source": "synthetic fixture",
            "daily_returns": [{"date": d, "return": "0.01" if constant else
                               ("0.012" if i % 2 else "-0.008")}
                              for i, d in enumerate(days)]}


def fake_metrics(days, values, sharpe_defined, sortino_defined):
    return {"version": "test", "metrics": {
        "cumulative_return": 0.08,
        "annualized_return": 0.63,
        "annual_volatility": 0.15,
        "max_drawdown": -0.04,
        "sharpe_zero_rf": 0.4 if sharpe_defined else None,
        "sortino_zero_target": 0.7 if sortino_defined else None,
    }}


class RiskMetricsContractTests(unittest.TestCase):
    @patch("invest.risk_metrics._from_quantstats", side_effect=fake_metrics)
    @patch("invest.risk_metrics._from_empyrical", side_effect=fake_metrics)
    def test_same_window_digest_and_explicit_assumptions(self, empyrical, quantstats):
        history = fixture()
        result = compare_risk_metrics(history, as_of="2025-04-01")
        self.assertEqual(result["schema"], "invest-risk-metrics-crosscheck-v2")
        self.assertEqual(result["comparison_status"], "AGREE")
        self.assertEqual(result["history_sessions"], 40)
        self.assertEqual(result["assumptions"]["periods_per_year"], 252)
        self.assertEqual(result["assumptions"]["sortino_target_return"], 0.0)
        self.assertEqual(result["data_scope"], "PUBLIC_RESEARCH_ONLY")
        self.assertEqual(len(result["history_sha256"]), 64)
        self.assertEqual(set(result["comparison"]), {
            "cumulative_return", "annualized_return", "annual_volatility",
            "max_drawdown", "sharpe_zero_rf", "sortino_zero_target"})
        self.assertEqual(empyrical.call_args.args[0], quantstats.call_args.args[0])
        self.assertEqual(empyrical.call_args.args[1], quantstats.call_args.args[1])

    @patch("invest.risk_metrics._from_quantstats", side_effect=fake_metrics)
    @patch("invest.risk_metrics._from_empyrical")
    def test_disagreement_is_reported_without_backend_selection(self, empyrical, quantstats):
        changed = fake_metrics([], [], True, True)
        changed["metrics"]["max_drawdown"] = -0.05
        empyrical.return_value = changed
        result = compare_risk_metrics(fixture(), as_of="2025-04-01")
        self.assertEqual(result["comparison_status"], "DISAGREE")
        self.assertEqual(result["comparison"]["max_drawdown"]["status"], "DISAGREE")
        self.assertEqual(result["backends"]["quantstats"]["metrics"]["max_drawdown"], -0.04)
        self.assertEqual(result["backends"]["empyrical_reloaded"]["metrics"]["max_drawdown"], -0.05)

    @patch("invest.risk_metrics._from_quantstats", side_effect=fake_metrics)
    @patch("invest.risk_metrics._from_empyrical", side_effect=fake_metrics)
    def test_positive_constant_stream_has_undefined_sharpe_and_sortino(self, empyrical, quantstats):
        result = compare_risk_metrics(fixture(constant=True), as_of="2025-04-01")
        self.assertEqual(result["comparison_status"], "PARTIAL_UNDEFINED")
        self.assertEqual(result["comparison"]["sharpe_zero_rf"]["status"], "UNDEFINED")
        self.assertEqual(result["comparison"]["sortino_zero_target"]["status"], "UNDEFINED")
        self.assertIsNone(result["backends"]["quantstats"]["metrics"]["sharpe_zero_rf"])
        self.assertIsNone(result["backends"]["quantstats"]["metrics"]["sortino_zero_target"])
        self.assertFalse(quantstats.call_args.args[2])
        self.assertFalse(quantstats.call_args.args[3])

    def test_rejects_future_leak_duplicates_scope_and_nonfinite_values(self):
        for change in (lambda h: h["daily_returns"].append(h["daily_returns"][-1].copy()),
                       lambda h: h["daily_returns"][-1].update(date="2025-04-02"),
                       lambda h: h.update(data_scope="EXECUTION"),
                       lambda h: h["daily_returns"][0].update({"return": float("nan")}),
                       lambda h: h["daily_returns"][0].update({"return": -1})):
            history = fixture()
            change(history)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare_risk_metrics(history, as_of="2025-04-01")

    @patch("invest.risk_metrics._from_quantstats", side_effect=fake_metrics)
    @patch("invest.risk_metrics._from_empyrical")
    def test_nonfinite_backend_result_fails_closed(self, empyrical, quantstats):
        changed = fake_metrics([], [], True, True)
        changed["metrics"]["annual_volatility"] = float("nan")
        empyrical.return_value = changed
        with self.assertRaisesRegex(ValueError, "非有限"):
            compare_risk_metrics(fixture(), as_of="2025-04-01")


if __name__ == "__main__":
    unittest.main()
