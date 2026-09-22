"""Financial journal boundaries, rollback and provenance regression tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from copy import deepcopy
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from invest.data import dataset_identity, parse_csv
from invest.portfolio import PaperLedger


DATES = ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08"]


def market(days=4, *, source="测试供应方", action_day=None, factor_day=None):
    header = "symbol,date,open,high,low,close,volume_shares,suspended,up_limit,down_limit,adj_factor,corporate_action"
    rows = [header]
    for i, day in enumerate(DATES[:days]):
        action = "true" if i == action_day else "false"
        factor = 2 if factor_day is not None and i >= factor_day else 1
        rows.append(f"600000.SH,{day},10,10.8,9.2,10.5,1000000,false,11,9,{factor},{action}")
    return parse_csv("\n".join(rows), source=source, calendar_csv="date\n" + "\n".join(DATES[:days]))


def order(day=DATES[0], side="BUY", quantity=100, **extra):
    result = {
        "symbol": "600000.SH", "date": day, "side": side, "quantity": quantity,
        "reason": "基于测试数据检验长期假设，非真实投资指令。",
        "commission_rate": 0, "min_commission": 0, "stamp_tax_rate": 0,
        "transfer_fee_rate": 0, "slippage_bps": 0,
        "cost_model_acknowledged": True,
    }
    result.update(extra)
    return result


class PaperLedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "private" / "ledger.sqlite3"
        self.ledger = PaperLedger(self.path)
        self.account = self.ledger.create_account("人民币模拟", 10000)
        self.account_id = self.account["id"]
        self.data = market()

    def tearDown(self):
        self.temp.cleanup()

    def trade(self, *args, data=None, **kwargs):
        return self.ledger.record_trade(self.account_id, data or self.data, order(*args, **kwargs))

    def test_buy_next_day_sell_and_exact_cash(self):
        bought = self.trade()
        self.assertEqual(bought["account"]["cash"], 9000)
        self.assertEqual(bought["positions"][0]["average_cost"], 10)
        self.assertEqual(bought["equity"], 10050)
        self.assertEqual(bought["trades"][0]["price"], 10)
        self.assertEqual(bought["trades"][0]["gross_exact"], "1000.00")
        sold = self.trade(DATES[1], "SELL")
        self.assertEqual(sold["account"]["cash"], 10000)
        self.assertEqual(sold["positions"], [])
        self.assertNotEqual(sold["trades"][0]["id"], sold["trades"][1]["id"])

    def test_failed_trade_rolls_back_and_keeps_account_usable(self):
        before = self.ledger.snapshot(self.account_id)
        with self.assertRaises(ValueError):
            self.trade(quantity=1100)
        self.assertEqual(self.ledger.snapshot(self.account_id), before)
        self.trade()
        self.assertEqual(len(self.ledger.snapshot(self.account_id)["trades"]), 1)

    def test_t_plus_one_then_sell_old_shares_after_new_buy(self):
        self.trade()
        with self.assertRaises(ValueError):
            self.trade(side="SELL")
        self.trade(DATES[1], "BUY")
        sold = self.trade(DATES[1], "SELL")
        self.assertEqual(sold["positions"][0]["quantity"], 100)
        with self.assertRaises(ValueError):
            self.trade(DATES[1], "SELL")
        self.assertEqual(len(self.ledger.snapshot(self.account_id)["trades"]), 3)

    def test_no_shorts_or_odd_lots(self):
        for payload in (order(side="SELL"), order(quantity=1), order(quantity=True), order(quantity=100.0), order(quantity=-100)):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                self.ledger.record_trade(self.account_id, self.data, payload)
        self.assertEqual(self.ledger.snapshot(self.account_id)["trades"], [])

    def test_concurrent_spend_is_serialized(self):
        account = self.ledger.create_account("并发", 1500)
        def buy(_):
            try:
                self.ledger.record_trade(account["id"], self.data, order())
                return "accepted"
            except ValueError:
                return "rejected"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(buy, range(2)))
        self.assertCountEqual(results, ["accepted", "rejected"])
        snapshot = self.ledger.snapshot(account["id"])
        self.assertEqual(snapshot["account"]["cash"], 500)
        self.assertEqual(len(snapshot["trades"]), 1)

    def test_dataset_extension_preserves_history_but_swaps_fail(self):
        self.trade(data=market(1))
        self.trade(DATES[1], data=market(2))
        with self.assertRaises(ValueError):
            self.trade(DATES[2], data=market(3, source="其他供应方"))
        changed = market(3)
        changed["bars"][0]["close"] = 10.4
        changed["id"] = dataset_identity(changed)
        with self.assertRaises(ValueError):
            self.trade(DATES[2], data=changed)
        self.assertEqual(len(self.ledger.snapshot(self.account_id)["trades"]), 2)

    def test_dataset_hash_must_match_content_before_first_trade_or_mark(self):
        tampered = deepcopy(self.data)
        tampered["bars"][0]["open"] = 9.5
        with self.assertRaisesRegex(ValueError, "指纹"):
            self.trade(data=tampered)
        self.assertEqual(self.ledger.snapshot(self.account_id)["trades"], [])
        self.trade()
        with self.assertRaisesRegex(ValueError, "指纹"):
            self.ledger.snapshot(self.account_id, tampered)

    def test_changed_future_corporate_action_blocks_entire_lifecycle(self):
        self.trade(data=market(1))
        for data in (market(action_day=1), market(factor_day=1)):
            with self.subTest(data=data), self.assertRaises(ValueError):
                self.trade(DATES[2], "SELL", data=data)
            mark = self.ledger.snapshot(self.account_id, data)
            self.assertFalse(mark["valuation_complete"])
            self.assertIsNone(mark["equity"])

    def test_closed_position_can_start_new_source_lifecycle(self):
        self.trade()
        self.trade(DATES[1], "SELL")
        reopened = self.trade(DATES[2], data=market(source="新供应方"))
        self.assertEqual(reopened["positions"][0]["quantity"], 100)
        self.assertEqual(reopened["trades"][-1]["dataset_source"], "新供应方")

    def test_missing_stale_and_incompatible_marks_are_null(self):
        self.trade(DATES[1])
        for dataset in (None, market(1), market(source="其他供应方")):
            with self.subTest(dataset=dataset):
                snapshot = self.ledger.snapshot(self.account_id, dataset)
                self.assertFalse(snapshot["valuation_complete"])
                self.assertIsNone(snapshot["equity"])
                self.assertIsNone(snapshot["positions"][0]["market_price"])
                self.assertIsNone(snapshot["risk"]["largest_position_weight"])

    def test_day_cannot_regress_and_date_is_strict(self):
        self.trade(DATES[1])
        for day in (DATES[0], "20260107", "2026-02-30", None, True):
            with self.subTest(day=day), self.assertRaises(ValueError):
                self.trade(day)

    def test_finite_cash_fee_inputs_acknowledgment_and_reason_required(self):
        for value in (float("nan"), float("inf"), "NaN", True, 0, -1, 1e20, 100.001):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.ledger.create_account("无效金额", value)
        for override in ({"reason": " "}, {"reason": "<script>alert(1)</script>"}, {"cost_model_acknowledged": False}, {"commission_rate": float("nan")}, {"slippage_bps": float("inf")}):
            with self.subTest(override=override), self.assertRaises(ValueError):
                self.trade(**override)

    def test_journal_reopens_and_database_rejects_rewrite(self):
        self.trade()
        reopened = PaperLedger(self.path)
        self.assertEqual(len(reopened.snapshot(self.account_id)["trades"]), 1)
        with closing(sqlite3.connect(self.path)) as db:
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("DELETE FROM trades")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE accounts SET initial_cash_cents=1")

    def test_trade_provenance_and_fee_components(self):
        snapshot = self.trade(commission_rate=0.0003, min_commission=5, transfer_fee_rate=0.00001)
        trade = snapshot["trades"][0]
        self.assertEqual(trade["dataset_id"], self.data["id"])
        self.assertEqual(trade["dataset_source"], "测试供应方")
        self.assertEqual(len(trade["history_sha256"]), 64)
        self.assertEqual(trade["commission"], 5)
        self.assertEqual(trade["transfer_fee"], 0.01)
        self.assertEqual(trade["parameters"]["initial_cash"], 10000)
        self.assertEqual(snapshot["account"]["cash"], 8994.99)
        json.dumps(snapshot, allow_nan=False)

    def test_cumulative_daily_volume_cannot_be_reused(self):
        text = "symbol,date,open,high,low,close,volume_shares,suspended,up_limit,down_limit,adj_factor,corporate_action\n600000.SH,2026-01-05,10,10.8,9.2,10.5,100,false,11,9,1,false"
        data = parse_csv(text, source="小成交量测试", calendar_csv="2026-01-05")
        self.trade(data=data)
        with self.assertRaises(ValueError):
            self.trade(data=data)
        self.assertEqual(len(self.ledger.snapshot(self.account_id)["trades"]), 1)

    def test_notes_are_plain_text_append_only_and_require_evidence(self):
        payload = {"symbol": "600000.SH", "thesis": "估值假设", "evidence": "可核验证据", "risks": "现金流波动", "invalidation": "连续两期证据不成立", "source_url": "https://example.com/report"}
        saved = self.ledger.save_note(payload)
        self.assertEqual(self.ledger.list_notes(), [saved])
        bad_urls = ("javascript:alert(1)", "file:///secret", "https://user:password@example.com/", "https://", "https://example.com\n/", "https://example.com:BAD/")
        for url in bad_urls:
            with self.subTest(url=url), self.assertRaises(ValueError):
                self.ledger.save_note({**payload, "source_url": url})
        for patch in ({"thesis": "<img src=x>"}, {"evidence": ""}, {"symbol": "688001.SH"}, {"thesis": {"html": "x"}}):
            with self.subTest(patch=patch), self.assertRaises(ValueError):
                self.ledger.save_note({**payload, **patch})
        self.assertEqual(len(self.ledger.list_notes()), 1)


if __name__ == "__main__":
    unittest.main()
