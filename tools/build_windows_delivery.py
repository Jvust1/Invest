"""Build the current checked-out source, test the real Windows program, then package it."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile


def main():
    ROOT=Path(__file__).resolve().parents[1]
    NAME=os.environ.get('DESKTOP_APP','Invest')
    if NAME != 'Invest':
        raise ValueError('This repository only builds Invest')
    OUT=ROOT/'delivery';EVIDENCE=OUT/'evidence'
    OUT.mkdir(exist_ok=True);EVIDENCE.mkdir(exist_ok=True)
    sys.path.insert(0,str(ROOT))
    from invest.provenance import source_manifest
    from invest import __version__
    subprocess.run(['git','diff','HEAD','--exit-code'],cwd=ROOT,check=True)
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    identity=source_manifest(ROOT/'invest',source_commit=commit)
    tracked=subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD','--','invest'],cwd=ROOT,text=True).splitlines()
    tracked_core={name.removeprefix('invest/') for name in tracked if name.endswith('.py')}
    if tracked_core != set(identity['files']):
        raise ValueError('Source manifest contains missing or untracked Python files')
    identity_path=EVIDENCE/'build_identity.json'
    identity_path.write_text(json.dumps(identity,ensure_ascii=False,indent=2),encoding='utf-8')

    def run(args,**kwargs):
        subprocess.run(args,check=True,cwd=ROOT,**kwargs)

    args=[sys.executable,'-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
          '--name',NAME,'--exclude-module','playwright','--exclude-module','pytest']
    args+=['--add-data','invest/web:invest/web','--add-data',str(identity_path)+':invest']
    args+=['desktop.py']
    run(args)
    package=ROOT/'dist'/NAME
    # Font binaries are deliberately NOT distributed; use installed system fonts.
    removed=[]
    for p in sorted(package.rglob('*')):
        if p.is_file() and p.suffix.lower() in {'.ttf','.otf','.woff','.woff2','.eot','.ttc'}:
            removed.append(p.relative_to(package).as_posix());p.unlink()
    for p in package.rglob('*.css'):
        text=p.read_text(encoding='utf-8',errors='strict')
        text=re.sub(r'@font-face\s*\{[^}]*\}', '', text)
        p.write_text(text,encoding='utf-8')
    (EVIDENCE/'font-exclusion.json').write_text(json.dumps({'font_binaries_distributed':0,'excluded_count':len(removed)},indent=2))
    exe=package/(NAME+'.exe')
    with tempfile.TemporaryDirectory(prefix=NAME+'-native-') as temp:
        smoke=EVIDENCE/'native-smoke.json'
        run([str(exe),'--self-test',str(smoke),'--data-dir',str(Path(temp)/'controller')],timeout=150)
        assert json.loads(smoke.read_text(encoding='utf-8'))['ok']
    run([sys.executable,'tools/desktop_browser_test.py',str(exe),str(EVIDENCE)],timeout=240)
    # Check the actual EXE's HTTP-exported study, not just a source-level test.
    study=json.loads((EVIDENCE/'browser-synthetic-study.json').read_text(encoding='utf-8'))
    protocol=study['payload']['protocol']
    if protocol.get('code_identity') != identity['code_identity'] or protocol.get('code_identity_scheme') != identity['schema']:
        raise ValueError('Packaged research provenance does not match the built source')
    (EVIDENCE/'packaged-code-identity.json').write_text(json.dumps({'status':'PASS','source_commit':commit,'source_code_identity':identity['code_identity'],'packaged_http_code_identity':protocol['code_identity'],'scheme':identity['schema'],'core_files':len(identity['files']),'evidence':'browser-synthetic-study.json','bytecode_signature_claim':False},indent=2),encoding='utf-8')
    # The source itself must still be the commit that was tested.
    run(['git','diff','HEAD','--exit-code'])
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    shutil.copy2(ROOT/'docs/G1_G5_DESKTOP.md',package/'使用说明.md')
    (package/'SOURCE_COMMIT.txt').write_text(commit+'\n',encoding='utf-8')
    manifest={'app':NAME,'version':__version__,'source_commit':commit, 'code_identity':identity['code_identity'],
              'code_identity_scheme':identity['schema'],
              'built_on':sys.platform,'python':sys.version,'native_executable_smoke':True,
              'actual_user_device_tested':False,'live_model_quality_accepted':False,'files':[]}
    for p in sorted(package.rglob('*')):
        if p.is_file():manifest['files'].append({'path':p.relative_to(package).as_posix(),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
    (package/'PACKAGE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    portable=OUT/(NAME+'-Windows-Portable.zip')
    with zipfile.ZipFile(portable,'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file():z.write(p,NAME+'/'+p.relative_to(package).as_posix())
    source=OUT/(NAME+'-Source-and-Tests.zip')
    run(['git','archive','--format=zip','HEAD','-o',str(source)])
    # Store evidence separately, not personal data or test working directories.
    with zipfile.ZipFile(OUT/(NAME+'-Verification.zip'),'w',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(EVIDENCE.rglob('*')):
            if p.is_file():z.write(p,p.relative_to(EVIDENCE).as_posix())
    (OUT/'release.json').write_text(json.dumps({k:v for k,v in manifest.items() if k!='files'},indent=2),encoding='utf-8')
    (OUT/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in sorted(OUT.glob('*.zip'))),encoding='utf-8')
    print(json.dumps({'app':NAME,'status':'BUILT_NATIVE_SMOKE_AND_BROWSER_PASS','commit':commit,'package_bytes':portable.stat().st_size}))


if __name__=="__main__":
    main()
