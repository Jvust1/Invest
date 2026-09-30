"""Deterministic native research evidence tests; no optional SDK or provider I/O.

The handmade snapshot is synthetic and uses the real cache request, frame and
snapshot digest conventions. These tests establish recorded arithmetic and
portability, not market-data authenticity or A-share cash-execution validity.
"""
from copy import deepcopy
from contextlib import contextmanager
import builtins
import io
import json
import math
from pathlib import Path
from types import SimpleNamespace
import zipfile

import numpy as np
import pandas as pd
import pytest

from invest import native_research as native
from invest.backup import export_backup, restore_backup
from invest.mlflow_tracking import _checked_record
from invest.optuna_walkforward import _training_fingerprint
from invest.provenance import source_manifest
from invest.providers.duckdb_cache import (
    DuckDBMarketCache, DuckDBReplayProvider, _frame_digest, _json, _normalize,
    _request, _sha,
)
from invest.study_charts import prepare_chart
from invest.workspace import Workspace, canonical, digest
from test_mlflow_local import http_server


SYMBOL = '600000.SH'
START, END = '20240101', '20241231'
SOURCE = 'qlib.native/v1;synthetic'
CANDIDATES = ((3, 10), (5, 14), (7, 20), (9, 21))
OPTIONAL_SDKS = {'duckdb', 'optuna', 'qlib', 'pyqlib', 'mlflow'}


class NoIOConnection:
    """Only constructor capability checks are expected in these unit tests."""

    def register(self, *args):
        pytest.fail('native evidence execution unexpectedly wrote to DuckDB')

    def execute(self, *args):
        pytest.fail('native evidence execution unexpectedly queried DuckDB')


class DeterministicStudy:
    def __init__(self, *, completed_offset=0, choose_worst=False):
        self.direction = SimpleNamespace(name='MAXIMIZE')
        self.trials = []
        self.requested_trials = None
        self.completed_offset = completed_offset
        self.choose_worst = choose_worst

    def optimize(self, objective, *, n_trials):
        self.requested_trials = n_trials
        for number in range(n_trials + self.completed_offset):
            fast, slow = CANDIDATES[number % len(CANDIDATES)]
            candidate = {'fast': fast, 'slow': slow}

            def suggest_int(name, low, high, candidate=candidate):
                assert low <= candidate[name] <= high
                return candidate[name]

            trial = SimpleNamespace(number=number, params=candidate, suggest_int=suggest_int)
            trial.value = objective(trial)
            self.trials.append(trial)
        select = min if self.choose_worst else max
        self.best_trial = select(self.trials, key=lambda trial: trial.value)


def synthetic_frame(*, later_multiplier=1.0):
    index = pd.bdate_range('2024-01-02', periods=120, name='date')
    t = np.arange(120, dtype=float)
    close = 100 + .18 * t + 3 * np.sin(t / 3) + 1.5 * np.cos(t / 7)
    # Long enough to hold a position across the split for every candidate.
    close[65:85] = np.linspace(close[64] + .5, close[64] + 10.5, 20)
    close[84:] *= later_multiplier
    frame = pd.DataFrame({
        'open': close * .999, 'high': close * 1.01, 'low': close * .99,
        'close': close, 'volume': 1000 + t, 'symbol': SYMBOL,
    }, index=index)
    request = _request(SOURCE, SYMBOL, START, END, 'daily', 'qlib')
    frame = _normalize(frame, request)
    market_data = {
        'provider': 'qlib', 'source_kind': 'local_qlib_dataset_unverified',
        'frequency': 'day', 'adjustment': 'qlib',
        'price_basis': 'qlib_native_unconverted', 'volume_basis': 'qlib_native_unconverted',
        'price_unit': 'dataset_defined_unverified', 'volume_unit': 'dataset_defined_unverified',
        'tracking': 'disabled', 'network': 'disabled', 'dataset_sha256': 'a' * 64,
        'runtime_version': '0.9.7', 'mlflow_runtime_version': '3.16.1',
        'instrument': 'SH600000', 'start_date': '2024-01-01', 'end_date': '2024-12-31',
    }
    metadata = {
        'request': request, 'request_id': _sha(_json(request)),
        'columns': frame.columns.tolist(), 'row_count': len(frame),
        'data_sha256': _frame_digest(frame), 'acquired_at': '2024-07-01T00:00:00+00:00',
        'duckdb_version': 'v1.4.0', 'market_data': market_data,
    }
    frame.attrs = {'market_data': deepcopy(market_data),
                   'duckdb_replay': {**metadata, 'snapshot_id': _sha(_json(metadata)),
                                     'cache_status': 'cache_only'}}
    return frame


def replay_provider(frame, *, mode='cache_only'):
    calls = []
    upstream = SimpleNamespace(history=lambda **kwargs: pytest.fail('upstream called'))
    provider = DuckDBReplayProvider(DuckDBMarketCache(connection=NoIOConnection()),
                                    source_id=SOURCE, upstream=upstream, mode=mode)

    def history(symbol, **kwargs):
        calls.append(dict(symbol=symbol, **kwargs))
        return deepcopy(frame)

    provider.history = history
    return provider, calls


def execute(workspace, frame=None, **overrides):
    provider, calls = replay_provider(synthetic_frame() if frame is None else frame)
    study = overrides.pop('optimization_study', DeterministicStudy())
    kwargs = dict(start_date=START, end_date=END, input_role='synthetic',
                  optimization_trials=4, optimization_study=study)
    kwargs.update(overrides)
    record = native.run_and_save_native_research(workspace, provider, SYMBOL, **kwargs)
    assert calls == [{'symbol': SYMBOL, 'start_date': START, 'end_date': END, 'adjust': 'qlib'}]
    return record, study


@pytest.fixture(scope='module')
def record(tmp_path_factory):
    root = tmp_path_factory.mktemp('native-record-seed')
    # Keep this arithmetic fixture independent of concurrent source edits and
    # optional installed package versions; source identity is tested separately.
    producer = {'manifest': source_manifest(), 'python': '3.11.9',
                'runtime_versions': {'numpy': '2.3.5', 'pandas': '2.2.3',
                    'scikit-learn': '1.8.0', 'duckdb': None, 'optuna': None,
                    'pyqlib': None, 'mlflow': None}}
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(native, '_producer', lambda: deepcopy(producer))
        return execute(Workspace(root / 'state.sqlite'))[0]


@pytest.fixture
def forbid_optional_sdk(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split('.')[0] not in OPTIONAL_SDKS, 'unexpected optional SDK import: ' + name
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)


def reseal(record):
    record['id'] = digest({'kind': record['kind'], 'payload': record['payload']})
    return record


def reseal_snapshot(snapshot):
    snapshot['request_id'] = _sha(_json(snapshot['request']))
    snapshot['snapshot_id'] = _sha(_json({k: v for k, v in snapshot.items()
                                        if k not in {'snapshot_id', 'cache_status'}}))


def set_path(value, path, replacement):
    for part in path[:-1]:
        value = value[part]
    value[path[-1]] = deepcopy(replacement)


def test_save_reopen_deduplicate_preserves_embedded_record(record, tmp_path, forbid_optional_sdk):
    workspace = Workspace(tmp_path / 'state.sqlite')
    first = workspace.put(native.KIND, deepcopy(record['payload']))
    second = Workspace(workspace.path).put(native.KIND, deepcopy(record['payload']))
    assert first == second
    assert Workspace(workspace.path).get(first['id'], native.KIND) == first
    assert Workspace(workspace.path).list(native.KIND) == [first]
    assert native.validate_native_record(json.loads(canonical(first))) == first
    assert first['payload']['snapshot']['market_data']['instrument'] == 'SH600000'
    assert first['payload']['input']['columns'] == synthetic_frame().columns.tolist()
    assert first['payload']['limitations']['frozen_holdout_opened'] is False
    assert first['payload']['limitations']['native_price_and_volume_units_verified'] is False
    assert first['payload']['optimization']['implementation'] == 'injected_study_unknown'
    assert first['payload']['optimization']['seed'] is None
    assert first['payload']['optimization']['optimizer_version'] is None


def test_execute_is_cache_only_explicit_native_and_counts_trials(tmp_path, forbid_optional_sdk):
    saved, study = execute(Workspace(tmp_path / 'state.sqlite'), optimization_trials=7,
                           optimization_seed=423)
    optimization = saved['payload']['optimization']
    assert study.requested_trials == 7
    assert len(study.trials) == len(optimization['trials']) == 7
    assert [t['number'] for t in optimization['trials']] == list(range(7))
    assert optimization['score'] == max(t['score'] for t in optimization['trials'])
    assert optimization['seed'] is optimization['optimizer_version'] is None
    assert saved['payload']['producer']['manifest'] == source_manifest()
    assert native.validate_native_record(saved) == saved


def test_backup_restore_needs_no_source_files_runtime_probe_or_optional_sdk(
        record, tmp_path, monkeypatch, forbid_optional_sdk):
    root = tmp_path / 'original'
    workspace = Workspace(root / 'state.sqlite')
    saved = workspace.put(native.KIND, record['payload'])
    backup = export_backup(root)
    with zipfile.ZipFile(io.BytesIO(backup)) as archive:
        assert set(archive.namelist()) == {'state.sqlite', 'manifest.json'}
    monkeypatch.setattr(native, '_producer', lambda: pytest.fail('restore stamped current producer'))
    monkeypatch.setattr(native, 'runtime_manifest', lambda: pytest.fail('restore read source files'))
    monkeypatch.setattr(native.metadata, 'version', lambda name: pytest.fail('restore probed SDK version'))
    monkeypatch.setattr(DuckDBReplayProvider, 'history', lambda *a, **k: pytest.fail('restore read provider'))
    restored = restore_backup(backup, tmp_path / 'restored')
    loaded = Workspace(restored / 'state.sqlite').get(saved['id'])
    assert loaded == saved
    assert native.validate_native_record(loaded) == saved
    assert not (restored / 'native.duckdb').exists()
    assert not (restored / 'mlflow').exists()


def test_later_curve_and_all_summary_metrics_match_independent_arithmetic(record):
    payload = record['payload']
    close = np.array([r[3] for r in payload['input']['rows']])
    fast, slow = (payload['optimization']['params'][k] for k in ('fast', 'slow'))
    signal = np.zeros(len(close))
    for i in range(slow - 1, len(close)):
        signal[i] = float(np.mean(close[i-fast+1:i+1]) > np.mean(close[i-slow+1:i+1]))
    returns = np.r_[0., close[1:] / close[:-1] - 1]
    turnover = np.abs(np.diff(signal, prepend=0))
    strategy = np.r_[0., signal[:-1]] * returns - turnover * 5 / 10000
    cutoff = 84
    evaluation = strategy[cutoff:]
    equity = np.cumprod(1 + evaluation)
    expected = np.column_stack((close[cutoff:], signal[cutoff:], returns[cutoff:],
                                turnover[cutoff:], evaluation, equity))
    assert payload['split']['training_observations'] == 84
    assert payload['split']['evaluation_observations'] == 36
    assert payload['curve']['dates'] == payload['input']['dates'][84:]
    assert signal[83] == signal[84] == 1
    assert expected[0, 3] == 0  # No artificial new entry fee at the split.
    assert expected[0, 4] != 0  # The prior position earns the boundary return.
    np.testing.assert_allclose(payload['curve']['rows'], expected, rtol=1e-12, atol=1e-12)
    assert equity[0] == 1 + evaluation[0]
    volatility = float(np.std(evaluation, ddof=1) * math.sqrt(252))
    expected_summary = {
        'total_return': float(equity[-1] - 1),
        'annualized_return': float(equity[-1] ** (252 / len(evaluation)) - 1),
        'annualized_volatility': volatility,
        'sharpe': float(np.mean(evaluation) * 252 / volatility),
        'max_drawdown': float(np.min(equity / np.maximum.accumulate(np.r_[1., equity])[1:] - 1)),
    }
    assert payload['summary'] == pytest.approx(expected_summary, rel=1e-12, abs=1e-12)


def test_future_prices_change_evaluation_but_never_training_evidence(tmp_path):
    workspace = Workspace(tmp_path / 'state.sqlite')
    first, _ = execute(workspace)
    changed, _ = execute(workspace, synthetic_frame(later_multiplier=1.37))
    assert first['payload']['input']['rows'][:84] == changed['payload']['input']['rows'][:84]
    assert first['payload']['optimization'] == changed['payload']['optimization']
    assert first['payload']['curve'] != changed['payload']['curve']
    assert first['payload']['summary'] != changed['payload']['summary']
    assert first['payload']['snapshot']['data_sha256'] != changed['payload']['snapshot']['data_sha256']
    assert first['id'] != changed['id']


def test_training_fingerprint_is_stable_across_ms_us_ns_resolution():
    frame = synthetic_frame()
    fingerprints = []
    for unit in ('ms', 'us', 'ns'):
        close = frame['close'].iloc[:84].copy()
        close.index = pd.DatetimeIndex(close.index.to_numpy(dtype=f'datetime64[{unit}]'), name='date')
        fingerprints.append(_training_fingerprint(close))
    assert len(set(fingerprints)) == 1


def test_json_http_download_validates_and_list_only_checks_identity(
        record, tmp_path, monkeypatch, forbid_optional_sdk):
    saved = Workspace(tmp_path / 'state.sqlite').put(native.KIND, record['payload'])
    original = native._walkforward_score
    seen = []

    def track(*args, **kwargs):
        seen.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(native, '_walkforward_score', track)
    monkeypatch.setattr(Workspace, 'list', lambda *a, **k: pytest.fail('native HTTP list retained full records'))
    with http_server(tmp_path) as (_, request):
        status, listing = request('/api/workbench/documents?kind=native_research')
        assert status == 200
        assert listing['listing_limit'] == 100
        assert listing['validation'] == 'content_identity_only; full_native_replay_on_download'
        assert [item['id'] for item in listing['documents']] == [saved['id']]
        assert 'payload' not in listing['documents'][0]
        assert seen == []
        status, downloaded = request('/api/workbench/document?id=' + saved['id'])
        assert status == 200
        assert downloaded == saved
        assert len(seen) == len(CANDIDATES)
        assert request('/api/workbench/study-chart?id=' + saved['id'] + '&case=0')[0] == 400
        assert request('/api/workbench/track-study', {'study_id': saved['id']})[0] == 400
        assert request('/api/workbench/documents?kind=arbitrary')[0] == 400


def test_http_refuses_resealed_arithmetic_tampering_and_releases_lock(record, tmp_path):
    workspace = Workspace(tmp_path / 'state.sqlite')
    corrupt = deepcopy(record)
    corrupt['payload']['summary']['total_return'] += .5
    reseal(corrupt)
    # Simulate an independently restored/imported DB: content identity alone is
    # valid, while the full document endpoint must reject the arithmetic claim.
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (corrupt['id'], corrupt['kind'], canonical(corrupt['payload']), corrupt['recorded_at']))
    with http_server(tmp_path) as (server, request):
        assert request('/api/workbench/documents?kind=native_research')[0] == 200
        assert request('/api/workbench/document?id=' + corrupt['id'])[0] == 400
        assert server.study_lock.acquire(blocking=False)
        server.study_lock.release()


def test_native_http_download_respects_shared_bounded_work_lock(record, tmp_path):
    saved = Workspace(tmp_path / 'state.sqlite').put(native.KIND, record['payload'])
    with http_server(tmp_path) as (server, request):
        with server.study_lock:
            assert request('/api/workbench/document?id=' + saved['id'])[0] == 409
            assert request('/api/workbench/documents?kind=native_research')[0] == 200
        assert request('/api/workbench/document?id=' + saved['id'])[0] == 200


@pytest.mark.parametrize('validator', [prepare_chart, _checked_record])
def test_cash_chart_and_mlflow_contracts_reject_native_records(record, validator, forbid_optional_sdk):
    with pytest.raises(ValueError):
        validator(record, 0) if validator is prepare_chart else validator(record)
    disguised = deepcopy(record)
    disguised['kind'] = 'study'
    reseal(disguised)
    with pytest.raises(ValueError):
        validator(disguised, 0) if validator is prepare_chart else validator(disguised)


@pytest.mark.parametrize('path,replacement', [
    (('schema',), 'invest-exploratory-study-v1'),
    (('input_role',), 'licensed_real'),
    (('training_fraction',), .6),
    (('split', 'training_observations'), 83),
    (('split', 'evaluation_observations'), 35),
    (('split', 'evaluation_start'), '2024-05-01 00:00:00'),
    (('split', 'frozen_holdout_opened'), 0),
    (('optimization', 'training_fingerprint'), '0' * 64),
    (('optimization', 'params', 'fast'), 1),
    (('optimization', 'params', 'slow'), 120),
    (('optimization', 'score'), 1000.),
    (('optimization', 'fold_scores', 0), 1000.),
    (('optimization', 'trials', 0, 'score'), 1000.),
    (('optimization', 'trials', 0, 'fold_scores', 0), 1000.),
    (('optimization', 'trials', 0, 'number'), 1),
    (('optimization', 'trials', 0, 'params', 'slow'), 22),
    (('optimization', 'fee_bps'), 12.),
    (('optimization', 'splits'), 2),
    (('optimization', 'score_metric'), 'sharpe_net_cash'),
    (('optimization', 'implementation'), 'claimed_verified_optuna'),
    (('optimization', 'seed'), 0),
    (('optimization', 'optimizer_version'), '5.0.0'),
    (('curve', 'rows', 0, 0), 1.),
    (('curve', 'rows', 0, 1), .5),
    (('curve', 'rows', 0, 2), 0.),
    (('curve', 'rows', 0, 3), 1.),
    (('curve', 'rows', 0, 4), 0.),
    (('curve', 'rows', 0, 5), 1.),
    (('curve', 'dates', 0), '2024-01-02'),
    (('summary', 'total_return'), 42.),
    (('summary', 'annualized_return'), 42.),
    (('summary', 'annualized_volatility'), 42.),
    (('summary', 'sharpe'), 42.),
    (('summary', 'max_drawdown'), -.999),
    (('conventions', 'fee'), 'no_fees'),
    (('limitations', 'frozen_holdout_opened'), 0),
    (('limitations', 'native_price_and_volume_units_verified'), True),
    (('producer', 'python'), 'unknown'),
    (('producer', 'runtime_versions', 'numpy'), None),
    (('producer', 'manifest', 'code_identity'), '0' * 64),
])
def test_resealed_claims_cannot_override_recorded_arithmetic_or_scope(record, path, replacement):
    corrupt = deepcopy(record)
    set_path(corrupt['payload'], path, replacement)
    reseal(corrupt)
    with pytest.raises(ValueError):
        native.validate_native_record(corrupt)


@pytest.mark.parametrize('path,replacement', [
    (('request', 'symbol'), '600000.SZ'),
    (('request', 'schema_version'), True),
    (('request', 'start_date'), '20240103'),
    (('request', 'end_date'), '20241230'),
    (('request', 'period'), 'weekly'),
    (('request', 'adjust'), 'qfq'),
    (('request', 'source_id'), 'x' * 501),
    (('request', 'source_id'), 'source\ncontrol'),
    (('request', 'source_id'), '   '),
    (('cache_status',), 'refresh'),
    (('row_count',), 119),
    (('data_sha256',), '0' * 64),
    (('acquired_at',), '2024-07-01T00:00:00'),
    (('acquired_at',), '2024-07-01T08:00:00+08:00'),
    (('duckdb_version',), 'unknown'),
    (('market_data', 'instrument'), 'SZ600000'),
    (('market_data', 'start_date'), '2024-01-02'),
    (('market_data', 'end_date'), '2024-12-30'),
    (('market_data', 'price_unit'), 'CNY'),
    (('market_data', 'volume_unit'), 'shares'),
    (('market_data', 'price_basis'), 'qfq'),
    (('market_data', 'volume_basis'), 'raw'),
    (('market_data', 'dataset_sha256'), 'not-a-digest'),
    (('market_data', 'network'), 'enabled'),
    (('market_data', 'tracking'), 'enabled'),
    (('market_data', 'runtime_version'), 'unknown'),
])
def test_resealed_snapshot_still_requires_exact_native_source_contract(record, path, replacement):
    corrupt = deepcopy(record)
    snapshot = corrupt['payload']['snapshot']
    set_path(snapshot, path, replacement)
    reseal_snapshot(snapshot)
    reseal(corrupt)
    with pytest.raises(ValueError):
        native.validate_native_record(corrupt)


def test_snapshot_and_request_digests_are_both_checked(record):
    for key in ('snapshot_id', 'request_id'):
        corrupt = deepcopy(record)
        corrupt['payload']['snapshot'][key] = '0' * 64
        with pytest.raises(ValueError):
            native.validate_native_record(reseal(corrupt))


def test_original_input_digest_rejects_copied_snapshot_attributes(record):
    corrupt = deepcopy(record)
    corrupt['payload']['input']['rows'][0][3] += .25
    with pytest.raises(ValueError, match='embedded original columns'):
        native.validate_native_record(reseal(corrupt))


def test_selected_trial_must_be_present_and_maximum(tmp_path):
    workspace = Workspace(tmp_path / 'state.sqlite')
    with pytest.raises(ValueError, match='selected maximum score'):
        execute(workspace, optimization_study=DeterministicStudy(choose_worst=True))
    assert workspace.list(native.KIND) == []


def test_record_must_contain_selected_candidate(record):
    corrupt = deepcopy(record)
    opt = corrupt['payload']['optimization']
    opt['trials'] = [trial for trial in opt['trials'] if trial['params'] != opt['params']]
    assert opt['trials']
    with pytest.raises(ValueError, match='selected candidate was not evaluated'):
        native.validate_native_record(reseal(corrupt))


@pytest.mark.parametrize('offset', [-1, 1])
def test_injected_study_cannot_silently_change_requested_trial_budget(tmp_path, offset):
    workspace = Workspace(tmp_path / 'state.sqlite')
    with pytest.raises(ValueError, match='trial count differs'):
        execute(workspace, optimization_study=DeterministicStudy(completed_offset=offset))
    assert workspace.list(native.KIND) == []


@pytest.mark.parametrize('original_column', ['open', 'high', 'low', 'close', 'volume', 'symbol'])
def test_feature_transform_cannot_change_original_source_columns(tmp_path, original_column):
    def transform(frame):
        frame.loc[frame.index[0], original_column] = ('600000.SZ' if original_column == 'symbol'
                                                    else frame.iloc[0][original_column] * 1.001)
        return frame
    workspace = Workspace(tmp_path / 'state.sqlite')
    with pytest.raises(ValueError):
        execute(workspace, feature_engineer=SimpleNamespace(transform=transform))
    assert workspace.list(native.KIND) == []


@pytest.mark.parametrize('action', ['drop', 'duplicate'])
def test_feature_transform_cannot_drop_or_duplicate_original_columns(tmp_path, action):
    def transform(frame):
        if action == 'drop':
            return frame.drop(columns=['volume'])
        return pd.concat([frame, frame[['close']]], axis=1)
    with pytest.raises(ValueError, match='removed or duplicated'):
        execute(Workspace(tmp_path / 'state.sqlite'), feature_engineer=SimpleNamespace(transform=transform))


def test_feature_columns_are_not_persisted_and_do_not_change_source(tmp_path):
    def transform(frame):
        frame['derived_feature'] = np.arange(len(frame))
        return frame
    result, _ = execute(Workspace(tmp_path / 'state.sqlite'),
                        feature_engineer=SimpleNamespace(transform=transform))
    assert 'derived_feature' not in result['payload']['input']['columns']
    assert result['payload']['snapshot']['data_sha256'] == synthetic_frame().attrs['duckdb_replay']['data_sha256']


@pytest.mark.parametrize('mismatch', ['prices', 'source_metadata', 'request'])
def test_wrapper_rejects_wrong_data_carrying_copied_source_attributes(tmp_path, mismatch):
    frame = synthetic_frame()
    if mismatch == 'prices':
        frame.loc[frame.index[0], 'close'] += .25
    elif mismatch == 'source_metadata':
        frame.attrs['market_data']['dataset_sha256'] = 'b' * 64
    else:
        snapshot = frame.attrs['duckdb_replay']
        snapshot['request']['source_id'] = 'different.native/v1'
        reseal_snapshot(snapshot)
    workspace = Workspace(tmp_path / 'state.sqlite')
    with pytest.raises(ValueError):
        execute(workspace, frame)
    assert workspace.list(native.KIND) == []


def test_wrapper_refuses_refresh_or_duck_typed_provider_before_io(tmp_path):
    workspace = Workspace(tmp_path / 'state.sqlite')
    refresh, calls = replay_provider(synthetic_frame(), mode='refresh')
    for provider in (refresh, SimpleNamespace(_mode='cache_only', history=refresh.history)):
        with pytest.raises(ValueError, match='cache-only DuckDBReplayProvider'):
            native.run_and_save_native_research(workspace, provider, SYMBOL,
                start_date=START, end_date=END, input_role='synthetic')
    assert calls == []


@pytest.mark.parametrize('role', [None, '', 'real', 'verified', 1])
def test_wrapper_requires_explicit_permitted_input_role_before_io(tmp_path, role):
    provider, calls = replay_provider(synthetic_frame())
    with pytest.raises(ValueError, match='input_role'):
        native.run_and_save_native_research(Workspace(tmp_path / 'state.sqlite'), provider, SYMBOL,
            start_date=START, end_date=END, input_role=role)
    assert calls == []


def test_user_supplied_unverified_is_an_explicit_supported_role(tmp_path):
    result, _ = execute(Workspace(tmp_path / 'state.sqlite'), input_role='user_supplied_unverified')
    assert result['payload']['input_role'] == 'user_supplied_unverified'
    assert result['payload']['limitations']['market_data_rights_or_authenticity_verified'] is False


@pytest.mark.parametrize('change', ['source', 'runtime'])
def test_producer_is_captured_during_execution_and_cannot_change(tmp_path, monkeypatch, change):
    before = native._producer()
    after = deepcopy(before)
    if change == 'source':
        manifest = after['manifest']
        manifest['files']['native_research.py'] = 'b' * 64
        manifest['code_identity'] = digest({'schema': manifest['schema'], 'files': manifest['files']})
    else:
        after['runtime_versions']['numpy'] = '9.9.9'
    declarations = iter([before, after])
    monkeypatch.setattr(native, '_producer', lambda: deepcopy(next(declarations)))
    workspace = Workspace(tmp_path / 'state.sqlite')
    with pytest.raises(ValueError, match='producer source/runtime changed'):
        execute(workspace)
    assert workspace.list(native.KIND) == []


@pytest.mark.parametrize('module', ['native_research.py', 'research_pipeline.py', 'pipeline.py',
                                  'optuna_walkforward.py', 'providers/duckdb_cache.py'])
def test_resealed_producer_cannot_omit_native_pipeline_modules(record, module):
    corrupt = deepcopy(record)
    manifest = corrupt['payload']['producer']['manifest']
    del manifest['files'][module]
    manifest['code_identity'] = digest({'schema': manifest['schema'], 'files': manifest['files']})
    with pytest.raises(ValueError, match='omits native research modules'):
        native.validate_native_record(reseal(corrupt))


def test_optuna_identity_requires_seed_version_and_producer_agreement(record):
    payload = deepcopy(record['payload'])
    opt = payload['optimization']
    opt.update(implementation='optuna_tpe', seed=0, optimizer_version='5.0.0')
    payload['producer']['runtime_versions']['optuna'] = '5.0.0'
    assert native.validate_native_research(payload) == payload
    for path, replacement in [(('optimization', 'seed'), None),
                              (('optimization', 'seed'), True),
                              (('optimization', 'seed'), -1),
                              (('optimization', 'seed'), 2**32),
                              (('optimization', 'optimizer_version'), None),
                              (('producer', 'runtime_versions', 'optuna'), '5.0.1')]:
        corrupt = deepcopy(payload)
        set_path(corrupt, path, replacement)
        with pytest.raises(ValueError):
            native.validate_native_research(corrupt)


@pytest.mark.parametrize('path,replacement', [
    (('training_fraction',), True), (('training_fraction',), 0),
    (('training_fraction',), 1), (('training_fraction',), .99),
    (('optimization', 'splits'), True), (('optimization', 'splits'), 1),
    (('optimization', 'splits'), 6), (('optimization', 'fee_bps'), True),
    (('optimization', 'fee_bps'), -1), (('optimization', 'fee_bps'), 10000),
    (('optimization', 'params', 'fast'), True),
    (('optimization', 'trials', 0, 'number'), True),
    (('optimization', 'trials', 0, 'number'), -1),
    (('optimization', 'trials', 0, 'number'), 2**31),
    (('optimization', 'trials', 0, 'fold_scores'), [1, 2]),
    (('optimization', 'fold_scores'), [1, 2]),
    (('optimization', 'trials'), []),
    (('snapshot', 'row_count'), True),
    (('snapshot', 'row_count'), 0),
    (('snapshot', 'row_count'), 10001),
    (('input', 'rows', 0), [1]),
    (('input', 'rows', 0, 3), True),
    (('input', 'rows', 0, 3), '100'),
    (('input', 'rows', 0, 5), 600000),
    (('input', 'dates', 0), '2024-02-30'),
    (('input', 'dates', 1), '2024-01-02'),
    (('input', 'columns'), ['close'] * 6),
    (('curve', 'rows', 0), [1]),
    (('curve', 'rows', 0, 3), True),
    (('curve', 'dates', 0), 'invalid'),
    (('curve', 'columns'), ['equity']),
    (('producer', 'python'), '3.' + '0' * 64),
])
def test_invalid_shapes_types_and_bounds_are_rejected_before_trial_replay(
        record, path, replacement, monkeypatch):
    payload = deepcopy(record['payload'])
    set_path(payload, path, replacement)
    monkeypatch.setattr(native, '_walkforward_score', lambda *a, **k: pytest.fail('malformed evidence was scored'))
    with pytest.raises(ValueError):
        native.validate_native_research(payload)


@pytest.mark.parametrize('bad_number', [float('nan'), float('inf'), -float('inf')])
@pytest.mark.parametrize('path', [('training_fraction',), ('input', 'rows', 0, 3),
                                ('curve', 'rows', 0, 5), ('optimization', 'score'),
                                ('summary', 'sharpe')])
def test_nonfinite_numbers_fail_closed_before_canonicalization_or_scoring(
        record, path, bad_number, monkeypatch):
    payload = deepcopy(record['payload'])
    set_path(payload, path, bad_number)
    monkeypatch.setattr(native, '_walkforward_score', lambda *a, **k: pytest.fail('nonfinite evidence was scored'))
    with pytest.raises(ValueError, match='finite'):
        native.validate_native_research(payload)


@pytest.mark.parametrize('kind', ['rows', 'trials', 'depth', 'cycle', 'nodes', 'text', 'bytes', 'object', 'numpy'])
def test_resource_and_plain_json_budgets_fail_before_arithmetic(record, kind, monkeypatch):
    payload = deepcopy(record['payload'])
    if kind == 'rows':
        payload['input']['rows'] = [[1.] * 6] * 10001
    elif kind == 'trials':
        payload['optimization']['trials'] = [deepcopy(payload['optimization']['trials'][0]) for _ in range(101)]
    elif kind in ('depth', 'cycle'):
        nested = []
        payload['extra'] = nested
        if kind == 'cycle':
            nested.append(nested)
        else:
            for _ in range(14):
                child = []
                nested.append(child)
                nested = child
    elif kind == 'nodes':
        payload['extra'] = [[0] * 1000 for _ in range(251)]
    elif kind == 'text':
        payload['extra'] = 'x' * 1025
    elif kind == 'bytes':
        payload['extra'] = ['x' * 1024] * 9000
    elif kind == 'object':
        payload['extra'] = object()
    elif kind == 'numpy':
        payload['summary']['sharpe'] = np.float64(1)
    monkeypatch.setattr(native, '_walkforward_score', lambda *a, **k: pytest.fail('over-budget evidence was scored'))
    with pytest.raises(ValueError):
        native.validate_native_research(payload)


@pytest.mark.parametrize('mutation', ['id', 'kind', 'timestamp', 'extra', 'payload_extra'])
def test_native_record_envelope_rejects_wrong_identity_timestamp_or_shape(record, mutation):
    corrupt = deepcopy(record)
    if mutation == 'id':
        corrupt['id'] = '0' * 64
    elif mutation == 'kind':
        corrupt['kind'] = 'study'
        reseal(corrupt)
    elif mutation == 'timestamp':
        corrupt['recorded_at'] = '2024-01-01T00:00:00'
    elif mutation == 'extra':
        corrupt['extra'] = True
    else:
        corrupt['payload']['extra'] = True
        reseal(corrupt)
    with pytest.raises(ValueError):
        native.validate_native_record(corrupt)


def test_workspace_does_not_save_invalid_native_payload(record, tmp_path):
    workspace = Workspace(tmp_path / 'state.sqlite')
    payload = deepcopy(record['payload'])
    payload['summary']['sharpe'] += 10
    with pytest.raises(ValueError):
        workspace.put(native.KIND, payload)
    assert workspace.list(native.KIND) == []


def test_real_sdk_golden_fixture_replays_without_sdks_or_current_producer(
        tmp_path, monkeypatch, forbid_optional_sdk):
    fixture = Path(__file__).with_name('fixtures') / 'native_research_v1_synthetic.json'
    saved = json.loads(fixture.read_text(encoding='utf-8'))
    assert saved['payload']['input_role'] == 'synthetic'
    assert saved['payload']['optimization']['implementation'] == 'optuna_tpe'
    assert len(saved['payload']['optimization']['trials']) == 12
    assert saved['payload']['snapshot']['row_count'] == 120
    monkeypatch.setattr(native, '_producer', lambda: pytest.fail('fixture restamped producer'))
    monkeypatch.setattr(native, 'runtime_manifest', lambda: pytest.fail('fixture read current source'))
    monkeypatch.setattr(native.metadata, 'version', lambda name: pytest.fail('fixture probed runtime'))
    monkeypatch.setattr(DuckDBReplayProvider, 'history', lambda *a, **k: pytest.fail('fixture fetched source'))
    monkeypatch.setattr(native, 'run_a_share_research_bundle', lambda *a, **k: pytest.fail('fixture reran research'))
    monkeypatch.setattr('invest.optuna_walkforward.optimize_sma_walkforward',
                        lambda *a, **k: pytest.fail('fixture reran optimizer'))
    assert native.validate_native_record(saved) == saved
    reopened = Workspace(tmp_path / 'state.sqlite').put(native.KIND, saved['payload'])
    assert reopened['id'] == saved['id']
    assert reopened['payload'] == saved['payload']
    restored = restore_backup(export_backup(tmp_path), tmp_path / 'restored')
    assert native.validate_native_record(Workspace(restored / 'state.sqlite').get(saved['id'])) == reopened


@pytest.mark.parametrize('name,value', [
    ('optimization_trials', 0), ('optimization_trials', 101), ('optimization_trials', True),
    ('optimization_trials', 4.0), ('optimization_splits', 1), ('optimization_splits', 6),
    ('optimization_splits', True), ('optimization_seed', -1), ('optimization_seed', 2**32),
    ('optimization_seed', True), ('training_fraction', 0), ('training_fraction', 1),
    ('training_fraction', True), ('training_fraction', float('nan')),
    ('fee_bps', -1), ('fee_bps', 10000), ('fee_bps', True), ('fee_bps', float('inf')),
])
def test_execution_rejects_unbounded_protocol_before_provider_or_optimizer_io(tmp_path, name, value):
    provider, calls = replay_provider(synthetic_frame())
    study = DeterministicStudy()
    kwargs = dict(start_date=START, end_date=END, input_role='synthetic',
                  optimization_study=study)
    kwargs[name] = value
    with pytest.raises(ValueError):
        native.run_and_save_native_research(Workspace(tmp_path / 'state.sqlite'), provider, SYMBOL, **kwargs)
    assert calls == []
    assert study.requested_trials is None


def test_execution_rejects_oversized_input_before_optimizer(tmp_path):
    frame = synthetic_frame()
    repeated = pd.concat([frame] * 84)
    assert len(repeated) > 10000
    study = DeterministicStudy()
    with pytest.raises(ValueError, match='1–10000 source rows'):
        execute(Workspace(tmp_path / 'state.sqlite'), repeated, optimization_study=study)
    assert study.requested_trials is None


def test_unbounded_python_integers_are_value_errors_before_hashing(record, monkeypatch):
    payload = deepcopy(record['payload'])
    payload['summary']['sharpe'] = 10**10000
    monkeypatch.setattr(native, 'canonical', lambda *a, **k: pytest.fail('unbounded integer was serialized'))
    with pytest.raises(ValueError, match='finite'):
        native.validate_native_research(payload)


def test_duplicate_candidates_are_all_preserved_but_replayed_once(tmp_path, monkeypatch):
    saved, _ = execute(Workspace(tmp_path / 'state.sqlite'), optimization_trials=7)
    original = native._walkforward_score
    calls = []

    def track(*args, **kwargs):
        calls.append((kwargs['fast'], kwargs['slow']))
        return original(*args, **kwargs)

    monkeypatch.setattr(native, '_walkforward_score', track)
    native.validate_native_record(saved)
    assert len(saved['payload']['optimization']['trials']) == 7
    assert calls == list(CANDIDATES)


def test_wrapper_preserves_source_declaration_verbatim(tmp_path):
    frame = synthetic_frame()
    declaration = 'caller declared Qlib product; units unverified/v1'
    snapshot = frame.attrs['duckdb_replay']
    snapshot['request']['source_id'] = declaration
    reseal_snapshot(snapshot)
    provider, calls = replay_provider(frame)
    provider._source_id = declaration
    saved = native.run_and_save_native_research(Workspace(tmp_path / 'state.sqlite'), provider, SYMBOL,
        start_date=START, end_date=END, input_role='synthetic', optimization_trials=4,
        optimization_study=DeterministicStudy())
    assert len(calls) == 1
    assert saved['payload']['snapshot']['request']['source_id'] == declaration
    assert saved['payload']['snapshot']['request_id'] == _sha(_json(snapshot['request']))


def test_feature_metadata_cannot_relabel_original_source_snapshot(tmp_path):
    def transform(frame):
        frame.attrs['duckdb_replay']['market_data']['price_unit'] = 'CNY'
        frame.attrs['duckdb_replay']['market_data']['dataset_sha256'] = 'b' * 64
        frame.attrs['market_data']['price_unit'] = 'CNY'
        return frame
    saved, _ = execute(Workspace(tmp_path / 'state.sqlite'),
                       feature_engineer=SimpleNamespace(transform=transform))
    source = saved['payload']['snapshot']['market_data']
    assert source['price_unit'] == 'dataset_defined_unverified'
    assert source['dataset_sha256'] == 'a' * 64


@pytest.mark.parametrize('replacement', [True, 0, -1, 10001, 120.0, '120'])
def test_resealed_row_count_retains_exact_bounded_integer_type(record, replacement):
    corrupt = deepcopy(record)
    corrupt['payload']['snapshot']['row_count'] = replacement
    reseal_snapshot(corrupt['payload']['snapshot'])
    with pytest.raises(ValueError, match='snapshot row count'):
        native.validate_native_record(reseal(corrupt))


@pytest.mark.parametrize('raw', ['x' * (8 * 1024 * 1024 + 1), '中' * (3 * 1024 * 1024)],
                         ids=['character-limit', 'utf8-byte-limit'])
def test_restored_oversized_native_row_is_rejected_before_json_parser(raw, tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / 'state.sqlite')
    key = 'a' * 64
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (key, native.KIND, raw, '2024-01-01T00:00:00+00:00'))
    monkeypatch.setattr('invest.workspace.json.loads',
                        lambda *a, **k: pytest.fail('oversized restored native record reached JSON parser'))
    with pytest.raises(ValueError, match='8 MiB'):
        workspace.get(key)
    with pytest.raises(ValueError, match='8 MiB'):
        workspace.list_summaries(native.KIND)


def test_native_summary_listing_streams_cursor_without_fetchall_or_arithmetic(record, tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / 'state.sqlite')
    saved = workspace.put(native.KIND, record['payload'])
    original_connection = workspace.connection
    yielded = []

    class StreamOnlyCursor:
        def __init__(self, cursor):
            self.cursor = cursor

        def __iter__(self):
            for row in self.cursor:
                yielded.append(row['id'])
                yield row

        def fetchall(self):
            pytest.fail('native listing materialized all raw records')

    @contextmanager
    def stream_only_connection():
        with original_connection() as db:
            yield SimpleNamespace(execute=lambda *a, **k: StreamOnlyCursor(db.execute(*a, **k)))

    monkeypatch.setattr(workspace, 'connection', stream_only_connection)
    monkeypatch.setattr(workspace, 'list', lambda *a, **k: pytest.fail('native listing used full-record list'))
    monkeypatch.setattr(native, '_walkforward_score', lambda *a, **k: pytest.fail('native listing replayed trials'))
    monkeypatch.setattr(native, 'validate_native_research', lambda *a, **k: pytest.fail('native listing did full validation'))
    assert workspace.list_summaries(native.KIND) == [{
        'id': saved['id'], 'kind': native.KIND, 'recorded_at': saved['recorded_at'],
        'name': saved['id'][:12], 'summary': saved['payload']['summary'],
    }]
    assert yielded == [saved['id']]


@pytest.mark.parametrize('summary', [None, [], {'extra': 1}, {'sharpe': [0] * 10000},
                                    'unbounded summary text'], ids=['null', 'list', 'keys', 'nested', 'text'])
def test_resealed_foreign_summary_cannot_expand_archive_listing(record, tmp_path, summary):
    workspace = Workspace(tmp_path / 'state.sqlite')
    corrupt = deepcopy(record)
    corrupt['payload']['summary'] = summary
    reseal(corrupt)
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (corrupt['id'], native.KIND, canonical(corrupt['payload']), corrupt['recorded_at']))
    with pytest.raises(ValueError, match='listing summary shape'):
        workspace.list_summaries(native.KIND)


@pytest.mark.parametrize('number', [True, '1.0', 10**400], ids=['boolean', 'string', 'huge-integer'])
def test_listing_metrics_require_bounded_finite_json_numbers(record, tmp_path, number):
    workspace = Workspace(tmp_path / 'state.sqlite')
    corrupt = deepcopy(record)
    corrupt['payload']['summary']['sharpe'] = number
    reseal(corrupt)
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (corrupt['id'], native.KIND, canonical(corrupt['payload']), corrupt['recorded_at']))
    with pytest.raises(ValueError):
        workspace.list_summaries(native.KIND)


def test_foreign_native_name_is_not_retained_in_identity_only_listing(record, tmp_path):
    workspace = Workspace(tmp_path / 'state.sqlite')
    corrupt = deepcopy(record)
    corrupt['payload']['name'] = 'arbitrary private text' * 20
    reseal(corrupt)
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (corrupt['id'], native.KIND, canonical(corrupt['payload']), corrupt['recorded_at']))
    summary = workspace.list_summaries(native.KIND)[0]
    assert summary['name'] == corrupt['id'][:12]
    assert len(canonical(summary)) < 1000


def test_training_fingerprint_timezone_and_resolution_equivalence():
    close = synthetic_frame()['close'].iloc[:84]
    expected = _training_fingerprint(close)
    for unit in ('ms', 'us', 'ns'):
        for tz in ('UTC', 'Asia/Shanghai', 'America/New_York'):
            equivalent = close.copy()
            equivalent.index = pd.DatetimeIndex(close.index.to_numpy(dtype=f'datetime64[{unit}]'),
                name='date').tz_localize('UTC').tz_convert(tz)
            assert _training_fingerprint(equivalent) == expected


@pytest.mark.parametrize('tz', [None, 'UTC', 'Asia/Shanghai'])
def test_training_fingerprint_rejects_out_of_nanosecond_range_without_wrapping(tz):
    try:
        index = pd.DatetimeIndex(np.array(['2500-01-01', '2500-01-02'], dtype='datetime64[us]'))
        if tz is not None:
            index = index.tz_localize(tz)
    except (pd.errors.OutOfBoundsDatetime, OverflowError):
        pytest.skip('installed pandas cannot represent out-of-nanosecond-range DatetimeIndex')
    close = pd.Series([1., 2.], index=index)
    with pytest.raises(ValueError, match='nanosecond range'):
        _training_fingerprint(close)


def test_feature_cannot_reseal_its_attrs_to_hide_changed_original_values(tmp_path):
    def transform(frame):
        frame.loc[frame.index[0], 'close'] += .25
        snapshot = frame.attrs['duckdb_replay']
        snapshot['data_sha256'] = _frame_digest(_normalize(frame, snapshot['request']))
        reseal_snapshot(snapshot)
        return frame
    workspace = Workspace(tmp_path / 'state.sqlite')
    with pytest.raises(ValueError, match='feature processing changed original source columns'):
        execute(workspace, feature_engineer=SimpleNamespace(transform=transform))
    assert workspace.list(native.KIND) == []


@pytest.mark.parametrize('payload', [None, [], ['nested'], 1, True, 'text'],
                         ids=['null', 'empty-list', 'list', 'integer', 'boolean', 'text'])
def test_restored_hash_consistent_nonobject_payloads_fail_closed_in_http_and_workspace(
        payload, tmp_path, monkeypatch):
    workspace = Workspace(tmp_path / 'state.sqlite')
    key = digest({'kind': native.KIND, 'payload': payload})
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (key, native.KIND, canonical(payload), '2024-01-01T00:00:00+00:00'))
    monkeypatch.setattr(native, '_walkforward_score', lambda *a, **k: pytest.fail('nonobject payload replayed'))
    for operation in (lambda: workspace.get(key), lambda: workspace.list_summaries(native.KIND)):
        with pytest.raises(ValueError, match='JSON object'):
            operation()
    with http_server(tmp_path) as (_, request):
        assert request('/api/workbench/documents?kind=native_research')[0] == 400
        assert request('/api/workbench/document?id=' + key)[0] == 400


@pytest.mark.parametrize('mutation', ['blob', 'timestamp-huge', 'timestamp-invalid', 'timestamp-naive'])
def test_restored_native_blob_or_bad_timestamp_fails_before_arithmetic_http400(
        record, tmp_path, monkeypatch, mutation):
    workspace = Workspace(tmp_path / 'state.sqlite')
    raw, timestamp = canonical(record['payload']), record['recorded_at']
    if mutation == 'blob':
        raw = raw.encode('utf-8')
    elif mutation == 'timestamp-huge':
        timestamp = '2024-01-01T00:00:00' + '0' * 10000 + '+00:00'
    elif mutation == 'timestamp-invalid':
        timestamp = 'not a timestamp'
    else:
        timestamp = '2024-01-01T00:00:00'
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (record['id'], native.KIND, raw, timestamp))
    monkeypatch.setattr(native, '_walkforward_score', lambda *a, **k: pytest.fail('bad restored envelope replayed'))
    for operation in (lambda: workspace.get(record['id']), lambda: workspace.list_summaries(native.KIND)):
        with pytest.raises(ValueError):
            operation()
    with http_server(tmp_path) as (_, request):
        assert request('/api/workbench/documents?kind=native_research')[0] == 400
        assert request('/api/workbench/document?id=' + record['id'])[0] == 400


@pytest.mark.parametrize('raw', [
    '{"duplicate":1,"duplicate":2}', '{"n":NaN}', '{"n":Infinity}', '{"n":-Infinity}',
    '{"n":1e999}', '{"n":' + '9' * 400 + '}', '[' * 2000 + '0' + ']' * 2000,
    '{"nested":' + '[' * 14 + '0' + ']' * 14 + '}', b'{"not":"text"}',
], ids=['duplicate-key', 'nan', 'positive-infinity', 'negative-infinity', 'float-overflow',
        'huge-integer', 'parser-depth', 'bounded-depth', 'bytes'])
def test_strict_native_json_loader_rejects_ambiguous_unbounded_or_nonfinite_input(raw):
    with pytest.raises(ValueError):
        native.parse_native_json(raw)


def test_strict_native_json_loader_preserves_golden_record_without_restamping():
    fixture = Path(__file__).with_name('fixtures') / 'native_research_v1_synthetic.json'
    raw = fixture.read_text(encoding='utf-8')
    assert native.parse_native_json(raw) == json.loads(raw)
