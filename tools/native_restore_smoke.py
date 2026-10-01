"""Verify native JSON restore from an installed wheel without optional SDKs.

Only the authored historical synthetic fixture is used. The installed package
must restore, list, and export its original envelope without a provider/search.
The explicit --charts mode additionally permits only the pinned Matplotlib SDK
and verifies the native derivative; the default remains fully SDK-free.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

CHILD = r'''
import builtins,json,sys,threading,subprocess
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
installed,root,fixture=map(lambda value:Path(value).resolve(),sys.argv[1:4])
with_charts=sys.argv[4]=='charts'
with_diagnostics=sys.argv[4]=='diagnostics'
chart_evidence={}
sys.path.insert(0,str(installed))
optional={'mlflow','duckdb','optuna','qlib','pyqlib','matplotlib','statsmodels'}
if with_charts:
    optional.remove('matplotlib')
if with_diagnostics:
    optional.remove('statsmodels')
attempts=[]
original_import=builtins.__import__
def guarded_import(name,*args,**kwargs):
    if name.split('.')[0] in optional:
        attempts.append(name)
        raise AssertionError('optional SDK import forbidden during native recovery')
    return original_import(name,*args,**kwargs)
builtins.__import__=guarded_import
network_attempts=[]
def local_only(event,args):
    if event in {'socket.connect','socket.bind'}:
        address=args[1]
        if not isinstance(address,tuple) or address[0] not in {'127.0.0.1','::1'}:
            network_attempts.append(event)
            raise AssertionError('external network forbidden during native recovery')
    elif event=='socket.getaddrinfo' and args[0] not in {'127.0.0.1','::1','localhost'}:
        network_attempts.append(event)
        raise AssertionError('external DNS forbidden during native recovery')
    elif event=='socket.sendto':
        network_attempts.append(event)
        raise AssertionError('datagram network forbidden during native recovery')
sys.addaudithook(local_only)
import invest
assert Path(invest.__file__).resolve().is_relative_to(installed)
from invest.native_research import restore_native_json,validate_native_record,parse_native_json
from invest.workspace import Workspace,canonical
from invest.server import InvestServer,encode_json
raw=fixture.read_text(encoding='utf-8')
original=parse_native_json(raw)
workspace=root/'restored'/'state.sqlite'
assert not workspace.parent.exists()
restored=restore_native_json(raw,workspace)
assert restored==original
assert canonical(restored)==canonical(original)
assert restore_native_json(raw,workspace)==original
reopened=Workspace(workspace).get(original['id'],'native_research')
assert canonical(reopened)==canonical(original)
assert len(Workspace(workspace).list('native_research'))==1
assert restored['recorded_at']==original['recorded_at']
assert restored['payload']['producer']==original['payload']['producer']
# A different timestamp is a conflicting envelope even though it is outside the
# content ID. The importer never replaces the existing saved declaration.
conflict=json.loads(raw)
conflict['recorded_at']='2001-01-01T00:00:00+00:00'
assert conflict['recorded_at']!=original['recorded_at']
try:
    restore_native_json(json.dumps(conflict),workspace)
except ValueError:
    pass
else:
    raise AssertionError('conflicting timestamp was silently accepted')
assert Workspace(workspace).get(original['id'])==original
invalid_destination=root/'invalid-destination'/'state.sqlite'
invalid=json.loads(raw);invalid['kind']='study'
try:
    restore_native_json(json.dumps(invalid),invalid_destination)
except ValueError:
    pass
else:
    raise AssertionError('cash schema entered native restore')
assert not invalid_destination.parent.exists()
server=InvestServer(('127.0.0.1',0),workspace.parent,track_experiments=False)
thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
base=f'http://127.0.0.1:{server.server_port}'
opener=build_opener(ProxyHandler({}))
try:
    with opener.open(base+'/api/workbench/documents?kind=native_research',timeout=15) as response:
        listing=json.loads(response.read())
    assert len(listing['documents'])==1 and listing['documents'][0]['id']==original['id']
    assert listing['documents'][0]['recorded_at']==original['recorded_at']
    with opener.open(base+'/api/workbench/document?id='+original['id'],timeout=15) as response:
        downloaded=response.read()
    assert downloaded==encode_json(reopened)
    assert validate_native_record(parse_native_json(downloaded.decode('utf-8')))==original
    js=r"""
const fs=require('node:fs'),vm=require('node:vm');
(async()=>{const [base,id,path]=process.argv.slice(1);
const response=await fetch(base+'/workbench.js');if(!response.ok)throw new Error('script missing');
const source=await response.text();let result;
const context={Blob,AbortSignal,encodeURIComponent,csrf:'',
fetch:(route,options)=>fetch(base+route,options),download:(blob,name)=>{result={blob,name};}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='),source.indexOf('function action(')),context);
await context.savedRecordDownload(id,'native-'+id+'.json');
if(!result||result.name!=='native-'+id+'.json')throw new Error('wrong saved identity');
fs.writeFileSync(path,Buffer.from(await result.blob.arrayBuffer()));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
    output=root/'restored-browser-export.json'
    result=subprocess.run(['node','-e',js,base,original['id'],str(output)],capture_output=True,timeout=30)
    assert result.returncode==0,result.stderr
    assert output.read_bytes()==downloaded
    assert validate_native_record(parse_native_json(output.read_text(encoding='utf-8')))==original
    if with_diagnostics:
        from invest.workspace import digest
        with opener.open(base+'/api/workbench/native-diagnostics?id='+original['id'],timeout=30) as response:
            assert response.headers.get_content_type()=='application/json'
            diagnostics_bytes=response.read()
        diagnostics=json.loads(diagnostics_bytes)
        assert diagnostics['schema']=='invest-native-diagnostics-v1'
        assert diagnostics['record_id']==original['id'] and diagnostics['record_sha256']==digest(original)
        assert diagnostics['curve_sha256']==digest(original['payload']['curve'])
        assert diagnostics['observations']==36 and diagnostics['status']=='computed'
        assert diagnostics['protocol']['lag']==7
        assert diagnostics['upstream']['version']=='0.15.0'
        assert diagnostics['diagnostics_id']==digest({k:v for k,v in diagnostics.items() if k!='diagnostics_id'})
        assert diagnostics['producer_declaration']==original['payload']['producer']
        assert diagnostics['recorded_at_declaration']==original['recorded_at']
        with opener.open(base+'/api/workbench/native-diagnostics?id='+original['id'],timeout=30) as response:
            assert response.read()==diagnostics_bytes
        diagnostic_js=js.replace("savedRecordDownload(id,'native-'+id+'.json')", "nativeDiagnosticsDownload(id,'native-'+id+'.json')")
        diagnostic_output=root/'native-browser-diagnostics.json'
        diagnostic_run=subprocess.run(['node','-e',diagnostic_js,base,original['id'],str(diagnostic_output)],capture_output=True,timeout=30)
        assert diagnostic_run.returncode==0,diagnostic_run.stderr
        assert diagnostic_output.read_bytes()==diagnostics_bytes
        chart_evidence.update(native_diagnostics_actual_sdk=True,native_diagnostics_record_identity=True,
            native_diagnostics_served_js_exact_bytes=True,native_diagnostics_repeat_identical=True)
    if with_charts:
        import io
        from PIL import Image
        from invest.workspace import digest
        from invest.study_charts import prepare_chart
        with opener.open(base+'/api/workbench/native-chart?id='+original['id'],timeout=30) as response:
            assert response.headers.get_content_type()=='image/png'
            native_png=response.read()
        with Image.open(io.BytesIO(native_png)) as image:
            assert image.format=='PNG' and image.size==(1200,900)
            image.load()
            assert len(image.convert('RGB').getcolors(1200*900))>100
            identity=json.loads(image.info['Description'])
            assert identity['schema']=='invest-native-research-chart-v1'
            assert identity['record_id']==original['id']
            assert identity['record_sha256']==digest(original)
            assert identity['curve_sha256']==digest(original['payload']['curve'])
            assert identity['producer_declaration']==original['payload']['producer']
            assert identity['recorded_at_declaration']==original['recorded_at']
            assert identity['initial_unit_capital']==1.0
            assert identity['renderer']['version']=='3.10.8'
        with opener.open(base+'/api/workbench/native-chart?id='+original['id'],timeout=30) as response:
            assert response.read()==native_png
        # Cash validation must still reject the separate native schema.
        try:
            prepare_chart(original,0)
        except ValueError:
            pass
        else:
            raise AssertionError('native record entered cash chart validation')
        chart_js=r"""
const fs=require('node:fs'),vm=require('node:vm');
(async()=>{const [base,id,path]=process.argv.slice(1);
const response=await fetch(base+'/workbench.js');if(!response.ok)throw new Error('script missing');
const source=await response.text();let result;
const context={Blob,AbortSignal,encodeURIComponent,csrf:'',
fetch:(route,options)=>fetch(base+route,options),download:(blob,name)=>{result={blob,name};}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='),source.indexOf('function action(')),context);
await context.nativeChartDownload(id,'native-chart-'+id+'.png');
if(!result||result.name!=='native-chart-'+id+'.png')throw new Error('wrong native chart identity');
fs.writeFileSync(path,Buffer.from(await result.blob.arrayBuffer()));
})().catch(error=>{console.error(error);process.exitCode=1;});
"""
        chart_output=root/'native-browser-chart.png'
        chart_run=subprocess.run(['node','-e',chart_js,base,original['id'],str(chart_output)],capture_output=True,timeout=30)
        assert chart_run.returncode==0,chart_run.stderr
        assert chart_output.read_bytes()==native_png
        chart_evidence={'native_png_identity_verified':True,'native_png_pixels_decoded':True,
            'native_png_repeat_identical':True,
            'native_served_javascript_png_byte_identical':True,'cash_validator_still_rejects_native':True}
finally:
    server.shutdown();thread.join(10);server.server_close()
if with_charts:
    # Recover the actual exported JSON into a second empty installed workspace;
    # no source provider/cache or research execution can participate.
    second=root/'chart-restored'/'state.sqlite'
    assert restore_native_json(downloaded.decode('utf-8'),second)==original
    other=InvestServer(('127.0.0.1',0),second.parent,track_experiments=False)
    worker=threading.Thread(target=other.serve_forever,daemon=True);worker.start()
    try:
        other_base=f'http://127.0.0.1:{other.server_port}'
        with opener.open(other_base+'/api/workbench/native-chart?id='+original['id'],timeout=30) as response:
            assert response.read()==native_png
        assert Workspace(second).get(original['id'])==original
    finally:
        other.shutdown();worker.join(10);other.server_close()
    assert not (second.parent/'mlflow').exists()
    chart_evidence['native_chart_after_json_restore_identical']=True
if with_diagnostics:
    second=root/'diagnostics-restored'/'state.sqlite'
    assert restore_native_json(downloaded.decode('utf-8'),second)==original
    other=InvestServer(('127.0.0.1',0),second.parent,track_experiments=False)
    worker=threading.Thread(target=other.serve_forever,daemon=True);worker.start()
    try:
        with opener.open(f'http://127.0.0.1:{other.server_port}/api/workbench/native-diagnostics?id='+original['id'],timeout=30) as response:
            assert response.read()==diagnostics_bytes
        assert Workspace(second).get(original['id'])==original
    finally:
        other.shutdown();worker.join(10);other.server_close()
    assert not (second.parent/'mlflow').exists()
    chart_evidence['native_diagnostics_after_json_restore_identical']=True
assert not attempts,attempts
assert not network_attempts,network_attempts
assert not (workspace.parent/'mlflow').exists()
print(json.dumps({'schema':'invest-installed-native-recovery-v1','synthetic_only':True,
    'installed_wheel_import':True,'guarded_optional_sdks':sorted(optional),
    'optional_sdk_import_attempts':0,'python_external_network_attempts':0,
    'node_fetch_scope':'loopback_base_only',
    'restore_empty_workspace':True,'repeated_restore_idempotent':True,
    'conflicting_timestamp_rejected':True,'cash_schema_rejected_before_write':True,
    'record_identity_preserved':True,'producer_and_timestamp_preserved_as_declarations':True,
    'http_list_and_raw_export':True,'served_javascript_export_byte_identical':True,
    'offline_arithmetic_revalidated':True,'mlflow_archive_used':False,
    'native_cash_units_conflated':False,'browser_layout_verified':False,**chart_evidence}))
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    mode=parser.add_mutually_exclusive_group()
    mode.add_argument('--charts', action='store_true', help='also verify pinned native PNG; default forbids every optional SDK')
    mode.add_argument('--diagnostics', action='store_true', help='verify actual statsmodels diagnostics; other optional SDKs remain forbidden')
    args = parser.parse_args(argv)
    wheel = args.wheel.resolve(strict=True)
    if wheel.is_dir():
        wheels = list(wheel.glob('invest-*.whl'))
        if len(wheels) != 1:
            parser.error('wheel directory must contain exactly one invest wheel')
        wheel = wheels[0]
    if wheel.suffix != '.whl':
        parser.error('expected a built invest wheel')
    with ZipFile(wheel) as package:
        required = {'invest/native_research.py', 'invest/workspace.py', 'invest/web/workbench.js'}
        if args.charts:
            required.add('invest/native_charts.py')
        if args.diagnostics:
            required.add('invest/native_diagnostics.py')
        if not required.issubset(package.namelist()):
            raise ValueError('wheel lacks native recovery/chart modules or web assets')
    fixture = Path(__file__).resolve().parents[1]/'tests'/'fixtures'/'native_research_v1_synthetic.json'
    with tempfile.TemporaryDirectory(prefix='invest-native-restore-wheel-') as directory:
        root = Path(directory)
        target = root/'installed'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index',
            '--target', str(target), str(wheel)], cwd=root, check=True, timeout=90, stdout=subprocess.DEVNULL)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1',
                   MPLCONFIGDIR=str(root/'matplotlib-cache'))
        result = subprocess.run([sys.executable, '-I', '-c', CHILD, str(target), str(root), str(fixture), 'charts' if args.charts else 'diagnostics' if args.diagnostics else 'core'],
            cwd=root, env=env, capture_output=True, timeout=90)
        if result.returncode:
            detail=(result.stdout+result.stderr).decode('utf-8',errors='replace')[-12000:]
            raise RuntimeError('installed native recovery failed:\n'+detail)
        print(json.dumps(json.loads(result.stdout), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
