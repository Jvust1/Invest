"""Verify copied source against the locally tested candidate; never rewrite it."""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
manifest = json.loads((ROOT/'governance/growth_source_identity.json').read_text(encoding='utf-8'))
failed = []
for name, expected in manifest['files'].items():
    path = ROOT/name
    actual = hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() if path.is_file() else None
    if actual != expected:
        failed.append({'path':name,'expected':expected,'actual':actual})
print(json.dumps({'status':'FAIL' if failed else 'PASS','checked_files':len(manifest['files']),'mismatches':failed},indent=2))
sys.exit(1 if failed else 0)
