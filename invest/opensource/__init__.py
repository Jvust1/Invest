"""Allowlisted, lazy, offline access to actually integrated open-source engines."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import hashlib
from importlib import metadata
import importlib.util
import json

from .common import validated_series

# Dispatch modules and functions are fixed in source, never resolved from caller code.
PROFILES = {
    'polars': ('polars', 'polars', '1.44.2', 'pola-rs/polars', 'columnar_descriptive_statistics', 8),
    'duckdb': ('duckdb', 'duckdb', '1.5.6', 'duckdb/duckdb', 'in_memory_sql_statistics', 8),
    'pyarrow': ('pyarrow', 'pyarrow', '25.0.1', 'apache/arrow', 'arrow_table_statistics', 8),
    'statsmodels': ('statsmodels', 'statsmodels', '0.15.0', 'statsmodels/statsmodels', 'autocorrelation_diagnostics', 8),
    'arch': ('arch', 'arch', '8.0.0', 'bashtage/arch', 'variance_ratio_diagnostics', 32),
    'scipy': ('scipy', 'scipy', '1.18.1', 'scipy/scipy', 'distribution_diagnostics', 8),
    'ta': ('ta', 'ta', '0.11.0', 'bukosabino/ta', 'technical_features', 26),
    'ffn': ('ffn', 'ffn', '1.2.2', 'pmorissette/ffn', 'price_path_performance', 8),
    'networkx': ('networkx', 'networkx', '3.7', 'networkx/networkx', 'direction_transition_graph', 8),
    'plotly': ('plotly', 'plotly', '7.1.0', 'plotly/plotly.py', 'chart_specification', 8),
    'sklearn': ('sklearn', 'scikit-learn', '1.9.1', 'scikit-learn/scikit-learn', 'chronological_model_comparison', 24),
}


def _version(distribution):
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:
        return None


def integration_catalog() -> dict:
    from ..upstreams import load_registry
    upstreams = {x['repo']: x for x in load_registry()['projects']}
    entries = []
    for key, (module, dist, tested, repo, capability, minimum) in PROFILES.items():
        installed = _version(dist)
        try:
            discoverable = importlib.util.find_spec(module) is not None
        except (ImportError, ValueError, ModuleNotFoundError):
            discoverable = False
        upstream = upstreams.get(repo, {})
        entries.append({'backend': key, 'repository': repo, 'url': 'https://github.com/' + repo,
                        'capability': capability, 'distribution': dist,
                        'installed_version': installed, 'module_discoverable': discoverable,
                        'tested_version': tested, 'matches_tested_version': installed == tested,
                        'runtime_execution_verified': False,
                        'minimum_observations': minimum, 'maximum_observations': 5000,
                        'software_license': upstream.get('license', 'NOT_RECORDED'),
                        'license_review': upstream.get('license_review'),
                        'github_stars_snapshot': upstream.get('stars'),
                        'metadata_observed_at': upstream.get('metadata_observed_at'),
                        'input_semantics': 'positive price/NAV path' if key in {'ta', 'ffn'} else 'explicit ordered numeric observations; see backend interpretation'})
    return {'schema': 'invest-research-integrations-v1', 'count': len(entries), 'integrations': entries,
            'execution_scope': 'OFFLINE_CALLER_SUPPLIED_RESEARCH', 'automatic_installation': False,
            'notes': ['Module discovery and package metadata do not prove successful execution.',
                      'Pinned full research extra is tested on Python 3.12; the base install remains separate.',
                      'Stars are dated metadata, not a quality or investment-return guarantee.',
                      'Optional package use is not upstream source vendoring; software and market-data rights differ.']}


def run_integration(name: str, payload: dict, *, source: str, as_of: str) -> dict:
    if not isinstance(name, str) or name not in PROFILES:
        raise ValueError('unknown backend; use research_catalog for the fixed allowlist')
    values = validated_series(payload)
    if not isinstance(source, str) or not 1 <= len(source) <= 300 or not source.strip() or not source.isprintable():
        raise ValueError('source must be a printable caller declaration of 1-300 characters')
    if not isinstance(as_of, str):
        raise ValueError('as_of must be a canonical date')
    try:
        cutoff = date.fromisoformat(as_of)
    except ValueError:
        raise ValueError('as_of must be a canonical date') from None
    if cutoff.isoformat() != as_of or cutoff > datetime.now(timezone(timedelta(hours=8))).date():
        raise ValueError('as_of must be canonical and not in the future in Asia/Shanghai')
    if name in {'polars', 'duckdb', 'pyarrow'}:
        from .data_engines import run
    elif name in {'statsmodels', 'arch', 'scipy'}:
        from .statistics import run
    else:
        from .features import run
    # No URL, SQL, expression, package name, code, model file, or local path is executed.
    result = run(name, {'values': values})
    try:
        json.dumps(result, allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        raise ValueError('backend returned a non-finite or non-JSON result') from None
    module, dist, tested, repo, capability, minimum = PROFILES[name]
    request = {'backend': name, 'payload': payload, 'source': source, 'as_of': as_of}
    encoded = json.dumps(request, sort_keys=True, ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8')
    return {'schema': 'invest-research-result-v1', 'status': 'SCENARIO_ONLY', 'backend': name,
            'backend_version': _version(dist), 'tested_version': tested,
            'upstream_url': 'https://github.com/' + repo, 'capability': capability,
            'source': source, 'as_of': as_of, 'observations': len(values), 'input_sha256': hashlib.sha256(encoded).hexdigest(),
            'backend_executed': True, 'network_attempted': False, 'execution_authorized': False,
            'result': result,
            'limitations': ['Caller-supplied values are not independently authenticated, licensed or dated per observation.',
                            'as_of is a caller declaration, not data-freshness verification or a trading calendar.',
                            'Statistics, indicators, model scores and graphs are research outputs, not trade orders or guaranteed returns.']}


__all__ = ['integration_catalog', 'run_integration']
