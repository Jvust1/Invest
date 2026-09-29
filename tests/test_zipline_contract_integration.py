"""Real Zipline Reloaded Shanghai calendar and bundle registration contract."""
import importlib.util
import unittest

from invest.independent_engines import zipline_synthetic_contract


@unittest.skipUnless(importlib.util.find_spec("zipline"), "Zipline Reloaded optional dependency required")
class ZiplineContractIntegrationTests(unittest.TestCase):
    def test_xshg_calendar_and_isolated_bundle_registration(self):
        result = zipline_synthetic_contract()
        self.assertEqual(result["backend"], "zipline-reloaded")
        self.assertEqual(result["backend_version"], "3.1.1")
        self.assertEqual(result["calendar"], "XSHG")
        self.assertGreaterEqual(result["session_count_probe"], 5)
        self.assertEqual(result["bundle_registration"], "REGISTERED_AND_REMOVED_WITHOUT_INGEST")


if __name__ == "__main__":
    unittest.main()
