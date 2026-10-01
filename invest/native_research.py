"""Durable native-Qlib research evidence, separate from cash execution studies.

The only producer runs the cache-only pipeline and saves immediately. Validation
replays bounded arithmetic from embedded rows; it never imports/calls an optional
SDK, reads provider files, or opens the original DuckDB database. Hashes identify
recorded claims and bytes, not market-data rights, authenticity or profitability.
Explicit JSON recovery preserves the original envelope without producing new
research or authenticating its producer/timestamp declarations.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from decimal import Decimal
from importlib import metadata
import json
import math
import platform
import re

import numpy as np
import pandas as pd

from .optuna_walkforward import _training_fingerprint, _walkforward_score
from .pipeline import moving_average_signal, performance_summary, run_backtest
from .providers.duckdb_cache import (_frame_digest, _json, _native_qlib_metadata,
    _normalize, _request, _sha, DuckDBReplayProvider)
from .provenance import runtime_manifest, validate_manifest
from .research_pipeline import run_a_share_research_bundle
from .workspace import Workspace, canonical, digest, instant

SCHEMA = 'invest-native-research-v1'
KIND = 'native_research'
MAX_BYTES = 8 * 1024 * 1024
MAX_ROWS = 10000
MAX_TRIALS = 100
CURVE_COLUMNS = ['close', 'signal', 'asset_return', 'turnover', 'strategy_return', 'equity']
VERSIONS = ('numpy', 'pandas', 'scikit-learn', 'duckdb', 'optuna', 'pyqlib', 'mlflow')
CONVENTIONS = {
    'scope': 'exploratory_close_to_close_signal_research_not_a_share_cash_execution',
    'equity': 'unit_capital_compounded_only_over_later_evaluation_returns',
    'drawdown': 'nonpositive_fraction_from_running_peak_including_initial_unit_capital',
    'annualized_return': 'geometric_252_observations_per_year',
    'annualized_volatility': 'sample_std_ddof_1_times_sqrt_252',
    'sharpe': 'annualized_arithmetic_sharpe_zero_risk_free',
    'fee': 'absolute_current_signal_change_times_fee_bps_over_10000',
    'position': 'previous_observation_signal_times_close_to_close_asset_return',
    'split_boundary': 'continue_prior_signal_no_artificial_entry_or_liquidation',
    'validation_tolerance': 'relative_1e-10_absolute_1e-12',
}
LIMITATIONS = {
    'frozen_holdout_opened': False,
    'native_price_and_volume_units_verified': False,
    'market_data_rights_or_authenticity_verified': False,
    'producer_identity_is_build_declaration_not_attestation': True,
    'qlib_network_and_tracking_declarations_scope': 'source_reader_only_not_entire_computation',
    'trial_replay_proves': 'recorded_candidate_arithmetic_and_maximum_not_sampler_history_or_optimality',
    'backup_contains': 'embedded_input_rows_in_state_sqlite_not_original_qlib_files_or_native_duckdb',
}
SPLIT_FIXED = {
    'mode': 'EXPLORATORY_PREFIX_SEARCH_LATER_EVALUATION',
    'frozen_holdout_opened': False,
    'scope': 'close_to_close_signal_research_not_a_share_cash_execution',
    'position_boundary': 'continuation_of_prior_signal; no artificial liquidation at split',
}


def _object(value, keys, name):
    if type(value) is not dict or set(value) != set(keys):
        raise ValueError(f'{name} must have exactly the declared keys')
    return value


def _int(value, lo, hi, name):
    if type(value) is not int or not lo <= value <= hi:
        raise ValueError(f'{name} is outside its integer bounds')
    return value


def _number(value, name):
    if type(value) not in (int, float) or not -1e308 <= value <= 1e308 or not math.isfinite(value):
        raise ValueError(f'{name} must be a finite JSON number')
    return value


def _version(value, *, nullable=False):
    if nullable and value is None:
        return
    if type(value) is not str or re.fullmatch(r'[0-9][A-Za-z0-9.+-]{0,63}', value) is None:
        raise ValueError('invalid bounded runtime version')


def _bounded_json(value):
    # Shape/size checks precede hashing, DataFrame construction and trial replay.
    # Strict JSON primitives exclude arbitrary objects, numpy scalars and bools
    # masquerading as numbers. Depth/node limits also reject cyclic containers.
    # Count the exact canonical UTF-8 byte length incrementally. Serialize only
    # bounded scalar fields, never an over-budget aggregate object. Dict key
    # sorting changes order but not encoded length; punctuation is counted here.
    def scalar_bytes(item):
        return len(json.dumps(item, ensure_ascii=False, allow_nan=False).encode('utf-8'))

    stack, nodes, size = [(value, 0)], 0, 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if depth > 12 or nodes > 250000:
            raise ValueError('native research JSON shape exceeds its bounded budget')
        if type(item) is dict:
            if len(item) > 1000 or any(type(k) is not str or len(k) > 200 for k in item):
                raise ValueError('invalid bounded JSON object')
            size += 2 + max(0, len(item) - 1) + len(item) + sum(scalar_bytes(k) for k in item)
            stack.extend((v, depth + 1) for v in item.values())
        elif type(item) is list:
            if len(item) > MAX_ROWS:
                raise ValueError('native research list exceeds 10000 items')
            size += 2 + max(0, len(item) - 1)
            stack.extend((v, depth + 1) for v in item)
        elif type(item) is str:
            if len(item) > 1024:
                raise ValueError('native research text exceeds bounded field size')
            size += scalar_bytes(item)
        elif type(item) in (float, int):
            if not -1e308 <= item <= 1e308 or not math.isfinite(item):
                raise ValueError('native research requires finite JSON')
            size += scalar_bytes(item)
        elif item is not None and type(item) is not bool:
            raise ValueError('native research requires plain JSON primitives')
        else:
            size += scalar_bytes(item)
        if size > MAX_BYTES:
            raise ValueError('native research exceeds 8 MiB')


def parse_native_json(raw):
    """Bounded strict JSON loading for standalone exports and restored records."""
    if type(raw) is not str or len(raw) > MAX_BYTES or len(raw.encode('utf-8')) > MAX_BYTES:
        raise ValueError('native research exceeds 8 MiB or is not JSON text')

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate native research JSON key')
            result[key] = value
        return result

    def integer(value):
        if len(value) > 310:
            raise ValueError('native research integer exceeds numeric bounds')
        return int(value)

    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_int=integer)
    except (ValueError, RecursionError) as exc:
        raise ValueError('invalid bounded native research JSON') from exc
    _bounded_json(value)
    return value


def _same(actual, expected, name):
    if type(expected) in (int, float):
        if not math.isclose(_number(actual, name), expected, rel_tol=1e-10, abs_tol=1e-12):
            raise ValueError(f'{name} differs from arithmetic replay')
    elif actual != expected:
        raise ValueError(f'{name} differs from the declared protocol')


def _table(frame, columns):
    return {'columns': list(columns), 'dates': frame.index.strftime('%Y-%m-%d').tolist(),
            'rows': [[str(v) if c == 'symbol' else float(v) for c, v in zip(columns, row)]
                     for row in frame[columns].itertuples(index=False, name=None)]}


def _read_table(table, *, columns=None, name):
    _object(table, {'columns', 'dates', 'rows'}, name)
    cols, dates, rows = table['columns'], table['dates'], table['rows']
    if (type(cols) is not list or not 1 <= len(cols) <= 11
            or any(type(c) is not str for c in cols) or len(set(cols)) != len(cols)
            or (columns is not None and cols != columns)):
        raise ValueError(f'{name} columns are invalid')
    if (type(dates) is not list or type(rows) is not list or not 1 <= len(rows) <= MAX_ROWS
            or len(dates) != len(rows) or any(type(d) is not str or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', d) for d in dates)):
        raise ValueError(f'{name} dates/rows exceed the declared shape')
    for row in rows:
        if type(row) is not list or len(row) != len(cols):
            raise ValueError(f'{name} row width differs from columns')
        for c, v in zip(cols, row):
            if c == 'symbol':
                if type(v) is not str:
                    raise ValueError('symbol must be an exact string')
            else:
                _number(v, c)
    try:
        index = pd.DatetimeIndex(pd.to_datetime(dates, format='%Y-%m-%d', exact=True), dtype='datetime64[ns]', name='date')
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError('invalid native research dates') from exc
    if not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError('native research dates must be unique and chronological')
    return pd.DataFrame(rows, columns=cols, index=index)


def _snapshot(value):
    keys = {'request', 'request_id', 'columns', 'row_count', 'data_sha256', 'acquired_at',
            'duckdb_version', 'market_data', 'snapshot_id', 'cache_status'}
    _object(value, keys, 'snapshot')
    request = _object(value['request'], {'schema_version', 'source_id', 'symbol', 'start_date',
                      'end_date', 'period', 'adjust'}, 'request')
    # Preserve the exact caller declaration; do not silently sanitize identity.
    # It can itself contain private text. Never automatically collect paths or
    # credentials, and document that export includes this declaration and rows.
    source_id = request['source_id']
    if (type(source_id) is not str or not source_id.strip() or len(source_id) > 500
            or any(ord(c) < 32 or ord(c) == 127 for c in source_id)):
        raise ValueError('source_id must preserve the bounded caller declaration')
    expected = _request(source_id, request['symbol'], request['start_date'], request['end_date'],
                        request['period'], request['adjust'])
    if type(request['schema_version']) is not int or request != expected or request['adjust'] != 'qlib':
        raise ValueError('native research requires an exact native Qlib request')
    if value['request_id'] != _sha(_json(request)) or value['cache_status'] != 'cache_only':
        raise ValueError('native research requires exact-request cache-only replay')
    metadata_only = {k: v for k, v in value.items() if k not in {'snapshot_id', 'cache_status'}}
    if value['snapshot_id'] != _sha(_json(metadata_only)):
        raise ValueError('native snapshot identity mismatch')
    _int(value['row_count'], 1, MAX_ROWS, 'snapshot row count')
    if type(value['data_sha256']) is not str or not re.fullmatch('[0-9a-f]{64}', value['data_sha256']):
        raise ValueError('invalid source data digest')
    if type(value['acquired_at']) is not str or len(value['acquired_at']) > 40:
        raise ValueError('invalid acquisition time')
    try:
        acquired = datetime.fromisoformat(value['acquired_at'])
    except ValueError as exc:
        raise ValueError('invalid acquisition time') from exc
    if acquired.tzinfo != timezone.utc:
        raise ValueError('snapshot acquisition must be UTC')
    version = value['duckdb_version']
    if type(version) is not str:
        raise ValueError('invalid DuckDB version')
    _version(version.removeprefix('v'))
    _native_qlib_metadata(value['market_data'], request)
    return request


def _split(frame, fraction):
    cutoff = int(Decimal(str(fraction)) * len(frame))
    if not 1 <= cutoff <= len(frame) - 20:
        raise ValueError('later evaluation requires at least 20 observations')
    return {**SPLIT_FIXED, 'training_observations': cutoff,
            'evaluation_observations': len(frame) - cutoff,
            'training_start': str(frame.index[0]), 'training_end': str(frame.index[cutoff - 1]),
            'evaluation_start': str(frame.index[cutoff]), 'evaluation_end': str(frame.index[-1])}


def validate_native_research(payload):
    """Fully validate source identity, prefix trials and later-only arithmetic.

    Cost is bounded by 10,000 input rows, 100 candidates and 2–5 folds. This is
    explicitly NOT run for every archive-list item. No optional SDK is needed.
    """
    _bounded_json(payload)
    _object(payload, {'schema', 'input_role', 'snapshot', 'input', 'training_fraction', 'split',
                     'optimization', 'curve', 'summary', 'conventions', 'limitations', 'producer'}, 'native research')
    if (payload['schema'] != SCHEMA or payload['input_role'] not in ('synthetic', 'user_supplied_unverified')
            or payload['conventions'] != CONVENTIONS or payload['limitations'] != LIMITATIONS):
        raise ValueError('native research schema/scope/metric conventions differ')
    # Equality of bool and int must not let a resealed 0/1 alter fixed declarations.
    if canonical(payload['conventions']) != canonical(CONVENTIONS) or canonical(payload['limitations']) != canonical(LIMITATIONS):
        raise ValueError('native research declarations must preserve exact JSON types')
    request = _snapshot(payload['snapshot'])
    frame = _normalize(_read_table(payload['input'], columns=payload['snapshot']['columns'], name='input'), request)
    if len(frame) != payload['snapshot']['row_count'] or _frame_digest(frame) != payload['snapshot']['data_sha256']:
        raise ValueError('embedded original columns differ from snapshot data identity')
    fraction = _number(payload['training_fraction'], 'training fraction')
    if not 0 < fraction < 1:
        raise ValueError('training fraction must be strictly between zero and one')
    split = _split(frame, fraction)
    if canonical(payload['split']) != canonical(split):
        raise ValueError('training/evaluation split differs from exact suffix')
    prefix = frame['close'].iloc[:split['training_observations']]
    opt = _object(payload['optimization'], {'params', 'score', 'fold_scores', 'trials', 'seed',
        'optimizer_version', 'training_fingerprint', 'splits', 'fee_bps', 'score_metric', 'implementation'}, 'optimization')
    splits = _int(opt['splits'], 2, 5, 'fold count')
    fee = _number(opt['fee_bps'], 'fee_bps')
    if not 0 <= fee < 10000:
        raise ValueError('fee_bps must be between zero and 10000')
    if opt['score_metric'] != CONVENTIONS['sharpe'] or opt['training_fingerprint'] != _training_fingerprint(prefix):
        raise ValueError('optimization score convention or training identity differs')
    if opt['implementation'] == 'injected_study_unknown':
        if opt['seed'] is not None or opt['optimizer_version'] is not None:
            raise ValueError('injected studies cannot claim Optuna version or sampler seed')
    elif opt['implementation'] == 'optuna_tpe':
        _int(opt['seed'], 0, 2**32 - 1, 'sampler seed')
        _version(opt['optimizer_version'])
    else:
        raise ValueError('unknown optimizer identity')
    trials = opt['trials']
    if type(trials) is not list or not 1 <= len(trials) <= MAX_TRIALS:
        raise ValueError('native research requires 1–100 recorded completed trials')
    # TimeSeriesSplit defaults: first training prefix includes the remainder.
    slow_max = min(120, len(prefix) - splits * (len(prefix) // (splits + 1)))
    if slow_max < 10:
        raise ValueError('insufficient first-fold warmup')

    def params(value):
        _object(value, {'fast', 'slow'}, 'candidate parameters')
        fast = _int(value['fast'], 3, min(30, slow_max - 2), 'fast')
        slow = _int(value['slow'], max(fast + 2, 10), slow_max, 'slow')
        return fast, slow

    selected = params(opt['params'])
    seen, scores, selected_seen, replayed = set(), [], False, {}
    # All shape checks run before any candidate scoring.
    for trial in trials:
        _object(trial, {'number', 'params', 'score', 'fold_scores'}, 'trial')
        number = _int(trial['number'], 0, 2**31 - 1, 'trial number')
        if number in seen:
            raise ValueError('trial numbers must be unique')
        seen.add(number)
        params(trial['params'])
        _number(trial['score'], 'trial score')
        if type(trial['fold_scores']) is not list or len(trial['fold_scores']) != splits:
            raise ValueError('trial fold evidence differs from declared fold count')
        for score in trial['fold_scores']:
            _number(score, 'fold score')
    if type(opt['fold_scores']) is not list or len(opt['fold_scores']) != splits:
        raise ValueError('selected fold evidence differs from declared fold count')
    _number(opt['score'], 'selected score')
    for score in opt['fold_scores']:
        _number(score, 'selected fold score')
    curve = _read_table(payload['curve'], columns=CURVE_COLUMNS, name='evaluation curve')
    if not curve.index.equals(frame.index[split['training_observations']:]):
        raise ValueError('evaluation curve is not the exact later suffix')
    expected = run_backtest(frame['close'], moving_average_signal(frame['close'], *selected), fee_bps=fee)
    expected = expected.iloc[split['training_observations']:].copy()
    expected['equity'] = (1 + expected['strategy_return']).cumprod()
    if not np.allclose(curve.to_numpy(dtype='float64'), expected.to_numpy(dtype='float64'), rtol=1e-10, atol=1e-12):
        raise ValueError('evaluation curve differs from continuous-position replay')
    summary = performance_summary(expected)
    _object(payload['summary'], summary, 'summary')
    for key, expected_value in summary.items():
        _same(payload['summary'][key], expected_value, key)
    producer = _object(payload['producer'], {'manifest', 'python', 'runtime_versions'}, 'producer')
    validate_manifest(producer['manifest'])
    if not {'native_research.py', 'research_pipeline.py', 'pipeline.py', 'optuna_walkforward.py',
            'providers/duckdb_cache.py'}.issubset(producer['manifest']['files']):
        raise ValueError('producer identity omits native research modules')
    _version(producer['python'])
    _object(producer['runtime_versions'], VERSIONS, 'producer runtime versions')
    for name, version in producer['runtime_versions'].items():
        _version(version, nullable=name in ('duckdb', 'optuna', 'pyqlib', 'mlflow'))
    if opt['implementation'] == 'optuna_tpe' and opt['optimizer_version'] != producer['runtime_versions']['optuna']:
        raise ValueError('claimed optimizer version differs from producer runtime')
    for trial in trials:
        pair = params(trial['params'])
        if pair not in replayed:
            replayed[pair] = _walkforward_score(prefix, fast=pair[0], slow=pair[1], fee_bps=fee, splits=splits)
        score, folds = replayed[pair]
        _same(trial['score'], score, 'trial score')
        for claimed, actual in zip(trial['fold_scores'], folds):
            _same(claimed, actual, 'trial fold score')
        scores.append(score)
        if pair == selected and math.isclose(opt['score'], score, rel_tol=1e-10, abs_tol=1e-12):
            for claimed, actual in zip(opt['fold_scores'], folds):
                _same(claimed, actual, 'selected fold score')
            selected_seen = True
    if not selected_seen:
        raise ValueError('selected candidate was not evaluated on this training prefix')
    _same(opt['score'], max(scores), 'selected maximum score')
    return payload


def validate_native_record(record):
    """Validate the Workspace envelope and fully replay its native payload."""
    _bounded_json(record)
    _object(record, {'id', 'kind', 'recorded_at', 'payload'}, 'native record')
    if record['kind'] != KIND or record['id'] != digest({'kind': KIND, 'payload': record['payload']}):
        raise ValueError('native research record identity differs')
    instant(record['recorded_at'])
    validate_native_research(record['payload'])
    return record


def restore_native_json(raw: str, workspace_path):
    """Restore one bounded native JSON export into an explicit SQLite path.

    Parse and fully replay the record before creating/opening the destination.
    Preserve its ID, numeric types, producer and recorded_at verbatim as declared
    evidence, never as authenticated provenance. Whitespace/key order in the
    input JSON are not identity. An identical repeat is idempotent; any existing
    envelope conflict, including a different timestamp for the same content ID,
    fails rather than overwriting the immutable original. No optional SDK runs.
    """
    record = validate_native_record(parse_native_json(raw))
    payload = canonical(record['payload'])

    def existing_record(db):
        # A foreign/restored database can bypass the normal write guards. Fetch
        # only scalar header facts before bringing any existing text into Python.
        # BLOB length counts UTF-8 bytes including content after embedded NULs.
        header = db.execute('''SELECT kind=? COLLATE BINARY AS is_native, typeof(payload) AS payload_type,
            length(CAST(payload AS BLOB)) AS payload_bytes,
            typeof(recorded_at) AS timestamp_type,
            length(CAST(recorded_at AS BLOB)) AS timestamp_bytes
            FROM growth_documents WHERE id=? COLLATE BINARY''', (KIND, record['id'])).fetchone()
        if header is not None:
            if (header['is_native'] != 1 or header['payload_type'] != 'text'
                    or not 0 < header['payload_bytes'] <= MAX_BYTES
                    or header['timestamp_type'] != 'text'
                    or not 0 < header['timestamp_bytes'] <= 40 * 4):
                raise ValueError('existing native research record conflicts with the imported envelope')
            existing = db.execute('''SELECT id,kind,payload,recorded_at FROM growth_documents
                WHERE id=? COLLATE BINARY''', (record['id'],)).fetchone()
            return workspace._decode(existing)
        return None

    workspace = Workspace(workspace_path)
    with workspace.connection() as db:
        # Serialize the check and insert across independent processes/connections.
        # Do not use INSERT OR IGNORE: it could hide a conflicting envelope.
        db.execute('BEGIN IMMEDIATE')
        existing = existing_record(db)
        if existing is not None:
            if canonical(existing) != canonical(record):
                raise ValueError('existing native research record conflicts with the imported envelope')
        else:
            inserted = db.execute('INSERT INTO growth_documents(id,kind,payload,recorded_at) VALUES(?,?,?,?)',
                                  (record['id'], KIND, payload, record['recorded_at']))
            if inserted.rowcount != 1:
                raise ValueError('native research restore did not insert exactly one record')
            # A foreign database can contain unexpected triggers. Do not report
            # success if one removes/substitutes the inserted envelope. Reuse the
            # bounded lookup and verify before commit so any side writes roll back.
            saved = existing_record(db)
            if saved is None or canonical(saved) != canonical(record):
                raise ValueError('native research restore did not preserve the imported envelope')
        db.commit()
    return record


def _producer():
    versions = {}
    for name in VERSIONS:
        try:
            versions[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            versions[name] = None
    return {'manifest': runtime_manifest(), 'python': platform.python_version(), 'runtime_versions': versions}


def run_and_save_native_research(workspace: Workspace, provider: DuckDBReplayProvider, symbol: str, *,
        start_date: str, end_date: str, input_role: str,
        optimization_trials: int = 12, optimization_splits: int = 3,
        training_fraction: float = .7, optimization_seed: int = 0, fee_bps: float = 5.,
        optimization_study=None, feature_engineer=None):
    """Execute an exact cache-only Qlib request and save a validated native record.

    ``input_role`` must explicitly be synthetic or user_supplied_unverified.
    The function never refreshes/downloads data. Use an already populated cache.
    There is intentionally no API that stamps today's producer on an old bundle.
    Feature columns are omitted; changes to original source columns are rejected.
    """
    if not isinstance(workspace, Workspace):
        raise TypeError('workspace must be a Workspace')
    if type(provider) is not DuckDBReplayProvider or provider._mode != 'cache_only':
        raise ValueError('native record execution requires a cache-only DuckDBReplayProvider')
    if input_role not in ('synthetic', 'user_supplied_unverified'):
        raise ValueError('input_role must explicitly declare synthetic or user_supplied_unverified')
    _int(optimization_trials, 1, MAX_TRIALS, 'trial budget')
    _int(optimization_splits, 2, 5, 'fold count')
    _int(optimization_seed, 0, 2**32 - 1, 'requested seed')
    if not 0 < _number(training_fraction, 'training fraction') < 1:
        raise ValueError('training fraction must be strictly between zero and one')
    if not 0 <= _number(fee_bps, 'fee_bps') < 10000:
        raise ValueError('fee_bps must be between zero and 10000')
    producer = _producer()
    history = provider.history(symbol, start_date=start_date, end_date=end_date, adjust='qlib')
    if not isinstance(history, pd.DataFrame) or not 1 <= len(history) <= MAX_ROWS:
        raise ValueError('native execution requires 1–10000 source rows')
    snapshot = history.attrs.get('duckdb_replay')
    _bounded_json(snapshot)
    snapshot = json.loads(_json(snapshot))
    request = _snapshot(snapshot)
    if request != _request(provider._source_id, symbol, start_date, end_date, 'daily', 'qlib'):
        raise ValueError('provider snapshot differs from execution request')
    if history.attrs.get('market_data') != snapshot['market_data']:
        raise ValueError('source metadata differs from snapshot')
    original = _normalize(history, request)
    if (len(original) != snapshot['row_count'] or original.columns.tolist() != snapshot['columns']
            or _frame_digest(original) != snapshot['data_sha256']):
        raise ValueError('original source columns differ from snapshot')

    class CapturedHistory:
        def history(self, **kwargs):
            return history.copy(deep=True)

    # One cache read. Freeze the source before optional features/search and keep
    # their original metadata binding independently of mutable frame attrs.
    bundle = run_a_share_research_bundle(CapturedHistory(), symbol, start_date=start_date, end_date=end_date,
        adjust='qlib', feature_engineer=feature_engineer, fee_bps=fee_bps,
        optimization_trials=optimization_trials, optimization_splits=optimization_splits,
        training_fraction=training_fraction, optimization_seed=optimization_seed, optimization_study=optimization_study)
    if not bundle.market.columns.is_unique or not set(snapshot['columns']).issubset(bundle.market.columns):
        raise ValueError('feature processing removed or duplicated original columns')
    transformed = _normalize(bundle.market[snapshot['columns']], request)
    if _frame_digest(transformed) != snapshot['data_sha256']:
        raise ValueError('feature processing changed original source columns')
    optimization = asdict(bundle.optimization)
    if len(optimization['trials']) != optimization_trials:
        raise ValueError('recorded completed trial count differs from requested budget')
    optimization['implementation'] = ('injected_study_unknown' if optimization_study is not None else 'optuna_tpe')
    # Convert tuples and numpy-free dataclass numbers to plain immutable JSON.
    payload = json.loads(canonical({'schema': SCHEMA, 'input_role': input_role, 'snapshot': snapshot,
        'input': _table(original, snapshot['columns']), 'training_fraction': training_fraction,
        'split': bundle.research_split, 'optimization': optimization,
        'curve': _table(bundle.backtest, CURVE_COLUMNS), 'summary': bundle.summary,
        'conventions': CONVENTIONS, 'limitations': LIMITATIONS, 'producer': producer}))
    # Source must not change while the computation runs. Installed SDK version
    # declarations are captured at execution and never refreshed during restore.
    if producer != _producer():
        raise ValueError('producer source/runtime changed during native research execution')
    return workspace.put(KIND, payload)
