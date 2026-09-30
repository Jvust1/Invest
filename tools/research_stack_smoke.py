"""Install a built wheel outside the checkout and exercise the integrated pilot.

The active interpreter needs the declared research-stack extras. All input is
authored synthetic data. No market download, account, credential or order API.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

CHILD = r'''
import io,json,sys,threading,subprocess
from dataclasses import asdict
from importlib import metadata
from pathlib import Path
from urllib.request import Request,build_opener,ProxyHandler
target,root,source=map(lambda p:Path(p).resolve(),sys.argv[1:4])
sys.path.insert(0,str(target))
import invest
assert Path(invest.__file__).resolve().is_relative_to(target), 'source checkout leaked into installed-wheel proof'
from invest.qlib_bridge import create_qlib_market_provider
from invest.providers.duckdb_cache import DuckDBMarketCache,DuckDBReplayProvider,DuckDBCacheMiss
from invest.research_pipeline import run_a_share_research_bundle
from invest.native_research import run_and_save_native_research,validate_native_record
from invest.pipeline import run_a_share_sma_backtest,performance_summary
from invest.server import InvestServer
from invest.backup import restore_backup
from invest.workspace import Workspace
from PIL import Image
import pandas as pd

versions={name:metadata.version(name) for name in ('pyqlib','mlflow','matplotlib','duckdb','optuna','scikit-learn')}
assert versions['pyqlib']=='0.9.7' and versions['mlflow']=='3.16.1' and versions['matplotlib']=='3.10.8'
assert versions['duckdb']=='1.5.6' and versions['optuna']=='5.0.0'
provider=create_qlib_market_provider(provider_uri=source)
request={'symbol':'000001.SH','start_date':'20250102','end_date':'20250618','adjust':'qlib'}
source_id='synthetic-native-qlib-pilot/v1;unconverted-unverified-units'
cache_path=root/'native.duckdb'
with DuckDBMarketCache(cache_path) as cache:
    refresh=DuckDBReplayProvider(cache,source_id=source_id,upstream=provider,mode='refresh')
    captured=refresh.history(**request)
    snapshot=refresh.last_snapshot
assert len(captured)==120 and captured.attrs['market_data']['instrument']=='SH000001'
assert captured.attrs['market_data']['price_basis']=='qlib_native_unconverted'
# Reopen without any upstream. Optimization and later evaluation consume the
# recorded native basis, never a mislabeled raw/qfq series or implicit refresh.
with DuckDBMarketCache(cache_path,read_only=True) as cache:
    replay=DuckDBReplayProvider(cache,source_id=source_id)
    bundle=run_a_share_research_bundle(replay,**request,optimization_trials=12,
        optimization_splits=3,training_fraction=.7,optimization_seed=7)
    assert bundle.research_split['training_observations']==84
    assert bundle.research_split['evaluation_observations']==36
    assert len(bundle.optimization.trials)==12 and bundle.optimization.optimizer_version=='5.0.0'
    assert len(bundle.backtest)==36 and len(bundle.market)==120
    for frame in (bundle.market,bundle.backtest):
        assert frame.attrs['market_data']==captured.attrs['market_data']
        assert frame.attrs['duckdb_replay']['snapshot_id']==snapshot['snapshot_id']
    native_record=run_and_save_native_research(Workspace(root/'workbench'/'state.sqlite'),replay,
        request['symbol'],start_date=request['start_date'],end_date=request['end_date'],input_role='synthetic',
        optimization_trials=12,optimization_splits=3,training_fraction=.7,optimization_seed=7)
    assert native_record['payload']['summary']==bundle.summary
    assert native_record['payload']['optimization']['params']==bundle.optimization.params
    assert native_record['payload']['snapshot']['snapshot_id']==snapshot['snapshot_id']
    assert native_record['payload']['optimization']['implementation']=='optuna_tpe'
    assert len(native_record['payload']['input']['rows'])==120
    assert len(native_record['payload']['curve']['rows'])==36
    validate_native_record(native_record)
    assert Workspace(root/'workbench'/'state.sqlite').put('native_research',native_record['payload'])==native_record
    baseline,_=run_a_share_sma_backtest(**request,provider_instance=replay,
        fast=bundle.optimization.params['fast'],slow=bundle.optimization.params['slow'])
    later=baseline.iloc[84:].copy()
    later['equity']=(1+later['strategy_return']).cumprod()
    pd.testing.assert_frame_equal(later,bundle.backtest)
    assert performance_summary(later)==bundle.summary
    try:
        replay.history(**{**request,'symbol':'SH000001'})
    except DuckDBCacheMiss:
        pass
    else:
        raise AssertionError('exact-request cache silently matched an alias')
(root/'native-research.json').write_text(json.dumps(native_record,indent=2,allow_nan=False),encoding='utf-8')

# Native normalized prices intentionally do not enter the strict cash/lot/T+1
# engine. Its independent pilot uses the existing explicitly synthetic dataset.
server=InvestServer(('127.0.0.1',0),root/'workbench',track_experiments=True)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
opener=build_opener(ProxyHandler({}));base=f'http://127.0.0.1:{server.server_port}'
def request_http(path,payload=None):
    headers={'Content-Type':'application/json','X-Invest-CSRF':server.csrf_token}
    body=json.dumps(payload).encode() if payload is not None else None
    with opener.open(Request(base+path,data=body,headers=headers),timeout=60) as response:
        assert response.status==200
        raw=response.read()
        return json.loads(raw) if 'json' in response.headers.get('Content-Type','') else raw
try:
    assert b'workbench.js' in request_http('/')
    script=request_http('/workbench.js')
    assert all(feature in script for feature in (b'chartPicker', b'walk_forward', b'archiveControls'))
    assert request_http('/api/workbench/document?id='+native_record['id'])==native_record
    # Exercise the installed package's actual JS byte-export path. Parsing the
    # Python JSON into JS numbers and stringify would destroy content identity.
    js = """
const fs=require('node:fs'),vm=require('node:vm');
(async()=>{const [base,id,out]=process.argv.slice(1);
const source=await(await fetch(base+'/workbench.js')).text();
let result;const context={Blob,AbortSignal,encodeURIComponent,csrf:'',
fetch:(route,opts)=>fetch(base+route,opts),download:(blob,name)=>{result={blob,name};}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='),source.indexOf('function action(')),context);
await context.savedRecordDownload(id,'native-'+id+'.json');
if(result.name!=='native-'+id+'.json')throw new Error('wrong saved identity filename');
fs.writeFileSync(out,Buffer.from(await result.blob.arrayBuffer()));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    downloaded_path=root/'native-browser-download.json'
    js_run=subprocess.run(['node','-e',js,base,native_record['id'],str(downloaded_path)],
        capture_output=True,text=True,timeout=30)
    assert js_run.returncode==0,js_run.stderr
    from invest.server import encode_json
    assert downloaded_path.read_bytes()==encode_json(native_record)
    assert validate_native_record(json.loads(downloaded_path.read_text(encoding='utf-8')))==native_record
    listing=request_http('/api/workbench/documents?kind=native_research')
    assert listing['documents'][0]['id']==native_record['id']
    assert listing['validation']=='content_identity_only; full_native_replay_on_download'
    dataset=request_http('/api/datasets/demo',{})
    assert dataset['meta']['source_kind']=='demo'
    saved=request_http('/api/workbench/study',{'dataset_id':dataset['id'],'specification':{
        'symbol':'600000.SH','cost_model_acknowledged':True,
        'walk_forward':{'n_splits':3,'gap':5,'test_size':15,'max_train_size':20}}})
    tracking=saved.pop('tracking')
    assert tracking['status']=='archived',tracking
    assert saved['payload']['schema']=='invest-walk-forward-study-v1'
    assert saved['payload']['summary']['succeeded']==9 and saved['payload']['summary']['failed']==0
    assert saved['payload']['protocol']['frozen_holdout_opened'] is False
    assert request_http('/api/workbench/document?id='+saved['id'])==saved
    retry=request_http('/api/workbench/track-study',{'study_id':saved['id']})['tracking']
    assert retry['status']=='archived' and retry['reused'] is True and retry['run_id']==tracking['run_id'],retry
    assert not server.study_lock.locked()
    png=request_http('/api/workbench/study-chart?id='+saved['id']+'&case=0')
    with Image.open(io.BytesIO(png)) as image:
        assert image.size==(1200,840)
        identity=json.loads(image.info['Description'])
        assert identity['study_id']==saved['id'] and identity['source_kind']=='demo'
        assert identity['schema']=='invest-walk-forward-study-v1'
        assert 'SYNTHETIC DEMO' in image.info['Disclaimer']
    (root/'study.json').write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    (root/'study.png').write_bytes(png)
    backup=request_http('/api/private-backup',{'confirm_private_export':True})
finally:
    server.shutdown();thread.join(10);server.server_close()
restored=restore_backup(backup,root/'restored')
assert Workspace(restored/'state.sqlite').get(saved['id'],'study')==saved
assert Workspace(restored/'state.sqlite').get(native_record['id'],'native_research')==native_record
assert not (restored/'native.duckdb').exists()
# Report validation/JSON after restore needs no optional SDK or provider call.
from unittest.mock import patch
with patch('invest.providers.duckdb_cache.DuckDBReplayProvider.history',side_effect=AssertionError('provider called')), \
     patch('invest.optuna_walkforward.optimize_sma_walkforward',side_effect=AssertionError('optimizer called')):
    validate_native_record(Workspace(restored/'state.sqlite').get(native_record['id'],'native_research'))
assert not (restored/'mlflow').exists(), 'derivative archive was silently added to private backup'
# A restored authoritative record must regenerate the same derivative image and
# rebuild the optional local archive without replaying data or copying MLflow DBs.
server=InvestServer(('127.0.0.1',0),restored,track_experiments=True)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'
try:
    assert request_http('/api/workbench/document?id='+saved['id'])==saved
    assert request_http('/api/workbench/document?id='+native_record['id'])==native_record
    assert request_http('/api/workbench/study-chart?id='+saved['id']+'&case=0')==png
    rebuilt=request_http('/api/workbench/track-study',{'study_id':saved['id']})['tracking']
    assert rebuilt['status']=='archived' and rebuilt['reused'] is False,rebuilt
    assert request_http('/api/workbench/document?id='+saved['id'])==saved
finally:
    server.shutdown();thread.join(10);server.server_close()
report={'schema':'invest-installed-research-stack-pilot-v1','installed_wheel_import':True,
    'synthetic_only':True,'versions':versions,'external_market_calls':0,'broker_connected':False,
    'native_replay_rows':120,'optimization_trials':12,'training_rows':84,'evaluation_rows':36,
    'native_source_identity_preserved':True,'native_research_json':True,
    'native_saved_record_id':native_record['id'],'native_record_restored_and_replayed':True,
    'native_embedded_input_rows':120,'native_full_trial_arithmetic_verified':True,
    'native_javascript_download_byte_identity':True,
    'rolling_cases':9,'saved_study_identity':saved['id'],'mlflow_archive_reused':True,
    'png_identity_verified':True,'private_backup_restored':True,
    'restored_chart_identical':True,'restored_archive_rebuilt':True,'frozen_holdout_opened':False,
    'browser_layout_verified':False,'native_prices_used_for_cash_execution':False}
(root/'pilot-report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,allow_nan=False))
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    args = parser.parse_args(argv)
    wheel = args.wheel.resolve(strict=True)
    if wheel.is_dir():
        wheels = list(wheel.glob('invest-*.whl'))
        if len(wheels) != 1:
            parser.error('wheel directory must contain exactly one invest wheel')
        wheel = wheels[0]
    if wheel.suffix != '.whl':
        parser.error('expected a built invest wheel')
    with ZipFile(wheel) as archive:
        required = {'invest/web/workbench.js', 'invest/web/workbench.html', 'invest/upstream_registry.json',
                    'invest/qlib_local.py', 'invest/study_charts.py', 'invest/walkforward.py', 'invest/native_research.py'}
        if not required.issubset(archive.namelist()):
            raise ValueError('wheel lacks the integrated runtime modules/assets')
    repo = Path(__file__).resolve().parents[1]
    # Only fixture authoring happens in the checkout. Every production import,
    # SDK worker and HTTP request runs from the installed wheel under Python -I.
    sys.path.insert(0, str(repo))
    spec = importlib.util.spec_from_file_location('synthetic_qlib_fixture', repo/'examples/qlib_local_research.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    with tempfile.TemporaryDirectory(prefix='invest-stack-wheel-') as directory:
        root = Path(directory)
        fixture.write_synthetic_dataset(root/'qlib-source')
        target = root/'installed'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index',
                        '--target', str(target), str(wheel)], check=True, cwd=root, timeout=90,
                       stdout=subprocess.DEVNULL)
        env = dict(os.environ, MLFLOW_DISABLE_TELEMETRY='true', DO_NOT_TRACK='true',
                   OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   MPLCONFIGDIR=str(root/'matplotlib-cache'))
        result = subprocess.run([sys.executable, '-I', '-c', CHILD, str(target), str(root), str(root/'qlib-source')],
                                cwd=root, env=env, capture_output=True, text=True, timeout=240)
        if result.returncode:
            raise RuntimeError('installed research stack failed:\n'+(result.stdout+result.stderr)[-16000:])
        report = json.loads(result.stdout)
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
