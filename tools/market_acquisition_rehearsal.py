"""Rehearse acquisition with explicit artificial transport; no market access."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from integrations.market_evidence.acquisition import _collect, plan
from integrations.market_evidence.fixtures import fixture
from integrations.market_evidence.intake import canonical


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args(argv)
    args.output.mkdir(parents=True,exist_ok=False)
    results=[]
    secret='SYNTHETIC_CREDENTIAL_NOT_REAL_123456'
    with tempfile.TemporaryDirectory() as temp:
        root=Path(temp);fixture(root/'input')
        access=root/'test-access.txt'
        access.write_text('TEST ONLY: simulated scope evidence, not a real permission.',encoding='utf-8')
        for name in ['complete','permission_denied','network_interruption','calendar_gap','secret_reflection']:
            calls=[]
            def transport(body):
                request=json.loads(body);api=request['api_name'];calls.append(api)
                if name=='permission_denied':
                    return canonical({'code':2002,'msg':'artificial denied','data':None})
                if name=='network_interruption' and api=='adj_factor':
                    raise OSError('artificial outage')
                if name=='secret_reflection':
                    return canonical({'code':0,'msg':secret,'data':None})
                raw=(root/'input'/'raw'/(api+'.json')).read_bytes()
                if name=='calendar_gap' and api=='trade_cal':
                    data=json.loads(raw);data['data']['items'].pop();raw=canonical(data)
                return raw
            receipt=_collect(plan('600000.SH','2024-01-02','2024-01-08'),args.output/name,access,
                             access_declared=True,network_allowed=True,credential_reader=lambda:secret,
                             transport=transport,mode='TEST_TRANSPORT_NOT_REAL',pause=lambda _:None)
            expected={'complete':'CAPTURED_MAPPING_CHECKED','calendar_gap':'CAPTURED_WITH_DATA_BLOCKERS'}.get(name,'FAILED')
            assert receipt['status']==expected,(name,receipt['status'])
            assert not receipt['execution_authorized']
            results.append({'case':name,'expected':expected,'actual':receipt['status'],
                            'simulated_attempts':len(calls),'real_market_requests':0})
    for path in args.output.rglob('*'):
        if path.is_file():assert secret.encode() not in path.read_bytes(),path
    summary={'schema':'invest-acquisition-rehearsal-v1','mode':'SYNTHETIC_TRANSPORT_ONLY',
             'cases':results,'real_market_requests':0,'real_data_obtained':False,
             'access_verified':False,'credential_reflection_scan':'PASS'}
    (args.output/'SUMMARY.json').write_bytes(canonical(summary))
    print(json.dumps(summary,ensure_ascii=False))
    return 0


if __name__=='__main__':
    raise SystemExit(main())
