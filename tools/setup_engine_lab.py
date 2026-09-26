"""Create a NEW isolated RQAlpha research environment from one verified archive.

This installs optional third-party packages into a dedicated virtual environment.
It does not modify your existing Python, Invest data, or fetch market data.
Read the upstream LICENSE before acknowledging it. No commercial rights granted.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.request
import venv
import zipfile

ROOT=Path(__file__).resolve().parents[1]
COMMIT='0d98adefa87956e26f3e7ca5b26b5f3fc7ca834f'
ARCHIVE_SHA256='9baa67dc8a1ed195894489bac52a0b92c307c9d79c164de55da5ed59df1d2b29'
ARCHIVE_URL='https://codeload.github.com/ricequant/rqalpha/zip/'+COMMIT
LIMIT=32*1024*1024


def verify_archive(path):
    path=Path(path)
    if not path.is_file() or path.stat().st_size>LIMIT:raise ValueError('Missing or oversized source ZIP')
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ARCHIVE_SHA256:raise ValueError('Pinned RQAlpha archive SHA256 mismatch; no installation performed')
    with zipfile.ZipFile(path) as z:
        name='rqalpha-'+COMMIT+'/LICENSE'
        license_text=z.read(name).decode('utf-8')
    return license_text


def download_source(destination):
    with urllib.request.urlopen(ARCHIVE_URL,timeout=60) as response:
        raw=response.read(LIMIT+1)
    if len(raw)>LIMIT:raise ValueError('Source download exceeds limit')
    Path(destination).write_bytes(raw)
    verify_archive(destination)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--environment',required=True,help='NEW virtual environment directory; never overwrites')
    source=parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--source-archive',help='Exact rqalpha snapshot ZIP inside the Drive 03 archive')
    source.add_argument('--download-source',action='store_true',help='Explicitly download the fixed source ZIP from official GitHub')
    parser.add_argument('--acknowledge-rqalpha-license',action='store_true')
    args=parser.parse_args(argv)
    if not args.acknowledge_rqalpha_license:parser.error('Read the upstream LICENSE and explicitly acknowledge permitted synthetic research use')
    target=Path(args.environment).resolve()
    if target.exists():parser.error('Environment directory already exists; nothing overwritten')
    if not target.parent.is_dir():parser.error('Environment parent directory does not exist')
    try:
        with tempfile.TemporaryDirectory(prefix='invest-rqalpha-setup-') as tmp:
            archive=Path(args.source_archive).resolve() if args.source_archive else Path(tmp)/'rqalpha-pinned.zip'
            if args.download_source:download_source(archive)
            license_text=verify_archive(archive)
            print('Verified source: ricequant/rqalpha@'+COMMIT)
            print('The upstream license contains noncommercial/commercial-use distinctions. No new rights granted.')
            venv.EnvBuilder(with_pip=True,clear=False).create(target)
            python=target/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
            env=dict(os.environ)
            env['SETUPTOOLS_SCM_PRETEND_VERSION_FOR_RQALPHA']='0.0.0+snapshot.0d98adefa879'
            env['PYTHONUTF8']='1';env['PYTHONIOENCODING']='utf-8'
            subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check',str(archive)],check=True,env=env,timeout=900)
            subprocess.run([str(python),'-m','pip','check'],check=True,env=env,timeout=60)
            script="import importlib.util,json,sys;s=importlib.util.spec_from_file_location('w',sys.argv[1]);w=importlib.util.module_from_spec(s);s.loader.exec_module(w);print(json.dumps(w.verify_source(json.load(open(sys.argv[2],encoding='utf-8')))))"
            result=subprocess.run([str(python),'-I','-c',script,str(ROOT/'integrations/rqalpha/worker.py'),str(ROOT/'integrations/rqalpha/source-lock.json')],check=True,env=env,timeout=60,capture_output=True,text=True)
            identity=json.loads(result.stdout)
            freeze=subprocess.run([str(python),'-m','pip','freeze'],check=True,env=env,timeout=60,capture_output=True,text=True).stdout
            (target/'RQALPHA_LICENSE.txt').write_text(license_text,encoding='utf-8')
            (target/'requirements-observed.txt').write_text(freeze,encoding='utf-8')
            (target/'INSTALL_IDENTITY.json').write_text(json.dumps({'source_archive_sha256':ARCHIVE_SHA256,'engine':identity,'pip_check':'PASS','scope':'SYNTHETIC_ENGINE_VERIFICATION_ONLY'},indent=2),encoding='utf-8')
            print('Environment created and source identity verified: '+str(python))
            return 0
    except (ValueError,OSError,subprocess.SubprocessError,zipfile.BadZipFile) as exc:
        print('Setup failed: '+str(exc),file=sys.stderr)
        if target.exists():print('Partial environment retained for diagnosis; it is not marked ready.',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
