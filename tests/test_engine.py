import copy
import math
import unittest
from decimal import Decimal

from invest.data import dataset_identity
from invest.engine import (
    backtest, execute_order, research, validate_market_window, validate_parameters,
)


def dataset(closes=(10, 11, 12, 13, 10, 8), opens=None):
    bars = []
    for i, close in enumerate(closes):
        opening = opens[i] if opens else close
        bars.append({"symbol": "600000.SH", "date": f"2025-01-{i + 2:02d}",
                     "open": opening, "close": close, "high": max(opening, close) + 2,
                     "low": min(opening, close) - 2, "volume_shares": 1000000,
                     "suspended": False, "up_limit": 100, "down_limit": 1,
                     "adj_factor": 1, "corporate_action": False})
    result = {"meta": {"source": "synthetic test", "source_kind": "demo", "currency": "CNY", "price_basis": "raw", "volume_unit": "shares", "calendar_source": "synthetic sessions"},
              "bars": bars, "calendar": [bar["date"] for bar in bars]}
    return identified(result)


def identified(result):
    result["id"] = dataset_identity(result)
    return result


def params(**updates):
    return {"symbol": "600000.SH", "initial_cash": 10000, "fast": 1, "slow": 2,
            "commission_rate": 0, "min_commission": 0, "stamp_tax_rate": 0,
            "transfer_fee_rate": 0, "slippage_bps": 0,
            "cost_model_acknowledged": True, **updates}


class ParameterTests(unittest.TestCase):
    def test_requires_explicit_cost_acknowledgement(self):
        for value in (None, False, 1, "true"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_parameters(params(cost_model_acknowledged=value))

    def test_invalid_numbers_and_windows(self):
        for key, value in (("fast", True), ("slow", 2.0), ("fast", 2), ("slow", 501),
                           ("initial_cash", 0), ("initial_cash", 1.001),
                           ("commission_rate", True), ("commission_rate", float("nan")),
                           ("stamp_tax_rate", float("inf")), ("transfer_fee_rate", -.1),
                           ("slippage_bps", 1001), ("min_commission", 1001),
                           ("symbol", "300001.SZ"), ("start_date", "2025-02-30")):
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                validate_parameters(params(**{key: value}), require_strategy=True)


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.bar = dataset((10,))["bars"][0]

    def test_cash_includes_all_fees_and_rounds_components(self):
        p = params(commission_rate=.0003, min_commission=5, transfer_fee_rate=.00001, stamp_tax_rate=.0005)
        with self.assertRaisesRegex(ValueError, "现金不足"):
            execute_order(self.bar, "BUY", 100, 1000, 0, p)
        fill = execute_order(self.bar, "BUY", 100, Decimal("1005.01"), 0, p)
        self.assertEqual(fill["cash_after"], Decimal("0.00"))
        self.assertEqual(fill["fees"], Decimal("5.01"))
        sell = execute_order(self.bar, "SELL", 100, 0, 100, p)
        self.assertEqual(sell["stamp_tax"], Decimal("0.50"))
        self.assertEqual(sell["cash_after"], Decimal("994.49"))

    def test_t_plus_one_lots_and_no_short(self):
        for side, quantity, available in (("BUY", 1, 0), ("BUY", True, 0), ("SELL", 100, 0), ("SELL", 200, 100)):
            with self.subTest(side=side, quantity=quantity), self.assertRaises(ValueError):
                execute_order(self.bar, side, quantity, 10000, available, params())
        self.assertEqual(execute_order(self.bar, "SELL", 100, 0, 100, params())["quantity"], 100)

    def test_directional_limits(self):
        up = {**self.bar, "open": 12, "high": 12, "up_limit": 12}
        with self.assertRaisesRegex(ValueError, "涨停"):
            execute_order(up, "BUY", 100, 10000, 100, params())
        self.assertEqual(execute_order(up, "SELL", 100, 0, 100, params())["price"], 12)
        down = {**self.bar, "open": 8, "low": 8, "down_limit": 8}
        with self.assertRaisesRegex(ValueError, "跌停"):
            execute_order(down, "SELL", 100, 0, 100, params())
        self.assertEqual(execute_order(down, "BUY", 100, 10000, 0, params())["price"], 8)

    def test_slippage_conservatively_rounds_and_cannot_escape_ohlc(self):
        self.assertEqual(execute_order(self.bar, "BUY", 100, 10000, 0, params(slippage_bps=1))["price"], Decimal("10.01"))
        self.assertEqual(execute_order(self.bar, "SELL", 100, 0, 100, params(slippage_bps=1))["price"], Decimal("9.99"))
        tight = {**self.bar, "high": 10, "low": 10}
        with self.assertRaisesRegex(ValueError, "滑点"):
            execute_order(tight, "BUY", 100, 10000, 0, params(slippage_bps=1))

    def test_no_liquidity_no_fill(self):
        for updates in ({"suspended": True}, {"volume_shares": 0}, {"volume_shares": 99}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                execute_order({**self.bar, **updates}, "BUY", 100, 10000, 0, params())


class WindowTests(unittest.TestCase):
    def test_missing_calendar_and_gaps_rejected(self):
        for mutate in (
            lambda d: d.update(calendar=[]),
            lambda d: d["bars"].pop(2),
            lambda d: d["calendar"].append(d["calendar"][-1]),
            lambda d: d["meta"].update(price_basis="adjusted"),
        ):
            d = dataset()
            mutate(d)
            identified(d)
            with self.assertRaises(ValueError):
                validate_market_window(d, "600000.SH")

    def test_critical_unknowns_and_actions_rejected(self):
        for key, value in (("suspended", None), ("corporate_action", None),
                           ("corporate_action", True), ("adj_factor", None),
                           ("adj_factor", 2), ("up_limit", None)):
            d = dataset()
            d["bars"][2][key] = value
            identified(d)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                backtest(d, params())


class BacktestTests(unittest.TestCase):
    def test_hand_calculated_returns_drawdown_and_benchmark(self):
        # Warmup 10,11. Day3 buy 800x12; day4 hold 13; day5 hold10;
        # day6 sell800x8. Cash=400+6400=6800; peak=10800.
        result = backtest(dataset(), params())
        self.assertEqual(result["metrics"]["final_equity"], 6800)
        self.assertAlmostEqual(result["metrics"]["total_return"], -.32)
        self.assertAlmostEqual(result["metrics"]["max_drawdown"], 4000 / 10800)
        self.assertAlmostEqual(result["metrics"]["benchmark_return"], -.32)
        self.assertEqual([t["side"] for t in result["trades"]], ["BUY", "SELL"])
        self.assertEqual(result["trades"][0]["date"], "2025-01-04")
        self.assertEqual(result["trades"][0]["signal_date"], "2025-01-03")

    def test_mark_to_market_without_forced_liquidation_and_same_costs(self):
        result = backtest(dataset((10, 11, 12, 13)), params(min_commission=5))
        self.assertEqual(result["metrics"]["shares"], 800)
        self.assertEqual(result["metrics"]["cash"], 395)
        self.assertEqual(result["metrics"]["final_equity"], 10795)
        self.assertEqual(result["metrics"]["total_fees"], 5)
        self.assertEqual(result["metrics"]["benchmark_total_fees"], 5)
        self.assertEqual(len(result["trades"]), 1)
        self.assertEqual(result["curve"][-1]["equity"], result["curve"][-1]["benchmark_equity"])

    def test_no_lookahead_when_future_changes(self):
        original = dataset((10, 11, 12, 13, 10, 8))
        altered = copy.deepcopy(original)
        altered["bars"][4].update(open=20, close=20, high=22, low=18)
        identified(altered)
        a, b = backtest(original, params()), backtest(altered, params())
        before = lambda r: [t for t in r["trades"] if t["date"] < "2025-01-06"]
        self.assertEqual(before(a), before(b))
        self.assertEqual(a["curve"][:2], b["curve"][:2])
        # Today's close cannot alter the signal for today's open.
        altered = copy.deepcopy(original)
        altered["bars"][2].update(close=2, low=1)
        identified(altered)
        self.assertEqual(a["trades"][0], backtest(altered, params())["trades"][0])

    def test_day_order_expiry_uses_new_signal(self):
        d = dataset((10, 11, 8, 7))
        d["bars"][2]["suspended"] = True
        identified(d)
        result = backtest(d, params())
        self.assertFalse(result["trades"])
        self.assertEqual(len(result["rejected_orders"]), 1)
        self.assertEqual(result["rejected_orders"][0]["side"], "BUY")
        # Benchmark independently retries, not a carried strategy order.
        self.assertEqual(result["benchmark_trades"][0]["date"], "2025-01-05")

    def test_cash_reserves_minimum_commission(self):
        result = backtest(dataset((9, 10, 10)), params(initial_cash=1000, min_commission=5))
        self.assertEqual(result["metrics"]["shares"], 0)
        self.assertEqual(result["metrics"]["final_equity"], 1000)
        self.assertIn("100股", result["rejected_orders"][0]["reason"])

    def test_requested_start_uses_preexisting_warmup(self):
        result = backtest(dataset(), params(start_date="2025-01-05", end_date="2025-01-06"))
        self.assertEqual(result["evaluation_start"], "2025-01-05")
        self.assertEqual(result["evaluation_end"], "2025-01-06")
        self.assertEqual(result["warmup_start"], "2025-01-03")
        self.assertEqual(result["trades"][0]["date"], "2025-01-05")
        self.assertEqual(result["benchmark_trades"][0]["date"], "2025-01-05")

    def test_result_deterministic_and_input_unmodified(self):
        d, p = dataset(), params()
        before = copy.deepcopy((d, p))
        self.assertEqual(backtest(d, p), backtest(d, p))
        self.assertEqual((d, p), before)

    def test_changed_content_cannot_reuse_old_identity(self):
        d = dataset()
        before = backtest(d, params())
        d["bars"][-1].update(open=9, close=9, high=11, low=7)
        with self.assertRaisesRegex(ValueError, "指纹"):
            backtest(d, params())
        with self.assertRaisesRegex(ValueError, "指纹"):
            research(d)
        with self.assertRaisesRegex(ValueError, "指纹"):
            validate_market_window(d, "600000.SH")
        identified(d)
        after = backtest(d, params())
        self.assertNotEqual(before["fingerprint"], after["fingerprint"])
        self.assertNotEqual(before["metrics"]["final_equity"], after["metrics"]["final_equity"])


class ResearchTests(unittest.TestCase):
    def test_insufficient_history_is_null_not_fabricated(self):
        result = research(dataset())
        item = result["symbols"][0]
        self.assertIsNone(item["return_20d"])
        self.assertIsNone(item["volatility_20d"])
        self.assertEqual(result["source_kind"], "demo")
        self.assertTrue(item["warnings"])

    def test_research_remains_available_when_execution_unknown(self):
        d = dataset()
        d["bars"][1]["up_limit"] = None
        identified(d)
        self.assertTrue(research(d)["symbols"][0]["warnings"])

    def test_twenty_returns_require_twenty_one_closes(self):
        d = dataset(tuple(range(10, 31)))
        item = research(d)["symbols"][0]
        self.assertEqual(item["return_20d"], 2)
        self.assertTrue(math.isfinite(item["volatility_20d"]))
        self.assertEqual(item["max_drawdown"], 0)


if __name__ == "__main__":
    unittest.main()
