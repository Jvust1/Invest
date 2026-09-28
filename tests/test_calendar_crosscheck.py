import unittest
from unittest.mock import patch
from invest.calendar_crosscheck import crosscheck_shanghai_sessions


def check(observed):
    return crosscheck_shanghai_sessions(start="2024-01-08", end="2024-01-12",
        as_of="2024-01-13", observed_dates=observed,
        data_scope="PUBLIC_RESEARCH_ONLY")


class CalendarCrosscheckTests(unittest.TestCase):
    def test_disagreement_is_preserved_and_no_auto_authority(self):
        with patch("invest.calendar_crosscheck._exchange_sessions", return_value=({"2024-01-08", "2024-01-09"}, "x")), \
             patch("invest.calendar_crosscheck._pandas_sessions", return_value=({"2024-01-08"}, "p")):
            result = check(["2024-01-08"])
        self.assertEqual(result["status"], "CALENDAR_DISAGREEMENT")
        self.assertEqual(result["exchange_calendars_only"], ["2024-01-09"])

    def test_missing_observation_is_not_a_suspension_claim(self):
        with patch("invest.calendar_crosscheck._exchange_sessions", return_value=({"2024-01-08", "2024-01-09"}, "x")), \
             patch("invest.calendar_crosscheck._pandas_sessions", return_value=({"2024-01-08", "2024-01-09"}, "p")):
            result = check(["2024-01-08"])
        self.assertEqual(result["status"], "OBSERVATIONS_INCOMPLETE")
        self.assertEqual(result["unobserved_joint_sessions"], ["2024-01-09"])

    def test_reject_future_duplicate_and_non_public_scope(self):
        for dates in (["2024-01-08", "2024-01-08"], ["2024-01-14"]):
            with self.assertRaises(ValueError):
                check(dates)
        with self.assertRaises(ValueError):
            crosscheck_shanghai_sessions(start="2024-01-08", end="2024-01-12",
                as_of="2024-01-13", observed_dates=[], data_scope="EXECUTION_READY")


if __name__ == "__main__":
    unittest.main()
