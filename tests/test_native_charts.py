"""Actual Agg native PNGs, full-record validation and saved-only HTTP/downloads."""
import builtins
from copy import deepcopy
import importlib.util
from importlib import metadata
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
from unittest.mock import patch

import pytest

from invest import native_research as native
from invest.native_charts import (MAX_PLOT_MAGNITUDE, SCHEMA, prepare_native_chart,
                                  render_native_png)
from invest.study_charts import (ChartBusyError, ChartDependencyError, _RENDER_LOCK,
                                prepare_chart, render_study_png)
from invest.workspace import Workspace, canonical, digest
from test_mlflow_local import http_server

FIXTURE = Path(__file__).with_name('fixtures') / 'native_research_v1_synthetic.json'
SDK_NAMES = {'duckdb', 'optuna', 'qlib', 'pyqlib', 'mlflow'}
sdk = pytest.mark.skipif(importlib.util.find_spec('matplotlib') is None,
                         reason='optional actual Matplotlib is not installed')


@pytest.fixture
def record():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def reseal(record):
    record['id'] = digest({'kind': record['kind'], 'payload': record['payload']})
    return record


@pytest.fixture
def no_research(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split('.')[0] not in SDK_NAMES, 'unexpected SDK import: ' + name
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    forbidden = lambda *a, **k: pytest.fail('PNG invoked provider, search or research execution')
    monkeypatch.setattr(native.DuckDBReplayProvider, 'history', forbidden)
    monkeypatch.setattr(native, 'run_a_share_research_bundle', forbidden)
    monkeypatch.setattr(native, 'run_and_save_native_research', forbidden)
    monkeypatch.setattr(native, '_producer', forbidden)
    monkeypatch.setattr(native, 'runtime_manifest', forbidden)
    monkeypatch.setattr('invest.optuna_walkforward.optimize_sma_walkforward', forbidden)
    monkeypatch.setattr('invest.engine.backtest', forbidden)
    monkeypatch.setattr('invest.engine.execute_order', forbidden)


def test_complete_native_record_later_only_and_original_declarations(record, no_research):
    before = canonical(record)
    data = prepare_native_chart(record)
    payload, identity = record['payload'], data['identity']
    assert [d.isoformat() for d in data['dates']] == payload['curve']['dates']
    assert [d.isoformat() for d in data['dates']] == payload['input']['dates'][payload['split']['training_observations']:]
    assert data['equity'] == [r[-1] for r in payload['curve']['rows']]
    assert len(data['equity']) == payload['split']['evaluation_observations']
    peak = 1.0
    expected = []
    for value in data['equity']:
        peak = max(peak, value)
        expected.append(value / peak - 1)
    assert data['drawdown'] == expected
    assert all(v <= 0 for v in expected)
    assert identity['schema'] == SCHEMA
    assert identity['record_id'] == record['id']
    assert identity['record_sha256'] == digest(record)
    assert identity['curve_sha256'] == digest(payload['curve'])
    assert identity['initial_unit_capital'] == 1.0
    assert identity['source_declaration'] == payload['snapshot']
    assert identity['producer_declaration'] == payload['producer']
    assert identity['optimization_declaration'] == payload['optimization']
    assert identity['split_declaration'] == payload['split']
    assert identity['recorded_at_declaration'] == record['recorded_at']
    assert identity['conventions'] == payload['conventions']
    assert identity['limitations'] == payload['limitations']
    assert identity['render_id'] == digest({k: v for k, v in identity.items() if k != 'render_id'})
    assert canonical(record) == before
    # Prepared identities cannot become aliases that overwrite authoritative JSON.
    identity['producer_declaration']['python'] = 'changed'
    assert canonical(record) == before


@pytest.mark.parametrize('mutate', [
    lambda r: r.update(kind='study'),
    lambda r: r.update(kind='facts'),
    lambda r: r.update(extra='foreign envelope'),
    lambda r: r.update(recorded_at='yesterday'),
    lambda r: r['payload'].update(schema='invest-exploratory-study-v1'),
    lambda r: r['payload'].update(input_role='verified_market'),
    lambda r: r['payload']['curve']['rows'][0].__setitem__(-1, 987),
    lambda r: r['payload']['input']['rows'][0].__setitem__(0, 987),
    lambda r: r['payload']['summary'].update(sharpe=987),
    lambda r: r['payload']['optimization']['trials'][0].update(score=987),
    lambda r: r['payload']['optimization']['trials'][0]['params'].update(fast=987),
    lambda r: r['payload']['snapshot']['request'].update(source_id='other declaration'),
    lambda r: r['payload']['producer']['manifest'].update(code_identity='0' * 64),
    lambda r: r['payload']['split'].update(evaluation_start='2025-01-01'),
    lambda r: r['payload']['limitations'].update(native_price_and_volume_units_verified=True),
])
def test_resealed_malformed_source_or_arithmetic_rejected_before_sdk(record, mutate):
    mutate(record)
    reseal(record)
    with patch('invest.native_charts.metadata.version', side_effect=AssertionError('SDK queried')):
        with pytest.raises(ValueError):
            render_native_png(record)
    assert not _RENDER_LOCK.locked()


@pytest.mark.parametrize('value', [None, [], {}, {'kind': 'native_research'}])
def test_foreign_values_rejected_before_sdk(value):
    with patch('invest.native_charts.metadata.version', side_effect=AssertionError('SDK queried')):
        with pytest.raises(ValueError):
            render_native_png(value)


@pytest.mark.parametrize('field,value', [('id', '0' * 64), ('recorded_at', False)])
def test_unsealed_envelope_rejected(record, field, value):
    record[field] = value
    with pytest.raises(ValueError):
        prepare_native_chart(record)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), float('-inf'), True, '1.0'])
def test_bad_numeric_values_fail_closed(record, value):
    record['payload']['curve']['rows'][0][-1] = value
    with pytest.raises(ValueError):
        render_native_png(record)


@pytest.mark.parametrize('case', ['field', 'list', 'depth', 'total'])
def test_large_payload_rejected_before_sdk(record, case):
    if case == 'field':
        record['payload']['snapshot']['request']['source_id'] = 'x' * (native.MAX_BYTES + 1)
    elif case == 'list':
        record['payload']['curve']['rows'] = [[1] * 6] * (native.MAX_ROWS + 1)
    elif case == 'depth':
        value = 0
        for _ in range(14):
            value = [value]
        record['payload']['summary'] = value
    else:
        record['payload']['curve']['rows'] = [['x' * 1024] * 6] * 2000
    with patch('invest.native_charts.metadata.version', side_effect=AssertionError('SDK queried')):
        with pytest.raises(ValueError):
            render_native_png(record)


def rebuild_later(record, multiplier):
    """Authored synthetic changed suffix, independently resealed for bound tests."""
    payload = record['payload']
    frame = native._read_table(payload['input'], columns=payload['snapshot']['columns'], name='input')
    cutoff = payload['split']['training_observations']
    frame.loc[frame.index[cutoff:], ['open', 'high', 'low', 'close']] *= multiplier
    snapshot = payload['snapshot']
    snapshot['data_sha256'] = native._frame_digest(frame)
    snapshot['snapshot_id'] = native._sha(native._json({k: v for k, v in snapshot.items()
                                                       if k not in {'snapshot_id', 'cache_status'}}))
    payload['input'] = native._table(frame, snapshot['columns'])
    params = payload['optimization']['params']
    curve = native.run_backtest(frame['close'], native.moving_average_signal(frame['close'], **params),
                               fee_bps=payload['optimization']['fee_bps']).iloc[cutoff:].copy()
    curve['equity'] = (1 + curve['strategy_return']).cumprod()
    payload['curve'] = native._table(curve, native.CURVE_COLUMNS)
    payload['summary'] = native.performance_summary(curve)
    return reseal(record)


def test_initial_loss_drawdown_includes_unit_baseline(record):
    rebuilt = rebuild_later(record, .5)
    assert native.validate_native_record(rebuilt) == rebuilt
    data = prepare_native_chart(rebuilt)
    assert data['equity'][0] < 1
    assert data['drawdown'][0] == data['equity'][0] - 1
    assert min(data['drawdown']) == pytest.approx(rebuilt['payload']['summary']['max_drawdown'])


def test_valid_extreme_values_rejected_without_clipping_or_sdk(record):
    rebuilt = rebuild_later(record, MAX_PLOT_MAGNITUDE * 10)
    assert native.validate_native_record(rebuilt) == rebuilt
    assert rebuilt['payload']['curve']['rows'][0][-1] > MAX_PLOT_MAGNITUDE
    before = canonical(rebuilt)
    with patch('invest.native_charts.metadata.version', side_effect=AssertionError('SDK queried')):
        with pytest.raises(ValueError, match='plotting magnitude'):
            render_native_png(rebuilt)
    assert canonical(rebuilt) == before


def test_signed_values_are_never_clipped_after_native_validation(record):
    # The native v1 arithmetic rejects returns below -1, so materially negative
    # equity is not a valid v1 record. Isolate the display contract rather than
    # weakening that arithmetic to manufacture a negative-capital fixture.
    record['payload']['curve']['rows'][0][-1] = -.5
    with patch('invest.native_charts.validate_native_record') as validation:
        data = prepare_native_chart(record)
    validation.assert_called_once_with(record)
    assert data['equity'][0] == -.5
    assert data['drawdown'][0] == -1.5
    with pytest.raises(ValueError):
        native.validate_native_record(reseal(record))


def test_cash_chart_validators_still_reject_native_and_native_rejects_cash(record):
    with pytest.raises(ValueError):
        prepare_chart(record, 0)
    with pytest.raises(ValueError):
        render_study_png(record, 0)
    with pytest.raises(ValueError):
        prepare_native_chart({'kind': 'study', 'payload': {'schema': 'invest-exploratory-study-v1'}})


def test_missing_wrong_renderer_releases_lock_and_preserves_json(record):
    before = canonical(record)
    for response in [metadata.PackageNotFoundError('matplotlib'), '3.9.0']:
        with patch('invest.native_charts.metadata.version', side_effect=response if isinstance(response, Exception) else None,
                   return_value=response):
            with pytest.raises(ChartDependencyError, match='charts'):
                render_native_png(record)
        assert not _RENDER_LOCK.locked()
    assert canonical(record) == before


def test_busy_shared_cash_renderer_lock_skips_validation(record):
    with patch('invest.native_charts.prepare_native_chart', side_effect=AssertionError('validated while busy')):
        _RENDER_LOCK.acquire()
        try:
            with pytest.raises(ChartBusyError):
                render_native_png(record)
        finally:
            _RENDER_LOCK.release()


@sdk
@pytest.mark.parametrize('role', ['synthetic', 'user_supplied_unverified'])
def test_actual_png_exact_metadata_pixels_and_repeated_bytes(record, no_research, monkeypatch, role):
    from PIL import Image
    record['payload']['input_role'] = role
    reseal(record)
    before = canonical(record)
    monkeypatch.setattr('socket.socket.connect', lambda *a, **k: pytest.fail('network forbidden'))
    png = render_native_png(record)
    assert png.startswith(b'\x89PNG\r\n\x1a\n')
    assert struct.unpack('>II', png[16:24]) == (1200, 900)
    with Image.open(io.BytesIO(png)) as image:
        expected = prepare_native_chart(record)['identity']
        assert json.loads(image.info['Description']) == expected
        assert image.info['Description'] == canonical(expected)
        assert image.info['Software'] == 'Invest / Matplotlib 3.10.8'
        assert ('SYNTHETIC' if role == 'synthetic' else 'USER-SUPPLIED') in image.info['Disclaimer']
        assert 'native price/volume units unverified' in image.info['Disclaimer']
        assert len(image.convert('RGB').getcolors(1200 * 900)) > 100
    assert render_native_png(record) == png
    assert canonical(record) == before


@sdk
def test_free_text_stays_inert_metadata_tex_disabled_and_backend_unchanged(record, monkeypatch):
    import matplotlib
    from matplotlib.text import Text
    from PIL import Image
    hostile = r'$\\input{private-file}$ <script>literal source declaration</script>'
    snapshot = record['payload']['snapshot']
    snapshot['request']['source_id'] = hostile
    snapshot['request_id'] = native._sha(native._json(snapshot['request']))
    snapshot['snapshot_id'] = native._sha(native._json({k: v for k, v in snapshot.items()
                                                       if k not in {'snapshot_id', 'cache_status'}}))
    reseal(record)
    render_native_png(record)  # initialize the local font cache before banning subprocess
    backend = matplotlib.get_backend()
    seen = []
    original = Text.draw

    def draw(self, *args, **kwargs):
        seen.append(self.get_text())
        assert self.get_usetex() is False
        assert self.get_parse_math() is False
        return original(self, *args, **kwargs)

    with matplotlib.rc_context({'text.usetex': True, 'text.parse_math': True}):
        monkeypatch.setattr(Text, 'draw', draw)
        monkeypatch.setattr(subprocess, 'Popen', lambda *a, **k: pytest.fail('TeX/subprocess forbidden'))
        png = render_native_png(record)
        assert matplotlib.rcParams['text.usetex'] is True
        assert matplotlib.get_backend() == backend
    assert all(hostile not in text for text in seen)
    assert 'EXPLORATORY / NOT A-SHARE CASH EXECUTION' in seen
    assert 'Unit capital (initial = 1)' in seen
    assert 'Drawdown (fraction)' in seen
    assert 'Declared symbol 000001.SH | Selected MA 4/13 | Native signal fee 5 bps' in seen
    with Image.open(io.BytesIO(png)) as image:
        assert json.loads(image.info['Description'])['source_declaration']['request']['source_id'] == hostile


@sdk
def test_renderer_failure_or_import_error_releases_shared_lock(record, monkeypatch):
    with patch('matplotlib.backends.backend_agg.FigureCanvasAgg.print_png', side_effect=ValueError('renderer failed')):
        with pytest.raises(ValueError, match='renderer failed'):
            render_native_png(record)
    assert not _RENDER_LOCK.locked()
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == 'matplotlib.backends.backend_agg':
            raise ImportError('broken Agg')
        return original(name, *args, **kwargs)

    with monkeypatch.context() as guard:
        guard.setattr(builtins, '__import__', guarded)
        with pytest.raises(ChartDependencyError, match='charts'):
            render_native_png(record)
    assert not _RENDER_LOCK.locked()
    assert render_native_png(record).startswith(b'\x89PNG')


@sdk
def test_json_restored_record_renders_identical_without_research(record, tmp_path, no_research):
    png = render_native_png(record)
    path = tmp_path / 'restored' / 'state.sqlite'
    restored = native.restore_native_json(canonical(record), path)
    loaded = Workspace(path).get(record['id'], 'native_research')
    assert canonical(loaded) == canonical(record) == canonical(restored)
    assert render_native_png(loaded) == png
    assert canonical(Workspace(path).get(record['id'])) == canonical(record)
    assert not (path.parent / 'mlflow').exists()
    assert not (path.parent / 'native.duckdb').exists()


@sdk
def test_http_saved_only_route_retries_and_preserves_json(record, tmp_path, no_research):
    native.restore_native_json(canonical(record), tmp_path / 'state.sqlite')
    with http_server(tmp_path) as (server, request):
        route = '/api/workbench/native-chart?id=' + record['id']
        code, png = request(route)
        assert code == 200 and png.startswith(b'\x89PNG')
        assert request(route) == (200, png)
        assert request('/api/workbench/document?id=' + record['id'])[1] == record
        assert server.workspace.list('native_research') == [record]
        assert request('/api/workbench/study-chart?id=' + record['id'] + '&case=0')[0] == 400
        for suffix in ['', 'bad', '0' * 64, record['id'] + '&id=' + record['id']]:
            assert request('/api/workbench/native-chart?id=' + suffix)[0] == 400
        for headers in [{'Host': 'bad.invalid'}, {'Origin': 'https://bad.invalid'}, {'Sec-Fetch-Site': 'cross-site'}]:
            assert request(route, headers=headers)[0] == 403
        assert request(route, {})[0] == 404  # no execution/import POST endpoint
        with patch('invest.native_charts.metadata.version', side_effect=metadata.PackageNotFoundError('matplotlib')):
            code, error = request(route)
            assert code == 503 and error['record_saved'] is True
        assert not server.study_lock.locked() and not _RENDER_LOCK.locked()
        server.study_lock.acquire()
        try:
            code, error = request(route)
            assert code == 409 and 'record_saved' not in error
        finally:
            server.study_lock.release()
        _RENDER_LOCK.acquire()
        try:
            assert request(route)[0] == 409
        finally:
            _RENDER_LOCK.release()
        assert request(route) == (200, png)
        assert server.workspace.get(record['id']) == record


@sdk
def test_http_reply_happens_after_validation_and_render_locks_release(record, tmp_path):
    from invest.workbench_api import dispatch
    from types import SimpleNamespace
    import threading
    workspace = Workspace(tmp_path / 'state.sqlite')
    native.restore_native_json(canonical(record), workspace.path)
    server = SimpleNamespace(workspace=workspace, study_lock=threading.Lock())
    replies = []

    def reply(status, *args, **kwargs):
        assert not server.study_lock.locked()
        assert not _RENDER_LOCK.locked()
        replies.append(status)
        return status

    handler = SimpleNamespace(server=server, _reply=reply)
    parameter = lambda name, required: record['id']
    assert dispatch(handler, '/api/workbench/native-chart', parameter) == 200
    with patch('invest.native_charts.metadata.version', side_effect=metadata.PackageNotFoundError('matplotlib')):
        assert dispatch(handler, '/api/workbench/native-chart', parameter) == 503
    with patch('invest.native_charts.render_native_png', side_effect=ChartBusyError('busy')):
        assert dispatch(handler, '/api/workbench/native-chart', parameter) == 409
    assert replies == [200, 503, 409]


@sdk
def test_real_http_served_javascript_native_download(record, tmp_path, no_research):
    native.restore_native_json(canonical(record), tmp_path / 'state.sqlite')
    with http_server(tmp_path) as (server, request):
        route = '/api/workbench/native-chart?id=' + record['id']
        _, expected = request(route)
        output = tmp_path / 'served-helper.png'
        js = r"""
const fs=require('node:fs'),vm=require('node:vm');
(async()=>{const [base,id,path]=process.argv.slice(1);
const response=await fetch(base+'/workbench.js');if(!response.ok)throw new Error('script missing');
const source=await response.text();let result;
const context={Blob,AbortSignal,encodeURIComponent,csrf:'',
fetch:(route,options)=>fetch(base+route,options),download:(blob,name)=>{result={blob,name};}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='),source.indexOf('function action(')),context);
await context.nativeChartDownload(id,'native-'+id+'.png');
if(!result||result.name!=='native-'+id+'.png')throw new Error('wrong saved identity');
fs.writeFileSync(path,Buffer.from(await result.blob.arrayBuffer()));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        result = subprocess.run(['node', '-e', js, f'http://127.0.0.1:{server.server_port}', record['id'], str(output)],
                                capture_output=True, timeout=30)
        assert result.returncode == 0, result.stderr
        assert output.read_bytes() == expected
        assert request('/api/workbench/document?id=' + record['id'])[1] == record


def test_module_import_and_prepare_without_any_optional_sdks():
    root = Path(__file__).resolve().parents[1]
    script = r'''
import builtins,sys,json
from pathlib import Path
sys.path.insert(0,sys.argv[1])
original=builtins.__import__
def guarded(name,*args,**kwargs):
    assert name.split('.')[0] not in {'matplotlib','duckdb','optuna','qlib','pyqlib','mlflow'},name
    return original(name,*args,**kwargs)
builtins.__import__=guarded
from invest.native_charts import prepare_native_chart
record=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
assert prepare_native_chart(record)['identity']['record_id']==record['id']
print('SDK-free native preparation passed')
'''
    result = subprocess.run([sys.executable, '-I', '-c', script, str(root), str(FIXTURE)],
                            capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert b'SDK-free native preparation passed' in result.stdout
