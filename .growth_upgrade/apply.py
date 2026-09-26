"""Expand a bounded, reviewed source capsule on exactly one feature branch.

The capsule is a transport artifact, not an alternative source of truth: after
verification the actual text files are committed, tested, and built normally.
"""
from pathlib import Path, PurePosixPath
import gzip
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import urllib.request
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
BRANCH='feat/g1-g5-workbench-20260926'
BASE='869c320e1dedd32e064e425f6c115aced5487b40'
EXPECTED='9daaab315a2f870d4b6f4eb2e57a452cef128100869cb1c490954253a0ca8c1a'

def git(*args,optional=False):
    r=subprocess.run(['git',*args],cwd=ROOT,text=True,capture_output=True)
    if r.returncode and not optional:
        raise RuntimeError(r.stderr)
    return r.stdout.strip() if not r.returncode else None

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None

def safe(rel):
    p=PurePosixPath(rel)
    if p.is_absolute() or '..' in p.parts or '\\' in rel or ':' in rel or not p.parts:
        raise ValueError('Unsafe source path')
    if p.parts[0] not in {'invest','tests','tools','docs','governance'} and rel not in {'AGENTS.md','README.md','desktop.py','desktop_adapter.py','desktop_runtime.py','restore_backup.py','pyproject.toml'}:
        raise ValueError('Source path outside declared scope: '+rel)
    if p.suffix not in {'.py','.md','.json','.toml','.html','.css','.js'}:
        raise ValueError('Unsupported source suffix')
    path=ROOT/rel
    if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
        raise ValueError('Unsafe source target')
    return path

def main():
    if os.environ.get('GITHUB_REPOSITORY')!='Jvust2/Invest' or os.environ.get('GITHUB_REF')!='refs/heads/'+BRANCH:
        raise SystemExit('Ref/repository outside the authorized candidate branch')
    archive=ROOT/'.growth_upgrade/source-capsule.json.gz'
    fresh=not archive.exists()
    if fresh:
        url=os.environ.get('SOURCE_CAPSULE_URL','')
        if url:print('::add-mask::'+url)
        parsed=urlsplit(url)
        if parsed.scheme!='https' or not parsed.hostname or not parsed.hostname.endswith('.oaiusercontent.com') or parsed.username or parsed.password:
            raise SystemExit('A fresh authorized source-file URL is required')
        try:
            with urllib.request.urlopen(url,timeout=60) as response:
                compressed=response.read(100001)
        except Exception:
            raise SystemExit('Source transport failed or expired; no source files changed') from None
    else:
        compressed=archive.read_bytes()
    if len(compressed)>100000:
        raise SystemExit('Oversized capsule')
    with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as z:
        raw=z.read(300001)
    if len(raw)>300000 or hashlib.sha256(raw).hexdigest()!=EXPECTED:
        raise SystemExit('Capsule SHA256 mismatch')
    capsule=json.loads(raw)
    if capsule['schema']!='invest-growth-source-capsule-v1' or capsule['repository']!='Jvust2/Invest' or capsule['branch']!=BRANCH or capsule['base_commit']!=BASE:
        raise SystemExit('Capsule identity mismatch')
    if fresh:archive.write_bytes(compressed)
    files=capsule['files'];prepends=capsule['prepend']
    if not 1<=len(files)<=40 or len(prepends)>5:
        raise SystemExit('Unexpected file scope')
    paths=set(files)|set(prepends)|{'governance/project_state.json'}
    for rel in paths:safe(rel)
    for rel,item in files.items():
        if hashlib.sha256(item['content'].encode()).hexdigest()!=item['sha256']:
            raise SystemExit('Invalid after hash: '+rel)
    already=all(sha(safe(rel))==item['sha256'] for rel,item in files.items())
    already=already and all(safe(rel).read_text(encoding='utf-8').startswith(prefix) for rel,prefix in prepends.items())
    if not already:
        # The bootstrap adds only capsule/workflow files. Never silently replace
        # a concurrent source change, including changes on the feature branch.
        for rel in paths:
            old=git('rev-parse',BASE+':'+rel,optional=True)
            current=git('rev-parse','HEAD:'+rel,optional=True)
            if old!=current:
                raise SystemExit('Source diverged from reviewed base: '+rel)
        for rel,item in files.items():
            path=safe(rel);path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(item['content'],encoding='utf-8',newline='\n')
        for rel,prefix in prepends.items():
            path=safe(rel);old=path.read_text(encoding='utf-8')
            path.write_text(prefix+old,encoding='utf-8',newline='\n')
        path=safe('governance/project_state.json');state=json.loads(path.read_text(encoding='utf-8'))
        state['validation_before_growth']=state.get('validation',{})
        state['validation']={'authority':'governance/growth_delivery_current.json','local_candidate_tests':224,
                             'remote_full_suite':'verify Actions output for the expanded source commit',
                             'empirical_acceptance':'PENDING'}
        state.update(capsule['state_patch'])
        path.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    for rel,item in files.items():
        if sha(safe(rel))!=item['sha256']:
            raise SystemExit('Expanded source verification failed: '+rel)
    evidence=Path(os.environ['RUNNER_TEMP'])/'invest-growth-evidence';evidence.mkdir(exist_ok=True)
    run=subprocess.run([sys.executable,'-m','unittest','discover','-s','tests','-v'],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (evidence/'source-tests.txt').write_text(run.stdout,encoding='utf-8')
    print(run.stdout)
    if run.returncode:raise SystemExit(run.returncode)
    subprocess.run([sys.executable,'-m','compileall','-q','invest','tests','tools'],cwd=ROOT,check=True)
    subprocess.run(['node','--check','invest/web/workbench.js'],cwd=ROOT,check=True)
    if not already:
        publish_paths=paths|{'.growth_upgrade/source-capsule.json.gz'}
        git('add','--',*sorted(publish_paths))
        staged=set((git('diff','--cached','--name-only') or '').splitlines())
        if not staged.issubset(publish_paths) or not staged:
            raise SystemExit('Unexpected staged source scope')
        current=git('rev-parse','HEAD')
        remote=git('ls-remote','origin','refs/heads/'+BRANCH).split()[0]
        if remote!=current or current!=os.environ['GITHUB_SHA']:
            raise SystemExit('Concurrent branch update; no force push')
        git('config','user.name','github-actions[bot]')
        git('config','user.email','41898282+github-actions[bot]@users.noreply.github.com')
        git('commit','-m','feat: integrate G1-G5 offline research workbench and executable evidence')
        git('push','origin','HEAD:refs/heads/'+BRANCH)
    source=git('rev-parse','HEAD')
    if git('ls-remote','origin','refs/heads/'+BRANCH).split()[0]!=source:
        raise SystemExit('Source publication readback mismatch')
    count=re.search(r'Ran (\d+) tests',run.stdout)
    report={'status':'PASS','source_commit':source,'capsule_sha256':EXPECTED,
            'source_files':len(files),'tests':int(count.group(1)) if count else None,
            'real_data_used':False,'real_holdout_opened':False,'empirical_gates_passed':False}
    (evidence/'source-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:f.write('source_commit='+source+'\n')
    print(json.dumps(report))

if __name__=='__main__':main()
