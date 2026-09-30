import unittest

import pandas as pd

from invest.indicators import TAFeatureEngineer


class _RSI:
    def __init__(self, close, window):
        self.close = close
    def rsi(self):
        return pd.Series([50.0] * len(self.close), index=self.close.index)


class _MACD:
    def __init__(self, close):
        self.close = close
    def macd(self):
        return pd.Series([1.0] * len(self.close), index=self.close.index)
    def macd_signal(self):
        return pd.Series([0.8] * len(self.close), index=self.close.index)
    def macd_diff(self):
        return pd.Series([0.2] * len(self.close), index=self.close.index)


class _BB:
    def __init__(self, close, window, window_dev):
        self.close = close
    def bollinger_mavg(self):
        return pd.Series([10.0] * len(self.close), index=self.close.index)
    def bollinger_hband(self):
        return pd.Series([11.0] * len(self.close), index=self.close.index)
    def bollinger_lband(self):
        return pd.Series([9.0] * len(self.close), index=self.close.index)


class _ATR:
    def __init__(self, high, low, close, window):
        self.close = close
    def average_true_range(self):
        return pd.Series([0.5] * len(self.close), index=self.close.index)


class TAFeatureEngineerTests(unittest.TestCase):
    def setUp(self):
        self.engineer = TAFeatureEngineer(
            rsi_cls=_RSI,
            macd_cls=_MACD,
            bollinger_cls=_BB,
            atr_cls=_ATR,
        )

    def test_transform_adds_stable_research_feature_columns(self):
        frame = pd.DataFrame({
            "high": [10.5, 11.0],
            "low": [9.5, 10.0],
            "close": [10.0, 10.8],
        })
        result = self.engineer.transform(frame)
        for name in (
            "ta_rsi_14", "ta_macd", "ta_macd_signal", "ta_macd_diff",
            "ta_bb_mid", "ta_bb_high", "ta_bb_low", "ta_atr_14",
        ):
            self.assertIn(name, result.columns)
        self.assertEqual(float(result.iloc[0]["ta_rsi_14"]), 50.0)

    def test_transform_rejects_missing_ohlc_columns(self):
        with self.assertRaises(ValueError):
            self.engineer.transform(pd.DataFrame({"close": [10.0]}))


if __name__ == "__main__":
    unittest.main()
