"""Dependency-free tests for net-value -> return -> risk-report bridging."""
from datetime import date, timedelta
import copy
import unittest
from unittest.mock import patch

from invest.replay_risk import compare_allocation_risk_report


def replay_fixture(*, all_cash=False, sessions=30):
    days = []
    day = date(2025, 1, 2)
    while len(days) < sessions:
        if day.weekday() < 5:
            days.append(day.isoformat())
        day += timedelta(days=1)
    if all_cash:
        equities = ["500.00"] * sessions
        fees = "0"
        quantity = 0
    else:
        equities = ["495.00"] + ["500.00" if i % 2 else "490.00" for i in range(1, sessions)]
        fees = "5.00"
        quantity = 200
    curve = [{"date": d, "cash_cny": "115.00" if not all_cash else "500.00",
              "equity_cny": equity, "fees_cny": fees if i == 0 else "0",
              "positions": {"DEMO.ETF": quantity}}
             for i, (d, equity) in enumerate(zip(days, equities))]
    return {
        "schema": "invest-bt-allocation-replay-v1",
        "status": "SCENARIO_ONLY",
        "data_scope": "PUBLIC_RESEARCH_ONLY",
        "as_of": days[-1],
        "history_source": "synthetic fixture",
        "history_sha256": "a" * 64,
        "history_sessions": sessions,
        "allocation": {
            "cash_cny": "500.00",
            "input_sha256": "b" * 64,
            "candidates": [{"symbol": "DEMO.ETF", "quantity_shares": quantity,
                            "entry_fees_cny": fees}],
        },
        "backend": "bt",
        "backend_version": "mock",
        "invest_curve": curve,
        "bt_curve": copy.deepcopy(curve),
        "comparison": [{"date": d, "status": "AGREE"} for d in days],
        "comparison_status": "AGREE",
    }


def risk_result(history):
    return {
        "schema": "invest-risk-metrics-crosscheck-v2",
        "status": "SCENARIO_ONLY",
        "data_scope": "PUBLIC_RESEARCH_ONLY",
        "history_sessions": len(history["daily_returns"]),
        "comparison_status": "AGREE",
    }


class ReplayRiskBridgeTests(unittest.TestCase):
    @patch("invest.replay_risk.compare_risk_metrics")
    @patch("invest.replay_risk.compare_allocation_replay")
    def test_first_return_includes_entry_fee_and_passes_same_rows_to_risk(self, replay, risk):
        replay.return_value = replay_fixture()
        risk.side_effect = lambda history, as_of: risk_result(history)
        result = compare_allocation_risk_report({}, {}, as_of="2025-02-12")
        self.assertEqual(result["schema"], "invest-allocation-risk-report-v1")
        self.assertEqual(result["entry_fees_cny"], "5.00")
        self.assertEqual(result["first_observation_return"], "-0.01")
        self.assertEqual(result["daily_returns"][0]["return"], "-0.01")
        self.assertEqual(result["return_convention"]["entry_fee_treatment"],
                         "included_in_first_observation_return")
        passed = risk.call_args.args[0]
        self.assertEqual(passed["daily_returns"], result["daily_returns"])
        self.assertEqual(passed["source"], "synthetic fixture")

    @patch("invest.replay_risk.compare_risk_metrics")
    @patch("invest.replay_risk.compare_allocation_replay")
    def test_all_cash_yields_zero_return_stream(self, replay, risk):
        replay.return_value = replay_fixture(all_cash=True)
        risk.side_effect = lambda history, as_of: risk_result(history)
        result = compare_allocation_risk_report({}, {}, as_of="2025-02-12")
        self.assertEqual(result["entry_fees_cny"], "0")
        self.assertTrue(all(row["return"] == "0" for row in result["daily_returns"]))

    @patch("invest.replay_risk.compare_risk_metrics")
    @patch("invest.replay_risk.compare_allocation_replay")
    def test_replay_disagreement_fails_closed_before_risk_metrics(self, replay, risk):
        changed = replay_fixture()
        changed["comparison_status"] = "DISAGREE"
        replay.return_value = changed
        with self.assertRaisesRegex(ValueError, "拒绝继续"):
            compare_allocation_risk_report({}, {}, as_of="2025-02-12")
        risk.assert_not_called()

    @patch("invest.replay_risk.compare_risk_metrics")
    @patch("invest.replay_risk.compare_allocation_replay")
    def test_less_than_30_sessions_fails_before_risk_metrics(self, replay, risk):
        replay.return_value = replay_fixture(sessions=29)
        with self.assertRaisesRegex(ValueError, "至少需要30"):
            compare_allocation_risk_report({}, {}, as_of="2025-02-11")
        risk.assert_not_called()


if __name__ == "__main__":
    unittest.main()
