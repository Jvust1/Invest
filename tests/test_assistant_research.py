import json
from pathlib import Path
import tempfile
import unittest

from tools.run_assistant_research import JobError, load_request, normalize_frame, summarize


class FakeFrame:
    empty = False
    def __init__(self, rows, columns):
        self._rows = rows
        self.columns = columns
    def iterrows(self):
        return enumerate(self._rows)


class AssistantResearchTests(unittest.TestCase):
    def request(self, **changes):
        value = {
            "schema": "invest-assistant-job-v1",
            "job_id": "test-job-001",
            "operation": "public_stock_research",
            "symbol": "600000.SH",
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "provider": "akshare_tencent",
        }
        value.update(changes)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "job.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return load_request(path)

    def test_valid_request(self):
        request = self.request()
        self.assertEqual(request["symbol"], "600000.SH")
        self.assertEqual(request["provider"], "akshare_tencent")

    def test_legacy_request_defaults_to_eastmoney(self):
        request = self.request()
        request.pop("provider", None)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "job.json"
            path.write_text(json.dumps(request), encoding="utf-8")
            self.assertEqual(load_request(path)["provider"], "akshare_eastmoney")

    def test_rejects_unknown_provider(self):
        with self.assertRaises(JobError):
            self.request(provider="automatic_fallback")

    def test_rejects_unsupported_board(self):
        with self.assertRaises(JobError):
            self.request(symbol="300001.SZ")

    def test_rejects_extra_field(self):
        with self.assertRaises(JobError):
            self.request(secret="never")

    def test_rejects_bad_range(self):
        with self.assertRaises(JobError):
            self.request(start_date="2026-02-01", end_date="2026-01-01")

    def test_normalize_eastmoney(self):
        rows = [{"日期": "2026-01-02", "开盘": 10, "收盘": 10.1, "最高": 10.2, "最低": 9.9, "成交量": 1000}]
        frame = FakeFrame(rows, ["日期", "开盘", "收盘", "最高", "最低", "成交量"])
        normalized = normalize_frame(frame, "akshare_eastmoney")
        self.assertEqual(normalized[0]["date"], "2026-01-02")
        self.assertEqual(normalized[0]["volume_provider_value"], 1000.0)

    def test_normalize_tencent_and_summary(self):
        rows = []
        for i in range(25):
            close = 10 + i * 0.1
            rows.append({"date": f"2026-01-{i+1:02d}", "open": close-0.02,
                         "close": close, "high": close+0.1, "low": close-0.1,
                         "volume": 1000+i, "turnover": 0.01, "amount": 100000})
        frame = FakeFrame(rows, ["date", "open", "close", "high", "low", "volume", "turnover", "amount"])
        normalized = normalize_frame(frame, "akshare_tencent")
        summary = summarize(normalized)
        self.assertEqual(summary["sessions"], 25)
        self.assertIsNotNone(summary["ma_20"])
        self.assertIsNone(summary["ma_60"])
        self.assertGreater(summary["period_return"], 0)

    def test_duplicate_dates_fail(self):
        rows = [
            {"date": "2026-01-02", "open": 10, "close": 10, "high": 10.1, "low": 9.9},
            {"date": "2026-01-02", "open": 10, "close": 10, "high": 10.1, "low": 9.9},
        ]
        frame = FakeFrame(rows, ["date", "open", "close", "high", "low"])
        with self.assertRaises(JobError):
            normalize_frame(frame, "akshare_tencent")

    def test_bad_ohlc_fails(self):
        frame = FakeFrame(
            [{"date": "2026-01-02", "open": 10, "close": 10, "high": 9, "low": 8}],
            ["date", "open", "close", "high", "low"],
        )
        with self.assertRaises(JobError):
            normalize_frame(frame, "akshare_tencent")


if __name__ == "__main__":
    unittest.main()
