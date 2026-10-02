"""Actual Agg PNG, saved-study HTTP, provenance and bounded failure tests."""
import copy
import importlib.util
from importlib import metadata
import io
import json
import struct
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from invest.data import demo_dataset
from invest.experiments import run_study
from invest.study_charts import (ChartBusyError, ChartDependencyError, MAX_POINTS,
    _RENDER_LOCK, drawdowns, prepare_chart, render_study_png)
from invest.workspace import Workspace, canonical, digest
from test_mlflow_local import http_server, study_request

sdk = pytest.mark.skipif(importlib.util.find_spec('matplotlib') is None,
                         reason='optional actual Matplotlib is not installed')


@pytest.fixture(scope='module')
def study(tmp_path_factory):
    root = tmp_path_factory.mktemp('chart-study')
    return Workspace(root / 'state.sqlite').put('study', run_study(demo_dataset(), {
        'symbol': '600000.SH', 'cost_model_acknowledged': True}))


def reseal(record):
    record['payload']['protocol_id'] = digest(record['payload']['protocol'])
    record['id'] = digest({'kind': 'study', 'payload': record['payload']})
    return record


def changed(study, mutate):
    record = copy.deepcopy(study)
    mutate(record)
    return reseal(record)


def test_prepare_curve_and_initial_capital_drawdown(study):
    data = prepare_chart(study, 0)
    assert data['identity']['study_id'] == study['id']
    assert data['identity']['curve_sha256'] == digest(study['payload']['results'][0]['result']['curve'])
    assert drawdowns([90, 80, 120, 60], 100) == pytest.approx([-.1, -.2, 0, -.5])
    assert min(data['benchmark_drawdown']) < 0
    assert data['benchmark_drawdown'][0] < 0  # first-day entry costs are not discarded


@pytest.mark.parametrize('index', [-1, 27, 1.1, True, '0', None])
def test_rejects_invalid_case_before_dependency_load(study, index):
    with patch('invest.study_charts.metadata.version', side_effect=AssertionError('SDK queried')):
        with pytest.raises(ValueError):
            render_study_png(study, index)


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(kind='facts'),
    lambda r: r['payload'].update(schema='unknown'),
    lambda r: r['payload']['protocol'].update(mode='EXPLORATORY_WALK_FORWARD'),
    lambda r: r['payload']['protocol'].update(frozen_holdout_opened=True),
    lambda r: r['payload']['protocol'].update(dataset_id='bad'),
    lambda r: r['payload']['results'][0].update(status='FAILED'),
    lambda r: r['payload']['results'][0]['result'].update(dataset_id='a'*64),
    lambda r: r['payload']['results'][0]['result'].update(source_kind='real'),
    lambda r: r['payload']['results'][0]['result']['parameters'].update(initial_cash=1),
    lambda r: r['payload']['results'][0]['result'].update(evaluation_end='2025-01-01'),
    lambda r: r['payload']['results'][0]['result']['metrics'].update(total_return=123),
    lambda r: r['payload']['results'][0]['result'].update(curve=[]),
    lambda r: r['payload']['results'][0]['result']['curve'][0].update(cash=1e10),
    lambda r: r['payload']['results'][0]['result']['curve'][0].update(equity=-1),
    lambda r: r['payload']['results'][0]['result']['curve'][0].update(equity='100'),
    lambda r: r['payload']['results'][0]['result']['curve'][0].update(equity=True),
    lambda r: r['payload']['results'][0]['result']['curve'][0].update(date='2024-99-01'),
    lambda r: r['payload']['results'][0]['result']['curve'][0].update(date='20240213'),
    lambda r: r['payload']['results'][0]['result']['curve'][1].update(date=r['payload']['results'][0]['result']['curve'][0]['date']),
    lambda r: r['payload']['results'][0]['result'].update(curve=[r['payload']['results'][0]['result']['curve'][0]]*(MAX_POINTS+1)),
])
def test_resealed_but_invalid_record_rejected(study, mutate):
    record = changed(study, mutate)
    with patch('invest.study_charts.metadata.version', side_effect=AssertionError('SDK queried')):
        with pytest.raises(ValueError):
            render_study_png(record, 0)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf')])
def test_nonfinite_values_fail_closed(study, value):
    record = copy.deepcopy(study)
    record['payload']['results'][0]['result']['curve'][0]['equity'] = value
    with pytest.raises(ValueError):
        render_study_png(record, 0)


def test_tampered_identity_and_protocol_are_rejected(study):
    for target, key in [('record', 'id'), ('payload', 'protocol_id')]:
        record = copy.deepcopy(study)
        (record if target == 'record' else record['payload'])[key] = 'f'*64
        if target == 'payload':
            record['id'] = digest({'kind':'study','payload':record['payload']})
        with pytest.raises(ValueError):
            prepare_chart(record, 0)


def test_oversized_saved_record_rejected(study):
    record = changed(study, lambda r: r['payload'].update(limitations=['x'*(8*1024*1024)]))
    with pytest.raises(ValueError, match='8 MiB'):
        prepare_chart(record, 0)


def test_known_rolling_schema_is_supported(study):
    # Schema contract fixture; a genuine PR49 rolling result is checked in combined QA.
    record = copy.deepcopy(study)
    record['payload']['schema'] = record['payload']['protocol']['schema'] = 'invest-walk-forward-study-v1'
    record['payload']['protocol']['mode'] = 'EXPLORATORY_WALK_FORWARD'
    assert prepare_chart(reseal(record), 0)['identity']['mode'] == 'EXPLORATORY_WALK_FORWARD'


def test_engine_supported_decimal_string_cash_is_preserved(tmp_path):
    payload = run_study(demo_dataset(), {'symbol': '600000.SH',
        'initial_cash': '100000.00', 'cost_model_acknowledged': True})
    record = Workspace(tmp_path/'state.sqlite').put('study', payload)
    assert prepare_chart(record, 0)['initial'] == 100000.0
    assert record['payload']['protocol']['initial_cash'] == '100000.00'


@pytest.mark.parametrize('trailing_zeros', [0, 20000])
def test_fee_display_uses_normalized_numbers_without_string_expansion(study, trailing_zeros):
    record = copy.deepcopy(study)
    result = record['payload']['results'][0]['result']
    result['parameters']['commission_rate'] = '0.0001' + '0' * trailing_zeros
    result['parameters']['stamp_tax_rate'] = '0.0005'
    result['parameters']['transfer_fee_rate'] = '0.00001'
    result['fingerprint'] = digest({'dataset_id': result['dataset_id'],
        'parameters': result['parameters'], 'engine': result['engine_version']})
    reseal(record)
    data = prepare_chart(record, 0)
    assert data['identity']['demonstration_costs']['commission_rate'] == .0001
    assert all(type(v) is float for v in data['identity']['demonstration_costs'].values())
    assert len(canonical(data['identity'])) < 3000
    # Fingerprint still binds the original saved declaration, not its display normalization.
    assert data['identity']['engine_fingerprint'] == result['fingerprint']
    if importlib.util.find_spec('matplotlib') is not None:
        assert render_study_png(record, 0).startswith(b'\x89PNG')


def test_missing_or_wrong_version_is_explicit_and_preserves_input(study):
    before = canonical(study)
    for response in [metadata.PackageNotFoundError('matplotlib'), '3.9.0']:
        with patch('invest.study_charts.metadata.version', side_effect=response if isinstance(response, Exception) else None,
                   return_value=response):
            with pytest.raises(ChartDependencyError, match='charts'):
                render_study_png(study, 0)
    assert canonical(study) == before


@sdk
def test_actual_png_metadata_pixels_repeat_and_no_network(study, monkeypatch):
    from PIL import Image
    before = canonical(study)
    monkeypatch.setattr('socket.socket.connect', lambda *a, **k: pytest.fail('network forbidden'))
    png = render_study_png(study, 0)
    assert png.startswith(b'\x89PNG\r\n\x1a\n')
    assert struct.unpack('>II', png[16:24]) == (1200, 840)
    with Image.open(io.BytesIO(png)) as image:
        identity = json.loads(image.info['Description'])
        assert identity['study_id'] == study['id']
        assert identity['case_index'] == 0
        assert identity['source_kind'] == 'demo'
        assert 'SYNTHETIC DEMO' in image.info['Disclaimer']
        assert identity['frozen_holdout_opened'] is False
        assert len(image.convert('RGB').getcolors(1200*840)) > 100
    assert render_study_png(study, 0) == png
    assert canonical(study) == before


@sdk
def test_inherited_tex_disabled_backend_unchanged_and_no_subprocess(study, monkeypatch):
    import matplotlib
    # Initialize the font cache before banning subprocess; fontconfig discovery is local.
    render_study_png(study, 0)
    backend = matplotlib.get_backend()
    with matplotlib.rc_context({'text.usetex': True, 'text.parse_math': True}):
        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('TeX/subprocess forbidden'))
        png = render_study_png(study, 0)
        assert png.startswith(b'\x89PNG')
        assert matplotlib.rcParams['text.usetex'] is True
        assert matplotlib.get_backend() == backend


@sdk
def test_busy_guard_and_renderer_error_release_lock(study):
    _RENDER_LOCK.acquire()
    try:
        with pytest.raises(ChartBusyError):
            render_study_png(study, 0)
    finally:
        _RENDER_LOCK.release()
    with patch('matplotlib.backends.backend_agg.FigureCanvasAgg.print_png', side_effect=ValueError('renderer failure')):
        with pytest.raises(ValueError, match='renderer failure'):
            render_study_png(study, 0)
    assert not _RENDER_LOCK.locked()
    assert render_study_png(study, 0).startswith(b'\x89PNG')


@sdk
def test_real_http_saved_study_chart_and_errors(tmp_path):
    with http_server(tmp_path) as (server, request):
        code, record = request('/api/workbench/study', study_request(request))
        assert code == 200
        route = '/api/workbench/study-chart?id=' + record['id'] + '&case=0'
        code, png = request(route)
        assert code == 200 and png.startswith(b'\x89PNG')
        assert request('/api/workbench/document?id=' + record['id'])[1] == record
        assert len(server.workspace.list('study')) == 1
        for suffix in ['-1', '27', '0&case=1', '01', '1.5', '%2B0', '%EF%BC%90']:
            assert request(route[:-1]+suffix)[0] == 400
        for headers in [{'Host':'bad.invalid'}, {'Origin':'https://bad.invalid'}, {'Sec-Fetch-Site':'cross-site'}]:
            assert request(route, headers=headers)[0] == 403
        with patch('invest.study_charts.metadata.version', side_effect=metadata.PackageNotFoundError('matplotlib')):
            code, error = request(route)
            assert code == 503 and error['study_saved'] is True
        _RENDER_LOCK.acquire()
        try:
            assert request(route)[0] == 409
        finally:
            _RENDER_LOCK.release()
        assert request(route)[0] == 200


@sdk
def test_backup_restore_preserves_chart_identity(tmp_path):
    from invest.backup import restore_backup
    with http_server(tmp_path / 'original') as (_, request):
        _, record = request('/api/workbench/study', study_request(request))
        route = '/api/workbench/study-chart?id=' + record['id'] + '&case=0'
        _, png = request(route)
        _, backup = request('/api/private-backup', {'confirm_private_export': True})
    restored = restore_backup(backup, tmp_path / 'restored')
    with http_server(restored) as (_, request):
        code, restored_png = request(route)
        assert code == 200 and restored_png == png
        assert request('/api/workbench/document?id='+record['id'])[1] == record


def test_registry_and_license_pin_do_not_expand_safe_allowlist():
    from invest.upstreams import list_upstreams, load_registry
    root = Path(__file__).resolve().parents[1]
    project = next(p for p in load_registry()['projects'] if p['repo'] == 'matplotlib/matplotlib')
    assert project['target'] == 'invest.study_charts.render_study_png'
    assert project['license'] == 'LicenseRef-Matplotlib'
    assert project['stars'] >= 10000
    assert project['repo'] not in {p['repo'] for p in list_upstreams(adapter_safe_only=True)}
    import hashlib
    raw = (root/'third_party/matplotlib/LICENSE').read_bytes()
    assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest() == 'ec51537db27dd4d9c9ed3cd39fd96485f3cfddea'
