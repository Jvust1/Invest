"""Verify explicit ENG-03 source hashes and unchanged historical runtime modules."""
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    manifest=json.loads((ROOT/'governance/execution_contract_source_identity.json').read_text(encoding='utf-8'))
    failures=[];count=0
    for section in ('new_files','unchanged_legacy_files'):
        for name,expected in manifest[section].items():
            path=ROOT/name;count+=1
            actual=hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest() if path.is_file() else None
            if actual!=expected:failures.append({'path':name,'expected':expected,'actual':actual})
    print(json.dumps({'status':'FAIL' if failures else 'PASS','files_checked':count,'failures':failures},indent=2))
    return 1 if failures else 0

if __name__=='__main__':sys.exit(main())
