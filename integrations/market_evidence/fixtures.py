"""Clearly synthetic four-response fixtures. No public market observations."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path

from .intake import SCHEMA, canonical, sha, audit_bundle

AS_OF = '2024-01-10T12:00:00+08:00'


def put(root: Path, name: str, value) -> dict:
    raw = value if isinstance(value, bytes) else canonical(value)
    path = root/name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return {'path':name, 'sha256':sha(raw)}


def fixture(root: Path, *, complete: bool = False, candidate: bool = False) -> dict:
    """Create new fixtures only. Never call this with an existing input directory."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=False)
    m = dict(schema=SCHEMA,provider='tushare',origin='synthetic_fixture',symbol='600000.SH',
             start_date='2024-01-02',end_date='2024-01-08',captured_at='2024-01-09T12:00:00+08:00',
             raw={},license_review=None,market_facts=None,normalized_candidate=None)
    days = [('2024010'+str(i),i not in (6,7)) for i in range(2,9)]
    fields = {
        'daily':['ts_code','trade_date','open','high','low','close','vol'],
        'adj_factor':['ts_code','trade_date','adj_factor'],
        'stk_limit':['ts_code','trade_date','up_limit','down_limit'],
        'trade_cal':['exchange','cal_date','is_open'],
    }
    rows = {
        'daily':[[m['symbol'],d,'10.00','10.50','9.80','10.20','12.34'] for d,o in days if o],
        'adj_factor':[[m['symbol'],d,'1.0'] for d,o in days if o],
        'stk_limit':[[m['symbol'],d,'11.00','9.00'] for d,o in days if o],
        'trade_cal':[['SSE',d,'1' if o else '0'] for d,o in days],
    }
    for n in fields:
        m['raw'][n] = put(root,'raw/'+n+'.json',{'code':0,'msg':None,'data':{'fields':fields[n],'items':rows[n]}})
    if complete:
        desc = put(root,'evidence/synthetic-only.txt',b'SYNTHETIC TEST ARTIFACT. NOT A LICENSE, EXCHANGE RECORD OR REAL MARKET FACT.\n')
        m['license_review'] = {'artifact':desc,'provider':'tushare','symbol':m['symbol'],
            'data_start':m['start_date'],'data_end':m['end_date'],'valid_from':'2024-01-01',
            'valid_until':'2024-12-31','permitted_uses':['local_research'],
            'decision':'declared_authorized','reviewed_at':'2024-01-09T12:00:00+08:00'}
        f = {'schema':'invest-market-facts-v1','symbol':m['symbol'],'start_date':m['start_date'],
             'end_date':m['end_date'], 'evidence':{'fixture':{'artifact':desc,
                'source_url':'https://synthetic-source.invalid/not-real',
                'published_at':'2024-01-01T00:00:00+08:00','retrieved_at':'2024-01-09T12:00:00+08:00'}},
             'calendar':[{'date':d[:4]+'-'+d[4:6]+'-'+d[6:],'is_open':o,'evidence_id':'fixture'} for d,o in days],
             'sessions':[{'date':d[:4]+'-'+d[4:6]+'-'+d[6:],'suspended':False,'corporate_action':False,
                          'risk_warning':False,'evidence_id':'fixture'} for d,o in days if o],
             'rules':[{'effective_from':'2024-01-01','effective_to':'2024-01-31',
                       'tick_size':'0.01','buy_lot':100,'evidence_id':'fixture'}]}
        m['market_facts'] = put(root,'evidence/facts.json',f)
    put(root,'bundle.json',m)
    if candidate:
        result = audit_bundle(root,as_of=AS_OF)
        assert result['report']['integrity']=='RAW_MAPPING_CHECKED',result['report']
        m['normalized_candidate'] = put(root,'normalized/candidate.json',result['artifacts']['normalized.json'])
        put(root,'bundle.json',m)
    return deepcopy(m)
