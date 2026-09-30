"""Read-only verification of additive engine-lab sources, with LF normalization."""
import hashlib
import json
from pathlib import Path


def main():
    root=Path(__file__).resolve().parents[1]
    manifest=json.loads((root/'governance/engine_lab_source_identity.json').read_text(encoding='utf-8'))
    failures=[]
    for name,expected in manifest['files'].items():
        path=root/name
        actual=hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() if path.is_file() else None
        if actual!=expected:failures.append({'path':name,'expected':expected,'actual':actual})
    print(json.dumps({'status':'FAIL' if failures else 'PASS','files_checked':len(manifest['files']),'failures':failures},indent=2))
    return 1 if failures else 0


if __name__=='__main__':raise SystemExit(main())
