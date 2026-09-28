import importlib.util
import unittest
from invest.calendar_crosscheck import crosscheck_shanghai_sessions


@unittest.skipUnless(all(importlib.util.find_spec(m) for m in ("exchange_calendars", "pandas_market_calendars")),
                     "two optional calendars required")
class RealShanghaiCalendarTests(unittest.TestCase):
    def test_two_real_calendars_retained_independently(self):
        result = crosscheck_shanghai_sessions(start="2024-01-08", end="2024-01-14",
            as_of="2024-01-15", observed_dates=[], data_scope="PUBLIC_RESEARCH_ONLY")
        self.assertGreater(result["first_session_count"], 0)
        self.assertGreater(result["second_session_count"], 0)
        self.assertEqual(result["data_scope"], "PUBLIC_RESEARCH_ONLY")
        self.assertIn(result["status"], ("OBSERVATIONS_INCOMPLETE", "CALENDAR_DISAGREEMENT"))
        self.assertNotIn("2024-01-13", result["unobserved_joint_sessions"])


if __name__ == "__main__":
    unittest.main()
