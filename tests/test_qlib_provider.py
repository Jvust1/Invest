import unittest

import pandas as pd

from invest.qlib_bridge import QlibMarketProvider


class FakeDataAPI:
    def __init__(self):
        self.calls = []

    def features(self, instruments, fields, start_time, end_time, freq):
        self.calls.append((instruments, fields, start_time, end_time, freq))
        idx = pd.MultiIndex.from_tuples(
            [("SZ000001", pd.Timestamp("2026-09-29")), ("SZ000001", pd.Timestamp("2026-09-30"))],
            names=["instrument", "datetime"],
        )
        return pd.DataFrame(
            {
                "$open": [10.0, 10.2],
                "$high": [10.5, 10.8],
                "$low": [9.9, 10.1],
                "$close": [10.3, 10.7],
                "$volume": [1000, 1200],
            },
            index=idx,
        )


class QlibProviderTests(unittest.TestCase):
    def test_normalize_instrument_for_a_share_codes(self):
        self.assertEqual(QlibMarketProvider.normalize_instrument("000001"), "SZ000001")
        self.assertEqual(QlibMarketProvider.normalize_instrument("600000"), "SH600000")
        self.assertEqual(QlibMarketProvider.normalize_instrument("SH600000"), "SH600000")

    def test_history_normalizes_qlib_feature_frame(self):
        api = FakeDataAPI()
        frame = QlibMarketProvider(api).history(
            "000001",
            start_date="2026-09-01",
            end_date="2026-09-30",
        )
        self.assertEqual(list(frame.columns), ["open", "high", "low", "close", "volume"])
        self.assertAlmostEqual(float(frame.iloc[-1]["close"]), 10.7)
        self.assertEqual(api.calls[0][0], ["SZ000001"])
        self.assertEqual(api.calls[0][-1], "day")


if __name__ == "__main__":
    unittest.main()
