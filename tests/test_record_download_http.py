"""Python HTTP -> actual workbench JavaScript Blob -> Python identity replay."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from invest.native_research import validate_native_record
from invest.server import encode_json
from invest.workspace import Workspace
from test_mlflow_local import http_server

NODE = shutil.which('node')


@pytest.mark.skipif(NODE is None, reason='optional Node runtime required for cross-language UI byte proof')
def test_actual_http_javascript_download_preserves_native_record_identity(tmp_path):
    golden = json.loads((Path(__file__).with_name('fixtures') / 'native_research_v1_synthetic.json').read_text(encoding='utf-8'))
    saved = Workspace(tmp_path / 'state.sqlite').put('native_research', golden['payload'])
    output = tmp_path / 'downloaded-native.json'
    script = r'''
const fs=require('node:fs'),vm=require('node:vm');
(async()=>{
  const [base,id,destination]=process.argv.slice(1);
  const source=await (await fetch(base+'/workbench.js')).text();
  const helper=source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='),source.indexOf('function action('));
  let result;
  const context={Blob,AbortSignal,encodeURIComponent,csrf:'',
    fetch:(route,options)=>fetch(base+route,options),
    download:(blob,name)=>{result={blob,name};}};
  vm.createContext(context);vm.runInContext(helper,context);
  await context.savedRecordDownload(id,'native-'+id+'.json');
  if(result.name!=='native-'+id+'.json')throw new Error('wrong saved identity filename');
  fs.writeFileSync(destination,Buffer.from(await result.blob.arrayBuffer()));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    with http_server(tmp_path) as (server, _):
        run = subprocess.run([NODE, '-e', script, f'http://127.0.0.1:{server.server_port}', saved['id'], str(output)],
                             capture_output=True, text=True, timeout=30)
    assert run.returncode == 0, run.stderr
    assert output.read_bytes() == encode_json(saved)
    downloaded = json.loads(output.read_text(encoding='utf-8'))
    assert validate_native_record(downloaded) == saved
    assert downloaded['id'] == golden['id']
    # Demonstrate the avoided cross-language bug: valid floats include integral
    # values; keeping just their apparent JS numeric value would change the ID.
    assert any(type(value) is float and value.is_integer()
               for row in saved['payload']['input']['rows'] for value in row)
