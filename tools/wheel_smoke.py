"""Smoke the installed wheel outside the checkout, without a browser/provider.

Usage: python tools/wheel_smoke.py /absolute/path/to/invest.whl (or wheel directory)
The active interpreter must already have Invest's core runtime dependencies.
The wheel is installed without network/dependency resolution into a fresh temp
directory; an isolated child process proves it does not import the checkout.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from zipfile import ZipFile

REQUIRED_ASSETS = frozenset({
    'invest/upstream_registry.json',
    'invest/web/index.html', 'invest/web/app.js', 'invest/web/app.css',
    'invest/web/workbench.html', 'invest/web/workbench.js', 'invest/web/workbench.css',
})

CHILD = r'''
import json
from pathlib import Path
import sys
import threading
from urllib.request import Request, build_opener, ProxyHandler

target = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(target))
import invest
from invest.server import InvestServer
from invest.upstreams import load_registry

assert Path(invest.__file__).resolve().is_relative_to(target), 'checkout import leaked into wheel test'
registry = load_registry()
assert len(registry['projects']) >= 30
server = InvestServer(('127.0.0.1', 0), Path(sys.argv[2]))
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
opener = build_opener(ProxyHandler({}))
base = f'http://127.0.0.1:{server.server_port}'

def request(path, payload=None):
    headers = {'Content-Type': 'application/json', 'X-Invest-CSRF': server.csrf_token}
    data = None if payload is None else json.dumps(payload).encode('utf-8')
    with opener.open(Request(base + path, data=data, headers=headers), timeout=20) as response:
        assert response.status == 200, (path, response.status)
        content = response.read()
        return json.loads(content) if 'json' in response.headers.get('Content-Type', '') else content

try:
    for path, marker in [('/', b'workbench.js'), ('/legacy', b'app.js'),
                         ('/workbench.js', b'study-form'), ('/workbench.css', b'{'),
                         ('/app.js', b'function'), ('/app.css', b'{')]:
        assert marker in request(path), f'packaged asset unavailable: {path}'
    dataset = request('/api/datasets/demo', {})
    assert dataset['meta']['source_kind'] == 'demo'
    saved = request('/api/workbench/study', {'dataset_id': dataset['id'], 'specification': {
        'symbol': '600000.SH', 'cost_model_acknowledged': True}})
    assert saved['payload']['summary']['succeeded'] == 18
    downloaded = request('/api/workbench/document?id=' + saved['id'])
    assert downloaded['id'] == saved['id'] and downloaded['payload'] == saved['payload']
    assert saved['payload']['protocol']['frozen_holdout_opened'] is False
    print(json.dumps({'installed_wheel_import': True, 'web_routes_checked': 6,
                      'registry_projects': len(registry['projects']), 'synthetic_studies': 1,
                      'replayed_comparisons': 18, 'saved_and_downloaded': True,
                      'real_provider_calls': 0}))
finally:
    server.shutdown()
    thread.join(10)
    server.server_close()
'''


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('wheel', type=Path)
    args = parser.parse_args(argv)
    wheel = args.wheel.resolve(strict=True)
    if wheel.is_dir():
        candidates = list(wheel.glob('invest-*.whl'))
        if len(candidates) != 1:
            parser.error('wheel directory must contain exactly one invest wheel')
        wheel = candidates[0]
    if wheel.suffix != '.whl':
        parser.error('expected a built wheel')
    with ZipFile(wheel) as archive:
        missing = REQUIRED_ASSETS - set(archive.namelist())
        if missing:
            raise ValueError('wheel is missing runtime assets: ' + ', '.join(sorted(missing)))
    with tempfile.TemporaryDirectory(prefix='invest-installed-wheel-') as directory:
        root = Path(directory)
        target = root / 'installed'
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--no-deps', '--no-index',
                        '--target', str(target), str(wheel)], check=True, timeout=90,
                       cwd=root, stdout=subprocess.DEVNULL)
        completed = subprocess.run([sys.executable, '-I', '-c', CHILD, str(target), str(root/'data')],
                                   timeout=90, cwd=root, text=True, capture_output=True)
        if completed.returncode:
            raise RuntimeError('isolated wheel smoke failed:\n' +
                               (completed.stdout + completed.stderr)[-16000:])
        report = json.loads(completed.stdout)
        print(json.dumps(report, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
