"""Synthetic-only archive phase diagnostics; never substitutes for SDK tests.

Measures fresh-worker import, storage, output and exit under the unchanged
production timeout. Prints timing/status categories, never raw SDK exceptions,
environment values, filesystem paths, run IDs or study contents.
"""
from __future__ import annotations

from contextlib import closing
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import tempfile
import time

MARKER = "INVEST_ARCHIVE_PHASE "
CHILD = r'''
import contextlib,json,sys,time
started=time.monotonic()
def phase(name, **detail):
    print('INVEST_ARCHIVE_PHASE '+json.dumps({'name':name,'seconds':round(time.monotonic()-started,4),**detail}),file=sys.__stderr__,flush=True)
try:
    phase('process_start')
    sys.path.insert(0,sys.argv[1])
    from invest import mlflow_tracking as module
    phase('invest_imported')
    def deny(event,args):
        if event in {'socket.connect','socket.getaddrinfo','socket.sendto','socket.bind'}:
            raise RuntimeError('network disabled for synthetic archive profiling')
    sys.addaudithook(deny)
    with contextlib.redirect_stdout(sys.stderr):
        import mlflow
    phase('mlflow_imported')
    original=mlflow.MlflowClient
    class TimedClient:
        def __init__(self,*args,**kwargs):
            phase('client_begin')
            self.inner=original(*args,**kwargs)
            phase('client_ready')
        def __getattr__(self,name):
            target=getattr(self.inner,name)
            if not callable(target):
                return target
            def measured(*args,**kwargs):
                phase(name+'_begin')
                try:
                    return target(*args,**kwargs)
                except Exception as error:
                    phase(name+'_error',error_type=type(error).__name__)
                    raise
                finally:
                    phase(name+'_end')
            return measured
    mlflow.MlflowClient=TimedClient
    original_archive=module._archive_local
    def measured_archive(*args,**kwargs):
        phase('archive_begin')
        try:
            kwargs['progress']=lambda name: phase(name)
            return original_archive(*args,**kwargs)
        except Exception as error:
            phase('archive_error',error_type=type(error).__name__)
            raise
        finally:
            phase('archive_returned')
    module._archive_local=measured_archive
    module._worker_main(sys.argv[2])
    phase('worker_returned')
    sys.stdout.flush()
    phase('status_flushed')
except BaseException as error:
    phase('bootstrap_error',error_type=type(error).__name__)
    raise
'''


def safe_output(raw, stderr):
    """Extract only our bounded, non-sensitive diagnostic vocabulary."""
    phases = []
    for line in (stderr or b'').decode('utf-8', errors='replace').splitlines():
        if not line.startswith(MARKER):
            continue
        try:
            item = json.loads(line[len(MARKER):])
            if (set(item) - {'name', 'seconds', 'error_type'}
                    or not re.fullmatch(r'[a-z_]{1,80}', item['name'])
                    or type(item['seconds']) not in (int, float)
                    or not math.isfinite(item['seconds']) or item['seconds'] < 0):
                continue
            if 'error_type' in item and not re.fullmatch(r'[A-Za-z_]{1,80}', item['error_type']):
                continue
            phases.append(item)
        except (ValueError, KeyError, TypeError):
            continue
    try:
        status = json.loads(raw) if raw and len(raw) <= 4096 else {}
    except (ValueError, UnicodeError):
        status = {}
    return status if isinstance(status, dict) else {}, phases[:100]


def verify_committed(root, status, raw):
    run_id = status.get('run_id')
    if status.get('status') != 'archived' or not isinstance(run_id, str) or not re.fullmatch('[a-f0-9]{32}', run_id):
        return {'success_emitted': False}
    result = {'success_emitted': True, 'artifact_matches': False, 'database_finished': False}
    try:
        artifact = root/'mlflow'/'artifacts'/run_id/'artifacts'/'study.json'
        result['artifact_matches'] = artifact.read_bytes() == raw
        database = root/'mlflow'/'tracking.sqlite'
        with closing(sqlite3.connect(database.as_uri()+'?mode=ro', uri=True, timeout=2)) as connection:
            row = connection.execute('SELECT status FROM runs WHERE run_uuid=?', (run_id,)).fetchone()
            result['database_finished'] = row is not None and row[0] == 'FINISHED'
    except (OSError, sqlite3.Error):
        pass
    return result


def main():
    from invest.data import demo_dataset
    from invest.experiments import run_study
    from invest.mlflow_tracking import WORKER_TIMEOUT
    from invest.workspace import Workspace, canonical

    package_root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='invest-archive-profile-') as directory:
        root = Path(directory)
        record = Workspace(root/'state.sqlite').put('study', run_study(demo_dataset(), {
            'symbol': '600000.SH', 'cost_model_acknowledged': True}))
        raw = canonical(record).encode('utf-8')
        base_env = {key:value for key,value in os.environ.items() if not key.startswith('MLFLOW_')}
        base_env.update(MLFLOW_DISABLE_TELEMETRY='true', DO_NOT_TRACK='true', MLFLOW_ENABLE_ASYNC_LOGGING='false')
        for label, extra in [('inherited_threads', {}), ('one_numeric_thread', {
                'OPENBLAS_NUM_THREADS':'1', 'OMP_NUM_THREADS':'1', 'MKL_NUM_THREADS':'1'})]:
            destination = root/label
            started = time.monotonic()
            timeout, returncode = False, None
            try:
                result = subprocess.run([sys.executable, '-I', '-c', CHILD, str(package_root), str(destination)],
                    input=raw, capture_output=True, env={**base_env, **extra}, cwd=root,
                    timeout=WORKER_TIMEOUT, check=False)
                stdout, stderr, returncode = result.stdout, result.stderr, result.returncode
            except subprocess.TimeoutExpired as error:
                timeout, stdout, stderr = True, error.stdout or b'', error.stderr or b''
            status, phases = safe_output(stdout, stderr)
            reason = status.get('reason')
            if reason not in {None, 'archive_timeout', 'archive_busy', 'local_archive_unavailable',
                              'unsupported_mlflow_version', 'mlflow_extra_required', 'source_python_required'}:
                reason = 'unrecognized_reason'
            summary = {'profile':label, 'synthetic_only':True, 'deadline_seconds':WORKER_TIMEOUT,
                'elapsed_seconds':round(time.monotonic()-started,3), 'sqlite_version':sqlite3.sqlite_version, 'process_timeout':timeout,
                'returncode':returncode, 'worker_status':status.get('status') if status.get('status') in {'archived','failed'} else 'not_emitted',
                'worker_reason':reason, 'phases':phases,
                'committed_evidence':verify_committed(destination,status,raw)}
            print(json.dumps(summary, allow_nan=False), flush=True)
    # Diagnostic collection is not a pass/fail assertion. The unchanged real
    # SDK test step must still run and gate the workflow immediately afterward.
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
