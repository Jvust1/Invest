"""Explicit caller-supplied history is never an implicit market-data fallback."""
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal
import hashlib
import json
import unittest
from unittest.mock import patch

from invest.chat.price_quality import ADJUSTMENTS, SHANGHAI, analyze_price_series


def bar(day="2020-01-01", close=10, **extra):
    return {"date": day, "open": close, "high": close, "low": close,
            "close": close, **extra}


class PriceQualityTests(unittest.TestCase):
    def call(self, bars=None, **kwargs):
        args = {"symbol": "600519.SH", "bars": bars if bars is not None else [bar()],
                "currency": "CNY", "source": "SYNTHETIC TEST FIXTURE", "as_of": "2020-01-10"}
        args.update(kwargs)
        return analyze_price_series(**args)

    def codes(self, result):
        return {item["code"] for item in result["warnings"]}

    def test_single_point_has_no_returns_or_risk_estimate(self):
        result = self.call()
        self.assertEqual(result["observations"], 1)
        self.assertIsNone(result["close_to_close"]["total_price_return"])
        self.assertIsNone(result["historical_risk"]["metrics"])
        self.assertEqual(result["historical_risk"]["status"], "INSUFFICIENT_RETURNS")
        self.assertIn("INSUFFICIENT_RETURNS", self.codes(result))
        self.assertNotIn("bars", result)

    def test_two_points_return_but_no_sample_risk(self):
        result = self.call([bar(), bar("2020-01-02", 11)])
        self.assertAlmostEqual(result["close_to_close"]["total_price_return"], 0.1)
        self.assertEqual(result["close_to_close"]["observations"], 1)
        self.assertIsNone(result["historical_risk"]["metrics"])

    def test_metrics_reuse_initial_wealth_drawdown(self):
        result = self.call([bar(close=10), bar("2020-01-02", 8), bar("2020-01-03", 9)])
        risk = result["historical_risk"]
        self.assertEqual(risk["status"], "DESCRIPTIVE_ONLY")
        self.assertAlmostEqual(risk["metrics"]["cumulative_return"], -0.1)
        self.assertAlmostEqual(risk["metrics"]["max_drawdown"], -0.2)
        self.assertAlmostEqual(result["close_to_close"]["latest_return"], 0.125)

    def test_constant_prices_undefined_ratios_are_null(self):
        result = self.call([bar(), bar("2020-01-02"), bar("2020-01-03")])
        metrics = result["historical_risk"]["metrics"]
        self.assertEqual(metrics["annual_volatility"], 0)
        self.assertIsNone(metrics["sharpe_zero_rf"])
        self.assertIsNone(metrics["sortino_zero_target"])
        json.dumps(result, allow_nan=False)

    def test_safety_labels_and_declarations_are_preserved(self):
        result = self.call(source="证券资料：调用者自填，不等于核验", currency="USD")
        self.assertEqual(result["status"], "CALLER_SUPPLIED")
        self.assertEqual(result["currency"], "USD")
        for field in ("independently_verified", "real_time", "executable_quote",
                      "execution_authorized", "automatic_orders_supported", "implicit_fallback"):
            self.assertIs(result[field], False)
        self.assertIn("LICENSE_UNVERIFIED", self.codes(result))
        self.assertIn("SOURCE_UNVERIFIED", self.codes(result))

    def test_staleness_boundary_and_zero_threshold(self):
        result = self.call(as_of="2020-01-08", max_staleness_days=7)
        self.assertFalse(result["stale"])
        self.assertNotIn("STALE_DATA", self.codes(result))
        self.assertTrue(self.call(as_of="2020-01-09")["stale"])
        self.assertFalse(self.call(as_of="2020-01-01", max_staleness_days=0)["stale"])
        self.assertTrue(self.call(as_of="2020-01-02", max_staleness_days=0)["stale"])

    def test_gap_does_not_claim_missing_trading_days(self):
        result = self.call([bar(), bar("2020-01-04"), bar("2020-01-05")])
        self.assertEqual(result["calendar_gaps"], {"count": 1, "max_gap_days": 3,
                                                  "exchange_calendar_checked": False})
        warning = next(w for w in result["warnings"] if w["code"] == "CALENDAR_GAPS")
        self.assertIn("not proof of missing trading days", warning["message"])

    def test_optional_partial_volume_and_units(self):
        result = self.call([bar(volume=0), bar("2020-01-02", volume=1e18), bar("2020-01-03")])
        self.assertEqual(result["volume_observations"], 2)
        self.assertTrue({"PARTIAL_VOLUME", "VOLUME_UNIT_UNVERIFIED"} <= self.codes(result))
        self.assertNotIn("PARTIAL_VOLUME", self.codes(self.call([bar(volume=0)])))

    def test_all_adjustment_labels_remain_unverified(self):
        for adjustment in ADJUSTMENTS:
            with self.subTest(adjustment=adjustment):
                result = self.call(adjustment=adjustment)
                self.assertEqual(result["adjustment"], adjustment)
                self.assertFalse(result["close_to_close"]["is_total_return_verified"])
        self.assertIn("ADJUSTMENT_UNKNOWN", self.codes(self.call()))
        self.assertIn("UNADJUSTED_PRICES", self.codes(self.call(adjustment="unadjusted")))
        self.assertIn("ADJUSTMENT_UNVERIFIED", self.codes(self.call(adjustment="split_adjusted")))

    def test_hash_deterministic_numeric_normalization_and_order(self):
        result = self.call([bar(close=10, volume=0)])
        reordered = {"volume": 0.0, "close": 10.0, "date": "2020-01-01", "low": 10.0,
                     "high": 10.0, "open": 10.0}
        self.assertEqual(result["data_sha256"], self.call([reordered])["data_sha256"])
        canonical = json.dumps([reordered], ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"), allow_nan=False)
        self.assertEqual(result["data_sha256"], hashlib.sha256(canonical.encode()).hexdigest())
        changed_metadata = self.call([bar(close=10, volume=0)], source="another declared source")
        self.assertEqual(result["data_sha256"], changed_metadata["data_sha256"])
        self.assertNotEqual(result["request_sha256"], changed_metadata["request_sha256"])
        self.assertNotEqual(result["data_sha256"], self.call([bar(close=11, volume=0)])["data_sha256"])

    def test_input_not_mutated(self):
        bars = [bar(volume=3), bar("2020-01-03")]
        original = deepcopy(bars)
        self.call(bars)
        self.assertEqual(bars, original)
        self.assertIs(type(bars[0]["close"]), int)

    def test_symbol_boundaries_and_supported_labels(self):
        for symbol in ("A", "A" * 40, "^GSPC", "BTC/USD", "BRK.B", "HK:0700", "USD-CNY=X"):
            self.assertEqual(self.call(symbol=symbol)["symbol"], symbol)
        for symbol in ("", "A" * 41, " 600519.SH", "a b", "../file", "股票", "A\n", None, 600519):
            with self.subTest(symbol=symbol), self.assertRaises(ValueError):
                self.call(symbol=symbol)

    def test_currency_format_is_ascii_uppercase_not_claimed_verified(self):
        for currency in ("", "cny", "CN", "CNYX", " CNY", "ＣＮＹ", 123, None):
            with self.subTest(currency=currency), self.assertRaises(ValueError):
                self.call(currency=currency)

    def test_source_limits_controls_and_whitespace(self):
        self.assertEqual(self.call(source="x" * 300)["source"], "x" * 300)
        for source in ("", "x" * 301, " a", "a ", "a\n", "a\t", "a\x00", "a\x7f", "a\u200b", None, 3):
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.call(source=source)

    def test_declarations_do_not_trigger_network_or_path_access(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("network forbidden")), \
                patch("builtins.open", side_effect=AssertionError("file access forbidden")):
            result = self.call(source="https://example.invalid/private?token=not-a-real-token")
        self.assertFalse(result["independently_verified"])

    def test_invalid_adjustment_and_staleness(self):
        for adjustment in ("qfq", "", [], None, True):
            with self.subTest(adjustment=adjustment), self.assertRaises(ValueError):
                self.call(adjustment=adjustment)
        for threshold in (-1, 3661, 1.0, "7", None, True):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                self.call(max_staleness_days=threshold)
        self.assertFalse(self.call(max_staleness_days=3660)["stale"])

    def test_bar_count_and_container_types(self):
        for bars in ([], (), {}, "bars", [bar()] * 5001):
            with self.subTest(kind=type(bars).__name__), self.assertRaises(ValueError):
                self.call(bars)
        with self.assertRaises(ValueError):
            analyze_price_series("TEST", None, "CNY", "SYNTHETIC", "2020-01-01")

    def test_maximum_5000_observations_is_accepted(self):
        first = date(2000, 1, 1)
        bars = [bar((first + timedelta(days=i)).isoformat(), 10) for i in range(5000)]
        result = self.call(bars, as_of=bars[-1]["date"])
        self.assertEqual(result["observations"], 5000)
        self.assertEqual(result["close_to_close"]["observations"], 4999)
        self.assertEqual(result["historical_risk"]["metrics"]["cumulative_return"], 0)

    def test_rows_need_exact_allowed_fields(self):
        for row in (None, [], "row", {"date": "2020-01-01"}, {**bar(), "note": "ignored?"},
                    {**bar(), "volume_provider_units": 3}, {**bar(), "adjusted_close": 10}):
            with self.subTest(row=row), self.assertRaises(ValueError):
                self.call([row])
        for field in ("date", "open", "high", "low", "close"):
            row = bar()
            del row[field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.call([row])

    def test_invalid_or_noncanonical_dates(self):
        for value in ("20200101", "2020-1-01", "2020-01-1", "2020-02-30", "2020-01-01T00:00:00",
                      "2020-W01-3", "0000-01-01", "２０２０-01-01", 20200101, True, None):
            for field in ("bar", "as_of"):
                with self.subTest(value=value, field=field), self.assertRaises(ValueError):
                    self.call([bar(value)]) if field == "bar" else self.call(as_of=value)

    def test_valid_leap_date_and_earliest_date(self):
        self.assertEqual(self.call([bar("2020-02-29")], as_of="2020-02-29")["start_date"], "2020-02-29")
        self.assertEqual(self.call([bar("0001-01-01")], as_of="0001-01-01")["start_date"], "0001-01-01")

    def test_future_and_as_of_cutoff_rejected(self):
        future = (datetime.now(SHANGHAI).date() + timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            self.call(as_of=future)
        with self.assertRaises(ValueError):
            self.call([bar(future)])
        with self.assertRaises(ValueError):
            self.call([bar("2020-01-02")], as_of="2020-01-01")

    def test_duplicate_or_decreasing_dates_rejected_without_sorting(self):
        for bars in ([bar(), bar()], [bar("2020-01-02"), bar()]):
            with self.assertRaises(ValueError):
                self.call(bars)

    def test_price_numeric_types_nonfinite_and_extremes(self):
        bad_values = (True, False, "10", "NaN", None, Decimal("10"), float("nan"),
                      float("inf"), -float("inf"), 0, -1, 1e-9, 1e13, 10 ** 400)
        for field in ("open", "high", "low", "close"):
            for value in bad_values:
                with self.subTest(field=field, value_type=type(value).__name__), self.assertRaises(ValueError):
                    self.call([{**bar(), field: value}])
        for close in (1e-8, 1e12):
            self.assertEqual(self.call([bar(close=close)])["observations"], 1)

    def test_ohlc_relationships(self):
        for values in ({"low": 11}, {"high": 9}, {"open": 11}, {"close": 9},
                       {"low": 12, "high": 8}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.call([{**bar(), **values}])
        result = self.call([bar(close=10, open=11, high=12, low=9)])
        self.assertEqual(result["observations"], 1)

    def test_volume_numeric_types_bounds_and_nonfinite(self):
        for volume in (True, "0", None, -1, 1e19, 10 ** 18 + 1, float("nan"), float("inf"), 10 ** 400):
            with self.subTest(volume_type=type(volume).__name__), self.assertRaises(ValueError):
                self.call([bar(volume=volume)])

    def test_extreme_finite_prices_do_not_report_invalid_risk(self):
        result = self.call([bar(close=1e12), bar("2020-01-02", 1e-8), bar("2020-01-03", 1)])
        self.assertEqual(result["historical_risk"]["status"], "NUMERIC_RANGE_EXCEEDED")
        self.assertIsNone(result["historical_risk"]["metrics"])
        self.assertIn("RISK_NUMERIC_RANGE", self.codes(result))
        json.dumps(result, allow_nan=False)

    def test_annualized_overflow_is_unavailable_not_fabricated(self):
        result = self.call([bar(close=1e-8), bar("2020-01-02", 1), bar("2020-01-03", 1e12)])
        self.assertEqual(result["historical_risk"]["status"], "NUMERIC_RANGE_EXCEEDED")
        self.assertIsNone(result["historical_risk"]["metrics"])
        json.dumps(result, allow_nan=False)

    def test_cancellation_round_trip_does_not_invent_gain_or_risk(self):
        for closes in ([1e8, 1e-8, 1e8], [1e-8, 1e8, 1e-8]):
            with self.subTest(closes=closes):
                bars = [bar(f"2020-01-{i + 1:02}", close) for i, close in enumerate(closes)]
                result = self.call(bars)
                self.assertEqual(result["close_to_close"]["total_price_return"], 0)
                self.assertEqual(result["historical_risk"]["status"], "NUMERIC_RANGE_EXCEEDED")
                self.assertIsNone(result["historical_risk"]["metrics"])
                self.assertIn("RISK_NUMERIC_RANGE", self.codes(result))
                json.dumps(result, allow_nan=False)

    def test_intermediate_cancellation_is_rejected_even_if_final_wealth_matches(self):
        # Opposite rounding errors cancel at the final point, but not at the
        # intervening high/low. Checking only terminal wealth would miss this.
        closes = [1e8, 1e-8, 1e8, 1.232595164407831e-8, 1e8]
        reconstructed = 1.0
        for previous, current in zip(closes, closes[1:]):
            reconstructed *= 1 + (current / previous - 1)
        self.assertAlmostEqual(reconstructed, closes[-1] / closes[0], delta=1e-12)
        bars = [bar(f"2020-01-{i + 1:02}", close) for i, close in enumerate(closes)]
        result = self.call(bars)
        self.assertEqual(result["historical_risk"]["status"], "NUMERIC_RANGE_EXCEEDED")
        self.assertIsNone(result["historical_risk"]["metrics"])

    def test_5000_nonconstant_prices_tolerate_ordinary_roundoff(self):
        first = date(2000, 1, 1)
        bars = [bar((first + timedelta(days=i)).isoformat(), 10 * 1.00001 ** i)
                for i in range(5000)]
        result = self.call(bars, as_of=bars[-1]["date"])
        self.assertEqual(result["historical_risk"]["status"], "DESCRIPTIVE_ONLY")
        self.assertAlmostEqual(result["historical_risk"]["metrics"]["cumulative_return"],
                               result["close_to_close"]["total_price_return"], delta=1e-10)
        self.assertEqual(result["historical_risk"]["metrics"]["max_drawdown"], 0)


if __name__ == "__main__":
    unittest.main()
