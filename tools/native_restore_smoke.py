"""Verify native JSON restore from an installed wheel without optional SDKs.

Only the authored historical synthetic fixture is used. The installed package
must restore, list, and export its original envelope without a provider/search.
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
sys.path.insert(0,str(installed))
optional={'mlflow','duckdb','optuna','qlib','pyqlib','matplotlib'}
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
finally:
    server.shutdown();thread.join(10);server.server_close()
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
    'native_cash_units_conflated':False,'browser_layout_verified':False}))
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
    with ZipFile(wheel) as package:
        if not {'invest/native_research.py', 'invest/workspace.py', 'invest/web/workbench.js'}.issubset(package.namelist()):
            raise ValueError('wheel lacks native recovery modules or web assets')
    fixture = Path(__file__).resolve().parents[1]/'tests'/'fixtures'/'native_research_v1_synthetic.json'
    with tempfile.TemporaryDirectory(prefix='invest-native-restore-wheel-') as directory:
        root = Path(directory)
        target = root/'installed'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index',
            '--target', str(target), str(wheel)], cwd=root, check=True, timeout=90, stdout=subprocess.DEVNULL)
        env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        result = subprocess.run([sys.executable, '-I', '-c', CHILD, str(target), str(root), str(fixture)],
            cwd=root, env=env, capture_output=True, timeout=90)
        if result.returncode:
            detail=(result.stdout+result.stderr).decode('utf-8',errors='replace')[-12000:]
            raise RuntimeError('installed native recovery failed:\n'+detail)
        print(json.dumps(json.loads(result.stdout), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
