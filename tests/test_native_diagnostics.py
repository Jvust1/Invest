"""Saved-only diagnostics contracts; actual SDK cases are optional and explicit."""
from copy import deepcopy
import importlib.util
from importlib import metadata
import json
import math
from pathlib import Path
from unittest.mock import patch

import pytest

from invest.native_diagnostics import (SCHEMA, DiagnosticsBusy, DiagnosticsUnavailable,
                                      _LOCK, _sample, native_diagnostics)
from invest.native_research import restore_native_json
from invest.workspace import Workspace, canonical, digest
from test_mlflow_local import http_server

FIXTURE = Path(__file__).with_name('fixtures')/'native_research_v1_synthetic.json'
sdk = pytest.mark.skipif(importlib.util.find_spec('statsmodels') is None,
                         reason='optional actual statsmodels is not installed')


@pytest.fixture
def record():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


@pytest.mark.parametrize('value', [[],None,[True],[float('nan')],[float('inf')],
    [-float('inf')],['0.1'],[1_000_001],[-1_000_001],[0]*10001])
def test_sample_refuses_invalid_values(value):
    with pytest.raises(ValueError):
        _sample(value)


@pytest.mark.parametrize('n', [1,2,19,29])
def test_insufficient_sample_has_no_invented_statistic(n):
    assert _sample([.1]*n)==('insufficient_observations', min(10,n//5), None)


@pytest.mark.parametrize('value', [0,.1,-.01,1e6,1e-200])
def test_exact_constant_samples_are_not_called_normal_or_independent(value):
    assert _sample([value]*36)==('constant_series',7,None)


def test_fixed_lag_and_scale_normalization():
    status,lag,x=_sample([(-1)**i*(i+1)*1e-200 for i in range(36)])
    assert status=='computed' and lag==7 and max(map(abs,x))==1
    assert all(math.isfinite(v) for v in x)
    assert abs(math.fsum(x))<1e-12
    assert _sample(list(range(100)))[1]==10


@pytest.mark.parametrize('mutate', [lambda r:r.update(kind='study'),
    lambda r:r['payload']['curve']['rows'][0].__setitem__(-2,999),
    lambda r:r['payload']['summary'].update(sharpe=999),
    lambda r:r['payload']['optimization']['trials'][0].update(score=999)])
def test_invalid_record_is_rejected_before_sdk_discovery(record, mutate):
    mutate(record);record['id']=digest({'kind':record['kind'],'payload':record['payload']})
    with patch('invest.native_diagnostics.metadata.version',side_effect=AssertionError('SDK queried')):
        with pytest.raises(ValueError):native_diagnostics(record)
    assert not _LOCK.locked()


@pytest.mark.parametrize('error',[metadata.PackageNotFoundError('statsmodels'),'99.0'])
def test_unavailable_sdk_is_explicit_and_record_immutable(record,error):
    before=canonical(record)
    with patch('invest.native_diagnostics.metadata.version',side_effect=error if isinstance(error,Exception) else None,
               return_value=error if isinstance(error,str) else None):
        with pytest.raises(DiagnosticsUnavailable):native_diagnostics(record)
    assert canonical(record)==before and not _LOCK.locked()


def test_busy_rejects_before_validation(record):
    assert _LOCK.acquire(blocking=False)
    try:
        with patch('invest.native_diagnostics.validate_native_record',side_effect=AssertionError('validation called')):
            with pytest.raises(DiagnosticsBusy):native_diagnostics(record)
    finally:_LOCK.release()


@sdk
def test_actual_sdk_matches_reference_and_only_saved_evaluation(record,monkeypatch):
    from statsmodels.stats.diagnostic import acorr_ljungbox
    from statsmodels.stats.stattools import durbin_watson,jarque_bera
    def forbidden(*a,**k):raise AssertionError('producer execution forbidden')
    monkeypatch.setattr('invest.native_research.run_and_save_native_research',forbidden)
    monkeypatch.setattr('invest.native_research.run_a_share_research_bundle',forbidden)
    monkeypatch.setattr('invest.optuna_walkforward.optimize_sma_walkforward',forbidden)
    monkeypatch.setattr('invest.providers.duckdb_cache.DuckDBReplayProvider.history',forbidden)
    before=canonical(record)
    result=native_diagnostics(record)
    curve=record['payload']['curve'];j=curve['columns'].index('strategy_return')
    values=[row[j] for row in curve['rows']];status,lag,x=_sample(values)
    lb=acorr_ljungbox(x,lags=[lag],model_df=0,period=None,auto_lag=False)
    jb,jbp,skew,kurt=jarque_bera(x)
    assert result['results']=={'ljung_box':{'lag':lag,'statistic':float(lb.lb_stat.iloc[0]),'asymptotic_pvalue':float(lb.lb_pvalue.iloc[0])},
        'jarque_bera':{'statistic':float(jb),'asymptotic_pvalue':float(jbp),'skewness':float(skew),'pearson_kurtosis':float(kurt)},
        'durbin_watson_centered':float(durbin_watson(x))}
    assert result['observations']==36==record['payload']['split']['evaluation_observations']
    assert result['record_id']==record['id'] and result['record_sha256']==digest(record)
    assert result['curve_sha256']==digest(curve) and result['returns_sha256']==digest(values)
    assert result['evaluation_start']==curve['dates'][0] and result['evaluation_end']==curve['dates'][-1]
    assert result['schema']==SCHEMA and result['status']==status=='computed'
    assert result['protocol']['alpha_or_pass_fail_decision'] is None
    assert result['diagnostics_id']==digest({k:v for k,v in result.items() if k!='diagnostics_id'})
    assert native_diagnostics(record)==result and canonical(record)==before
    result['producer_declaration']['python']='modified'
    assert canonical(record)==before


@sdk
def test_timestamp_declaration_changes_full_identity_not_statistics(record):
    a=native_diagnostics(record)
    record['recorded_at']='2000-01-01T00:00:00+00:00'
    b=native_diagnostics(record)
    assert a['record_id']==b['record_id'] and a['results']==b['results']
    assert a['record_sha256']!=b['record_sha256'] and a['diagnostics_id']!=b['diagnostics_id']


def test_http_missing_dependency_preserves_record_and_unlocks(tmp_path,record):
    restore_native_json(json.dumps(record),tmp_path/'state.sqlite')
    with http_server(tmp_path) as (server,request):
        with patch('invest.native_diagnostics.metadata.version',side_effect=metadata.PackageNotFoundError('statsmodels')):
            code,body=request('/api/workbench/native-diagnostics?id='+record['id'])
        assert code==503 and body['record_saved'] is True and 'diagnostics' in body['error']
        assert not server.study_lock.locked() and not _LOCK.locked()
        assert Workspace(tmp_path/'state.sqlite').get(record['id'])==record


@sdk
def test_http_restore_same_diagnostics_and_no_other_data_written(tmp_path,record):
    expected=native_diagnostics(record)
    for name in ('first','restored'):
        root=tmp_path/name;restore_native_json(json.dumps(record),root/'state.sqlite')
        with http_server(root) as (server,request):
            code,body=request('/api/workbench/native-diagnostics?id='+record['id'])
            assert code==200 and body==expected and not server.study_lock.locked()
            assert Workspace(root/'state.sqlite').get(record['id'])==record
            assert len(Workspace(root/'state.sqlite').list('native_research'))==1
        assert not (root/'mlflow').exists()


@pytest.mark.parametrize('value',['../x','x%0d%0aInjected','x%3BDROP%20TABLE%20records','a'*65])
def test_http_bad_identity_rejected(tmp_path,value):
    with http_server(tmp_path) as (server,request):
        code,_=request('/api/workbench/native-diagnostics?id='+value)
        assert code==400 and not server.study_lock.locked()


@sdk
def test_real_saved_insufficient_and_constant_records(tmp_path):
    from test_native_research import execute, synthetic_frame, _frame_digest, _json, _sha
    short,_=execute(Workspace(tmp_path/'short.sqlite'),training_fraction=.83)
    result=native_diagnostics(short)
    assert result['status']=='insufficient_observations' and result['observations']==21
    assert result['results'] is None
    frame=synthetic_frame()
    for column in ['open','high','low','close']: frame[column]=100.0
    snapshot=frame.attrs['duckdb_replay']
    snapshot['data_sha256']=_frame_digest(frame)
    snapshot['snapshot_id']=_sha(_json({k:v for k,v in snapshot.items() if k not in {'snapshot_id','cache_status'}}))
    flat,_=execute(Workspace(tmp_path/'flat.sqlite'),frame=frame)
    result=native_diagnostics(flat)
    assert result['status']=='constant_series' and result['results'] is None
    assert result['observations']==36


def test_pinned_license_bytes():
    import hashlib
    root=Path(__file__).resolve().parents[1]
    source=root/'third_party/statsmodels'
    provenance=json.loads((source/'PROVENANCE.json').read_text())
    assert hashlib.sha256((source/'LICENSE.txt').read_bytes()).hexdigest()==provenance['license_sha256']=='1ca78e1dec9dcebc55f3b96a862317f23e76422c5fc943568d955aad1f6b5fad'
    assert provenance['runtime_version']=='0.15.0' and provenance['source_revision']=='278ff9950636cdd4939b4055e339a8e681d79cab'
