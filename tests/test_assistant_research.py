import json
from pathlib import Path
import tempfile
import unittest

from tools.run_assistant_research import JobError, load_request, normalize_frame, summarize


class FakeFrame:
    empty = False
    columns = ["日期", "开盘", "收盘", "最高", "最低", "成交量"]
    def __init__(self, rows):
        self._rows = rows
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
        }
        value.update(changes)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "job.json"
            path.write_text(json.dumps(value), encoding="utf-8")
            return load_request(path)

    def test_valid_request(self):
        self.assertEqual(self.request()["symbol"], "600000.SH")

    def test_rejects_unsupported_board(self):
        with self.assertRaises(JobError):
            self.request(symbol="300001.SZ")

    def test_rejects_extra_field(self):
        with self.assertRaises(JobError):
            self.request(secret="never")

    def test_rejects_bad_range(self):
        with self.assertRaises(JobError):
            self.request(start_date="2026-02-01", end_date="2026-01-01")

    def test_normalize_and_summary(self):
        rows = []
        for i in range(25):
            close = 10 + i * 0.1
            rows.append({"日期": f"2026-01-{i+1:02d}", "开盘": close-0.02,
                         "收盘": close, "最高": close+0.1, "最低": close-0.1,
                         "成交量": 1000+i})
        normalized = normalize_frame(FakeFrame(rows))
        summary = summarize(normalized)
        self.assertEqual(summary["sessions"], 25)
        self.assertIsNotNone(summary["ma_20"])
        self.assertIsNone(summary["ma_60"])
        self.assertGreater(summary["period_return"], 0)

    def test_duplicate_dates_fail(self):
        frame = FakeFrame([
            {"日期": "2026-01-02", "开盘": 10, "收盘": 10, "最高": 10.1, "最低": 9.9, "成交量": 1},
            {"日期": "2026-01-02", "开盘": 10, "收盘": 10, "最高": 10.1, "最低": 9.9, "成交量": 1},
        ])
        with self.assertRaises(JobError):
            normalize_frame(frame)

    def test_bad_ohlc_fails(self):
        frame = FakeFrame([
            {"日期": "2026-01-02", "开盘": 10, "收盘": 10, "最高": 9, "最低": 8, "成交量": 1},
        ])
        with self.assertRaises(JobError):
            normalize_frame(frame)


if __name__ == "__main__":
    unittest.main()
