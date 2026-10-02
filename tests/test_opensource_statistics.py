"""Actual optional APIs, deterministic fixtures and bounded numeric contracts."""

from __future__ import annotations

import importlib.util
import json
import math
import unittest
from unittest.mock import patch

from invest.opensource.statistics import _number, run


VALUES = [math.sin(index * 1.7) + (index % 5) / 10 for index in range(64)]


class StatisticsInputTests(unittest.TestCase):
    def test_reject_unknown_adapter(self) -> None:
        for name in ["os", "", [], None]:
            with self.assertRaisesRegex(ValueError, "unknown"):
                run(name, {"values": VALUES})

    def test_nonfinite_backend_numbers_are_not_serialized(self) -> None:
        for value in [float("nan"), float("inf"), -float("inf")]:
            with self.assertRaisesRegex(ValueError, "undefined numeric"):
                _number(value)

    def test_bad_input_before_any_import(self) -> None:
        invalid = [
            {}, {"values": VALUES, "path": "input.csv"}, {"values": "file.csv"},
            {"values": [1] * 7}, {"values": [1] * 5001},
            *[{"values": [1] * 8 + [value]} for value in
              [True, None, "1", float("nan"), float("inf"), 1000001]],
        ]
        with patch("invest.opensource.statistics.load_dependency") as dependency:
            for name in ["statsmodels", "arch", "scipy"]:
                for payload in invalid:
                    with self.subTest(name=name, payload=payload):
                        with self.assertRaises(ValueError):
                            run(name, payload)
            dependency.assert_not_called()

    def test_dependency_failure_has_no_native_fallback(self) -> None:
        with patch("invest.opensource.statistics.load_dependency",
                   side_effect=ValueError("Optional backend unavailable")):
            for name in ["statsmodels", "arch", "scipy"]:
                with self.subTest(name=name):
                    with self.assertRaisesRegex(ValueError, "unavailable"):
                        run(name, {"values": VALUES})


@unittest.skipUnless(importlib.util.find_spec("statsmodels"), "optional statsmodels absent")
class StatsmodelsAdapterTests(unittest.TestCase):
    def test_matches_actual_backend(self) -> None:
        from statsmodels.stats.diagnostic import acorr_ljungbox
        from statsmodels.tsa.stattools import acf

        result = run("statsmodels", {"values": VALUES})
        expected = acf(VALUES, nlags=5, fft=False, missing="raise")
        for actual, reference in zip(result["acf"], expected):
            self.assertAlmostEqual(actual, reference, places=12)
        box = acorr_ljungbox(VALUES, lags=[5], model_df=0, return_df=True)
        self.assertAlmostEqual(result["ljung_box"]["pvalue"], box["lb_pvalue"].iloc[0])
        self.assertEqual(result, run("statsmodels", {"values": VALUES}))
        json.dumps(result, allow_nan=False)

    def test_minimum_count_and_bounded_lags(self) -> None:
        self.assertEqual(run("statsmodels", {"values": list(range(8))})["max_lag"], 2)
        large = run("statsmodels", {"values": [math.sin(i) for i in range(5000)]})
        self.assertEqual(len(large["acf"]), 6)
        json.dumps(large, allow_nan=False)

    def test_constant_and_near_constant_are_explicit_null(self) -> None:
        for values, status in [([0] * 8, "CONSTANT_SERIES"),
                               ([1.0 + i * 1e-14 for i in range(8)], "NUMERICALLY_NEAR_CONSTANT")]:
            result = run("statsmodels", {"values": values})
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["acf"])
            self.assertIsNone(result["ljung_box"])
            json.dumps(result, allow_nan=False)

    def test_tiny_numbers_scale_without_underflow(self) -> None:
        tiny = run("statsmodels", {"values": [v * 1e-200 for v in VALUES]})
        normal = run("statsmodels", {"values": VALUES})
        self.assertAlmostEqual(tiny["ljung_box"]["statistic"], normal["ljung_box"]["statistic"])


@unittest.skipUnless(importlib.util.find_spec("arch"), "optional arch absent")
class ArchAdapterTests(unittest.TestCase):
    def test_matches_actual_variance_ratio(self) -> None:
        from arch.unitroot import VarianceRatio

        levels = [0.0]
        for value in VALUES:
            levels.append(levels[-1] + value)
        expected = VarianceRatio(levels, lags=2, trend="c", robust=True,
                                 overlap=True, debiased=True)
        result = run("arch", {"values": VALUES})
        self.assertAlmostEqual(result["variance_ratio"], expected.vr, places=12)
        self.assertAlmostEqual(result["statistic"], expected.stat, places=12)
        self.assertAlmostEqual(result["pvalue"], expected.pvalue, places=12)
        self.assertEqual(result["constructed_levels"], 65)
        self.assertIn("NOT interpreted as price", result["interpretation"])
        self.assertEqual(result, run("arch", {"values": VALUES}))
        json.dumps(result, allow_nan=False)

    def test_short_constant_and_unresolved_series_are_rejected(self) -> None:
        for values in [VALUES[:31], [0] * 32, [3] * 32,
                       [1.0 + i * 1e-15 for i in range(32)]]:
            with self.subTest(values=values):
                with self.assertRaises(ValueError):
                    run("arch", {"values": values})

    def test_exact_minimum_and_maximum_count(self) -> None:
        for values in [VALUES[:32], [math.sin(i * 1.7) for i in range(5000)]]:
            result = run("arch", {"values": values})
            self.assertEqual(result["observations"], len(values))
            json.dumps(result, allow_nan=False)

    def test_cumulative_precision_loss_is_not_a_fake_result(self) -> None:
        with self.assertRaisesRegex(ValueError, "loses increments"):
            run("arch", {"values": [1.0, 1e-30, -1.0, 0.5] * 8})


@unittest.skipUnless(importlib.util.find_spec("scipy"), "optional scipy absent")
class ScipyAdapterTests(unittest.TestCase):
    def test_matches_actual_distribution_and_normality(self) -> None:
        import numpy
        from scipy import stats

        result = run("scipy", {"values": VALUES})
        description = stats.describe(VALUES, ddof=1, bias=False, nan_policy="raise")
        self.assertAlmostEqual(result["mean"], description.mean, places=12)
        self.assertAlmostEqual(result["sample_variance"], description.variance, places=12)
        self.assertAlmostEqual(result["skewness_bias_corrected"], description.skewness, places=12)
        self.assertAlmostEqual(result["normality"]["pvalue"], stats.normaltest(VALUES).pvalue, places=12)
        self.assertAlmostEqual(result["quantiles_linear"]["p50"], numpy.median(VALUES))
        json.dumps(result, allow_nan=False)
        self.assertEqual(result, run("scipy", {"values": VALUES}))

    def test_minimum_sample_gets_caution(self) -> None:
        result = run("scipy", {"values": list(range(8))})
        self.assertIn("SMALL_SAMPLE_NORMALITY_APPROXIMATION", result["warnings"])
        self.assertEqual(result["quantiles_linear"]["p50"], 3.5)
        json.dumps(result, allow_nan=False)

    def test_constant_defined_moments_and_null_undefined_moments(self) -> None:
        for value in [0, 10, 1e6, -1e6]:
            result = run("scipy", {"values": [value] * 8})
            self.assertEqual(result["mean"], value)
            self.assertEqual(result["sample_variance"], 0)
            self.assertIsNone(result["skewness_bias_corrected"])
            self.assertIsNone(result["excess_kurtosis_bias_corrected"])
            self.assertIsNone(result["normality"]["pvalue"])
            json.dumps(result, allow_nan=False)

    def test_near_constant_and_tiny_variance_are_not_fake_precision(self) -> None:
        near = run("scipy", {"values": [1 + i * 1e-14 for i in range(8)]})
        self.assertEqual(near["normality"]["status"], "NUMERICALLY_NEAR_CONSTANT")
        tiny = run("scipy", {"values": [v * 1e-200 for v in VALUES]})
        self.assertIsNone(tiny["sample_variance"])
        self.assertIn("VARIANCE_BELOW_FLOAT_RANGE", tiny["warnings"])
        json.dumps(tiny, allow_nan=False)

    def test_normalization_underflow_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "normalization"):
            run("scipy", {"values": [1e6, 5e-324] * 4})


if __name__ == "__main__":
    unittest.main()
