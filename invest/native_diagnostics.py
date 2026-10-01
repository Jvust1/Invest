"""Saved evaluation-return diagnostics using the pinned, optional statsmodels SDK.

This is descriptive research output, not a significance/profitability gate.
Records are fully revalidated before SDK discovery; no producer is re-executed.
"""
from copy import deepcopy
from importlib import metadata
import math
import threading

from .native_research import validate_native_record
from .workspace import digest

SCHEMA = 'invest-native-diagnostics-v1'
STATSMODELS_VERSION = '0.15.0'
SOURCE_REVISION = '278ff9950636cdd4939b4055e339a8e681d79cab'
MIN_OBSERVATIONS = 30  # Conservative reporting floor; not a validity guarantee.
MAX_OBSERVATIONS = 10_000
MAX_RETURN_MAGNITUDE = 1_000_000.0
_LOCK = threading.Lock()


class DiagnosticsUnavailable(RuntimeError):
    pass


class DiagnosticsBusy(RuntimeError):
    pass


def _sample(values):
    """Bound finite values and normalize centered returns without overflow."""
    if not isinstance(values, list) or not 1 <= len(values) <= MAX_OBSERVATIONS:
        raise ValueError('diagnostics require 1 to 10000 saved evaluation returns')
    if any(type(x) not in (int, float) or not math.isfinite(x)
           or abs(x) > MAX_RETURN_MAGNITUDE for x in values):
        raise ValueError('diagnostic returns must be finite and bounded by 1000000')
    n = len(values)
    lag = min(10, n // 5)
    if n < MIN_OBSERVATIONS:
        return 'insufficient_observations', lag, None
    if all(x == values[0] for x in values):
        return 'constant_series', lag, None
    center = math.fsum(values) / n
    centered = [x - center for x in values]
    scale = max(abs(x) for x in centered)
    if scale == 0:
        return 'constant_series', lag, None
    normalized = [x / scale for x in centered]
    if not all(math.isfinite(x) for x in normalized):
        raise ValueError('diagnostic normalization is not finite')
    return 'computed', lag, normalized


def _finite(value, *, probability=False):
    value = float(value)
    if not math.isfinite(value) or (probability and not 0 <= value <= 1):
        raise ValueError('statsmodels returned an invalid diagnostic value')
    return value


def native_diagnostics(record):
    """Return an identity-bound derivative of only the saved evaluation suffix."""
    if not _LOCK.acquire(blocking=False):
        raise DiagnosticsBusy('已有原生统计诊断正在运行，请稍后重试')
    try:
        validate_native_record(record)
        payload = record['payload']
        curve = payload['curve']
        position = curve['columns'].index('strategy_return')
        values = [row[position] for row in curve['rows']]
        status, lag, normalized = _sample(values)
        try:
            version = metadata.version('statsmodels')
        except metadata.PackageNotFoundError:
            raise DiagnosticsUnavailable('统计诊断需要可选 diagnostics 扩展（statsmodels 0.15.0）；保存研究仍保留') from None
        if version != STATSMODELS_VERSION:
            raise DiagnosticsUnavailable('统计诊断需要已验证的 statsmodels 0.15.0；请安装 diagnostics 扩展')
        results = None
        if status == 'computed':
            try:
                from statsmodels.stats.diagnostic import acorr_ljungbox
                from statsmodels.stats.stattools import durbin_watson, jarque_bera
            except ImportError:
                raise DiagnosticsUnavailable('statsmodels 依赖无法载入；请重新安装 diagnostics 扩展') from None
            # One predetermined Ljung-Box lag, no automatic lag search or model
            # fitting. All three functions receive centered, scale-normalized
            # returns. Scaling does not change these statistics.
            lb = acorr_ljungbox(normalized, lags=[lag], model_df=0,
                               period=None, return_df=True, auto_lag=False)
            jb, jbp, skew, kurtosis = jarque_bera(normalized)
            results = {
                'ljung_box': {'lag': lag, 'statistic': _finite(lb['lb_stat'].iloc[0]),
                              'asymptotic_pvalue': _finite(lb['lb_pvalue'].iloc[0], probability=True)},
                'jarque_bera': {'statistic': _finite(jb),
                               'asymptotic_pvalue': _finite(jbp, probability=True),
                               'skewness': _finite(skew), 'pearson_kurtosis': _finite(kurtosis)},
                'durbin_watson_centered': _finite(durbin_watson(normalized)),
            }
        result = {
            'schema': SCHEMA, 'record_id': record['id'], 'record_sha256': digest(record),
            'curve_sha256': digest(curve), 'returns_sha256': digest(values),
            'series': 'saved_later_evaluation_strategy_return', 'observations': len(values),
            'evaluation_start': curve['dates'][0], 'evaluation_end': curve['dates'][-1],
            'status': status, 'results': results,
            'input_role': payload['input_role'],
            'source_declaration': deepcopy(payload['snapshot']),
            'producer_declaration': deepcopy(payload['producer']),
            'recorded_at_declaration': record['recorded_at'],
            'protocol': {'lag': lag, 'lag_rule': 'min(10, evaluation_observations // 5)',
                         'minimum_observations': MIN_OBSERVATIONS, 'model_df': 0,
                         'centered_and_scaled': True, 'automatic_lag_search': False,
                         'model_fitted': False, 'alpha_or_pass_fail_decision': None},
            'upstream': {'repository': 'statsmodels/statsmodels', 'version': version,
                         'revision': SOURCE_REVISION, 'license': 'BSD-3-Clause'},
            'limitations': ['Exploratory descriptive diagnostics, not investment advice or proof of profitability.',
                'P-values are asymptotic, unadjusted across diagnostics, and can be unreliable in small/dependent samples.',
                'No correction for strategy selection, multiple research attempts, or unobserved market/data biases.',
                'A large p-value does not prove normality, independence, market validity, or a profitable strategy.',
                'Diagnostic statistics use only saved evaluation returns; validation rechecks all recorded input/trial arithmetic, without provider or optimizer execution.',
                'Native price/volume units remain unverified and distinct from cash execution.',
                'Source, producer and timestamp remain declarations, not authenticated provenance.'],
        }
        result['diagnostics_id'] = digest(result)
        return result
    finally:
        _LOCK.release()
