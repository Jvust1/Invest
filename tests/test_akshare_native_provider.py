import unittest

import pandas as pd

from invest.providers.akshare_native import AKShareProvider, normalize_history, normalize_spot


class FakeAKShare:
    def __init__(self):
        self.history_kwargs = None

    def stock_zh_a_hist(self, **kwargs):
        self.history_kwargs = kwargs
        return pd.DataFrame(
            [
                {
                    "日期": "2026-09-29",
                    "股票代码": "1",
                    "开盘": "10.1",
                    "收盘": "10.5",
                    "最高": "10.8",
                    "最低": "9.9",
                    "成交量": "1000",
                    "成交额": "10000",
                    "涨跌幅": "2.0",
                    "换手率": "1.2",
                }
            ]
        )

    def stock_zh_a_spot_em(self):
        return pd.DataFrame(
            [
                {
                    "代码": "600000",
                    "名称": "浦发银行",
                    "最新价": "12.34",
                    "涨跌幅": "1.1",
                    "成交量": "2000",
                    "总市值": "300000000000",
                }
            ]
        )


class AKShareNativeProviderTests(unittest.TestCase):
    def test_history_normalizes_upstream_columns_and_symbol(self):
        fake = FakeAKShare()
        provider = AKShareProvider(fake)
        frame = provider.history("1", start_date="20260901", end_date="20260930", adjust="qfq")
        self.assertEqual(fake.history_kwargs["symbol"], "000001")
        self.assertEqual(fake.history_kwargs["adjust"], "qfq")
        self.assertEqual(frame.iloc[0]["symbol"], "000001")
        self.assertAlmostEqual(float(frame.iloc[0]["close"]), 10.5)
        self.assertEqual(frame.index[0].strftime("%Y%m%d"), "20260929")

    def test_spot_normalizes_market_snapshot(self):
        frame = AKShareProvider(FakeAKShare()).spot()
        self.assertEqual(frame.iloc[0]["symbol"], "600000")
        self.assertEqual(frame.iloc[0]["name"], "浦发银行")
        self.assertAlmostEqual(float(frame.iloc[0]["last"]), 12.34)

    def test_normalizers_reject_non_dataframe(self):
        with self.assertRaises(TypeError):
            normalize_history([])
        with self.assertRaises(TypeError):
            normalize_spot({})


if __name__ == "__main__":
    unittest.main()
