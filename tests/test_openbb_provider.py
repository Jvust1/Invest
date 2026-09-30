import unittest
from types import SimpleNamespace

import pandas as pd

from invest.providers.openbb_provider import OpenBBProvider, normalize_openbb_ohlcv


class Output:
    def to_dataframe(self):
        return pd.DataFrame(
            [
                {"date": "2026-09-29", "open": 10, "high": 11, "low": 9, "close": 10.5, "volume": 1000},
                {"date": "2026-09-30", "open": 10.5, "high": 12, "low": 10, "close": 11.8, "volume": 1200},
            ]
        )


class Historical:
    def __init__(self):
        self.calls = []

    def __call__(self, symbol, **kwargs):
        self.calls.append((symbol, kwargs))
        return Output()


class OpenBBProviderTests(unittest.TestCase):
    def test_history_uses_public_openbb_path_and_normalizes(self):
        historical = Historical()
        obb = SimpleNamespace(
            equity=SimpleNamespace(price=SimpleNamespace(historical=historical))
        )
        frame = OpenBBProvider(obb).history("AAPL", provider="demo")
        self.assertEqual(historical.calls, [("AAPL", {"provider": "demo"})])
        self.assertEqual(frame.iloc[-1]["symbol"], "AAPL")
        self.assertAlmostEqual(float(frame.iloc[-1]["close"]), 11.8)

    def test_normalizer_accepts_datetime_index(self):
        frame = pd.DataFrame({"close": [1.0]}, index=pd.to_datetime(["2026-09-30"]))
        normalized = normalize_openbb_ohlcv(frame)
        self.assertEqual(normalized.index[0].strftime("%Y%m%d"), "20260930")


if __name__ == "__main__":
    unittest.main()
