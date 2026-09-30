"""Real loopback HTTP tests for the new API; not browser-rendering evidence."""
import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import zipfile
from invest.server import InvestServer
from test_growth import fact_payload

class GrowthHTTPTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.s=InvestServer(('127.0.0.1',0),Path(self.tmp.name))
        self.thread=threading.Thread(target=self.s.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.s.server_port}'
        self.token=self.s.csrf_token;self.opener=build_opener(ProxyHandler({}))
    def tearDown(self):
        self.s.shutdown();self.thread.join(5);self.s.server_close();self.tmp.cleanup()
    def request(self,path,payload=None,headers=None):
        h={'Content-Type':'application/json','X-Invest-CSRF':self.token};h.update(headers or {})
        req=Request(self.base+path,data=json.dumps(payload).encode() if payload is not None else None,headers=h)
        try:r=self.opener.open(req,timeout=10)
        except HTTPError as e:r=e
        with r:
            b=r.read();return r.status,json.loads(b) if 'json' in r.headers.get('Content-Type','') else b
    def test_root_and_legacy_static_allowlist(self):
        code,html=self.request('/');self.assertEqual(code,200);self.assertIn(b'workbench.js',html)
        code,html=self.request('/legacy');self.assertEqual(code,200);self.assertIn(b'load-demo',html)
        for path in ['/workbench.css','/workbench.js']:self.assertEqual(self.request(path)[0],200)
        self.assertEqual(self.request('/../workspace.py')[0],404)
    def test_new_documents_inherit_host_origin_csrf_guards(self):
        for h in [{'Host':'bad.invalid'},{'Origin':'https://bad.invalid'},{'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.request('/api/workbench/documents?kind=review',headers=h)[0],403)
        self.assertEqual(self.request('/api/workbench/reviews',{},headers={'X-Invest-CSRF':'wrong'})[0],403)
        self.assertEqual(self.request('/api/workbench/documents?kind=review')[1]['documents'],[])
    def test_end_to_end_study_receipt_and_full_download(self):
        _,dataset=self.request('/api/datasets/demo',{})
        code,r=self.request('/api/workbench/receipt',{'dataset_id':dataset['id']});self.assertEqual(code,200,r)
        self.assertEqual(r['payload']['dataset_id'],dataset['id'])
        code,r=self.request('/api/workbench/study',{'dataset_id':dataset['id'],'specification':{'symbol':'600000.SH','cost_model_acknowledged':True}})
        self.assertEqual(code,200,r);self.assertEqual(r['payload']['summary']['succeeded'],18)
        self.assertEqual(self.request('/api/workbench/document?id='+r['id'])[1],r)
        self.assertEqual(len(self.request('/api/workbench/documents?kind=study')[1]['documents']),1)
    def test_concurrent_study_guard_and_recovery(self):
        _,dataset=self.request('/api/datasets/demo',{})
        self.s.study_lock.acquire()
        try:self.assertEqual(self.request('/api/workbench/study',{'dataset_id':dataset['id'],'specification':{}})[0],409)
        finally:self.s.study_lock.release()
        self.assertEqual(self.request('/api/workbench/study',{'dataset_id':dataset['id'],'specification':{}})[0],400)
        self.assertFalse(self.s.study_lock.locked())
    def test_walk_forward_study_persist_download_and_invalid_config_recovery(self):
        _,dataset=self.request('/api/datasets/demo',{})
        specification={'symbol':'600000.SH','cost_model_acknowledged':True,
                       'walk_forward':{'n_splits':3,'gap':5}}
        payload={'dataset_id':dataset['id'],'specification':specification}
        code,record=self.request('/api/workbench/study',payload)
        self.assertEqual(code,200,record)
        report=record['payload']
        self.assertEqual(report['protocol']['mode'],'EXPLORATORY_WALK_FORWARD')
        self.assertEqual(report['summary']['succeeded'],9)
        self.assertEqual(report['summary']['training_runs'],18)
        self.assertFalse(report['protocol']['frozen_holdout_opened'])
        self.assertEqual(self.request('/api/workbench/document?id='+record['id'])[1],record)
        self.assertEqual(self.request('/api/workbench/study',payload)[1]['id'],record['id'])
        specification['walk_forward']['gap']=-1
        self.assertEqual(self.request('/api/workbench/study',payload)[0],400)
        self.assertFalse(self.s.study_lock.locked())
        self.assertEqual(len(self.request('/api/workbench/documents?kind=study')[1]['documents']),1)
    def test_review_event_repeat_and_backup_tables(self):
        code,d=self.request('/api/workbench/reviews',{'name':'HTTP测试','initial_cash':'1000','client_key':'http','manual_record_acknowledged':True})
        self.assertEqual(code,200,d)
        event={'type':'DEPOSIT','occurred_at':'2024-01-02T16:00:00+08:00','source':'test','amount':'1'}
        p={'review_id':d['id'],'event_key':'one','event':event}
        for _ in range(2):
            code,r=self.request('/api/workbench/event',p);self.assertEqual(code,200,r)
        self.assertEqual(r['state']['cash'],'1001.00');self.assertEqual(len(r['events']),1)
        self.assertEqual(self.request('/api/private-backup',{})[0],400)
        code,raw=self.request('/api/private-backup',{'confirm_private_export':True});self.assertEqual(code,200)
        with zipfile.ZipFile(io.BytesIO(raw)) as z:self.assertIn('state.sqlite',z.namelist())
    def test_extension_on_off_and_source_bound_export(self):
        self.assertEqual(self.request('/api/workbench/facts',{'bundle':fact_payload(),'enabled':False})[0],400)
        code,r=self.request('/api/workbench/facts',{'bundle':fact_payload(),'enabled':True});self.assertEqual(code,200,r)
        q={'bundle_id':r['id'],'symbol':'600000.SH','as_of':'2024-04-01T16:00:00+08:00','enabled':True}
        self.assertEqual(self.request('/api/workbench/as-of',q)[1]['facts'][0]['value'],'10')
        q.update(enabled=False,bundle_id='nonexistent')
        self.assertTrue(self.request('/api/workbench/as-of',q)[1]['core_unaffected'])
    def test_status_does_not_claim_real_acceptance(self):
        code,r=self.request('/api/workbench/status');self.assertEqual(code,200)
        from invest import __version__
        self.assertEqual(r['version'],__version__)
        code,html=self.request('/');self.assertEqual(code,200)
        self.assertIn(b'id="app-version"',html);self.assertNotIn(b'0.2.0-rc1',html)
        self.assertEqual(len(r['stages']),5);self.assertFalse(r['broker_connected']);self.assertFalse(r['real_holdout_opened']);self.assertGreater(len(r['not_accepted']),0)
    def test_query_ambiguity_and_wrong_document_kind(self):
        self.assertEqual(self.request('/api/workbench/documents?kind=facts&kind=review')[0],400)
        self.assertEqual(self.request('/api/workbench/documents?kind=secret')[0],400)
        self.assertEqual(self.request('/api/workbench/document?id=x')[0],400)

if __name__=='__main__':unittest.main()
