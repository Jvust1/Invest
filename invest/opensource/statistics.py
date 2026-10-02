"""Lazy, bounded statistical adapters; inputs are ordered caller observations.

Official API references (no third-party code is vendored):
https://www.statsmodels.org/stable/generated/statsmodels.tsa.stattools.acf.html
https://www.statsmodels.org/stable/generated/statsmodels.stats.diagnostic.acorr_ljungbox.html
https://arch.readthedocs.io/en/latest/unitroot/generated/arch.unitroot.VarianceRatio.html
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.describe.html
https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.normaltest.html
"""

from __future__ import annotations

import math
from typing import Any
import warnings

from .common import load_dependency, validated_series


def _number(value: Any) -> float:
    """Reject backend numeric failures rather than emitting non-JSON numbers."""
    result = float(value)
    if not math.isfinite(result):
        raise ValueError("statistical backend produced an undefined numeric result")
    return result


def _scaled(values: list[float]) -> tuple[list[float], float, str | None]:
    """Scale to avoid powers of tiny/large values in moment calculations."""
    scale = max(abs(value) for value in values) or 1.0
    normalized = [value / scale for value in values]
    if any(value != 0.0 and item == 0.0 for value, item in zip(values, normalized)):
        raise ValueError("numeric range loses observations during normalization")
    width = max(normalized) - min(normalized)
    reason = None
    if max(values) == min(values):
        reason = "CONSTANT_SERIES"
    elif width <= 1e-12:
        reason = "NUMERICALLY_NEAR_CONSTANT"
    return normalized, scale, reason


def _statsmodels(values: list[float]) -> dict[str, Any]:
    """Compute a bounded ACF and one predeclared Ljung-Box test."""
    stattools = load_dependency("statsmodels.tsa.stattools", "statsmodels")
    diagnostic = load_dependency("statsmodels.stats.diagnostic", "statsmodels")
    normalized, _, reason = _scaled(values)
    lag = min(5, len(values) // 4)
    result: dict[str, Any] = {
        "method": "acf_and_ljung_box",
        "observations": len(values),
        "max_lag": lag,
        "acf": None,
        "ljung_box": None,
        "status": reason or "DESCRIPTIVE_ONLY",
        "interpretation": (
            "Ljung-Box null: no serial autocorrelation through max_lag; "
            "a p-value is not proof of independence, stationarity or predictability. "
            "Input order is retained; equal sampling intervals are assumed, not verified."
        ),
    }
    if reason:
        return result
    correlations = stattools.acf(
        normalized, adjusted=False, nlags=lag, fft=False, missing="raise"
    )
    box = diagnostic.acorr_ljungbox(
        normalized, lags=[lag], model_df=0, return_df=True
    )
    result["acf"] = [_number(value) for value in correlations]
    result["ljung_box"] = {
        "lag": lag,
        "statistic": _number(box["lb_stat"].iloc[0]),
        "pvalue": _number(box["lb_pvalue"].iloc[0]),
        "null_hypothesis": "no serial autocorrelation through the declared lag",
    }
    return result


def _arch(values: list[float]) -> dict[str, Any]:
    """Treat supplied observations explicitly as additive increments, not prices."""
    unitroot = load_dependency("arch.unitroot", "arch")
    if len(values) < 32:
        raise ValueError("arch variance-ratio diagnostic requires at least 32 increments")
    normalized, _, reason = _scaled(values)
    if reason:
        raise ValueError("arch requires non-constant, numerically resolved increments")
    levels = [0.0]
    for increment in normalized:
        levels.append(levels[-1] + increment)
        recovered = levels[-1] - levels[-2]
        if not math.isclose(recovered, increment, rel_tol=1e-10, abs_tol=0.0):
            raise ValueError("numeric range loses increments during cumulative construction")
    test = unitroot.VarianceRatio(
        levels, lags=2, trend="c", robust=True, overlap=True, debiased=True
    )
    return {
        "method": "variance_ratio_of_cumulative_increments",
        "status": "DESCRIPTIVE_ONLY",
        "observations": len(values),
        "constructed_levels": len(levels),
        "lag": 2,
        "trend": "c",
        "heteroskedasticity_robust": True,
        "overlapping": True,
        "debiased": True,
        "variance_ratio": _number(test.vr),
        "statistic": _number(test.stat),
        "pvalue": _number(test.pvalue),
        "null_hypothesis": "the cumulative process is a random walk with possible drift",
        "interpretation": (
            "Values are additive increments, scaled by a common positive constant and "
            "cumulatively summed from zero; they are NOT interpreted as price levels "
            "or compounded simple returns. Equal intervals are assumed, not verified. "
            "The asymptotic p-value is exploratory, especially for short samples; "
            "it establishes neither profitability nor a trading signal."
        ),
    }


def _scipy(values: list[float]) -> dict[str, Any]:
    """Report distribution moments and normality without NaN constant results."""
    stats = load_dependency("scipy.stats", "scipy")
    numpy = load_dependency("numpy", "numpy")
    normalized, scale, reason = _scaled(values)
    notes = []
    if reason:
        # SciPy remains the calculator; undefined standardized moments are not zero.
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            mean = _number(stats.tmean(normalized)) * scale
            scaled_variance = _number(stats.tvar(normalized, ddof=1))
        if captured:
            notes.append("BACKEND_DEGENERATE_MOMENT_WARNING")
        skewness = kurtosis = None
        normality = {"status": reason, "statistic": None, "pvalue": None}
    else:
        description = stats.describe(normalized, ddof=1, bias=False, nan_policy="raise")
        mean = _number(description.mean) * scale
        scaled_variance = _number(description.variance)
        skewness = _number(description.skewness)
        kurtosis = _number(description.kurtosis)
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            normal = stats.normaltest(normalized, nan_policy="raise")
        if captured:
            # Expose a stable caution, not arbitrary backend warning payloads.
            notes.append("BACKEND_NORMALITY_APPROXIMATION_WARNING")
        normality = {
            "status": "EXPLORATORY",
            "statistic": _number(normal.statistic),
            "pvalue": _number(normal.pvalue),
        }
    variance = scaled_variance * scale * scale
    if scaled_variance > 0.0 and variance == 0.0:
        variance = None
        notes.append("VARIANCE_BELOW_FLOAT_RANGE")
    if len(values) < 20:
        notes.append("SMALL_SAMPLE_NORMALITY_APPROXIMATION")
    quantiles = numpy.quantile(values, [0.05, 0.25, 0.5, 0.75, 0.95], method="linear")
    return {
        "method": "distribution_and_dagostino_pearson_normality",
        "status": reason or "DESCRIPTIVE_ONLY",
        "observations": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "mean": _number(mean),
        "sample_variance": None if variance is None else _number(variance),
        "variance_ddof": 1,
        "skewness_bias_corrected": skewness,
        "excess_kurtosis_bias_corrected": kurtosis,
        "quantiles_linear": {
            label: _number(value)
            for label, value in zip(["p05", "p25", "p50", "p75", "p95"], quantiles)
        },
        "normality": normality,
        "warnings": notes,
        "interpretation": (
            "Normality null: observations follow a normal distribution. The omnibus "
            "test uses skewness and kurtosis with asymptotic calibration; dependence "
            "and small samples can invalidate its interpretation. A large p-value "
            "does not prove normality, safe tails or future investment performance."
        ),
    }


def run(name: str, payload: dict) -> dict[str, Any]:
    """Run exactly one allowlisted installed backend on bounded caller data."""
    implementations = {"statsmodels": _statsmodels, "arch": _arch, "scipy": _scipy}
    if not isinstance(name, str) or name not in implementations:
        raise ValueError("unknown statistical backend")
    values = validated_series(payload)
    return implementations[name](values)
