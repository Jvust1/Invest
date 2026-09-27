"""All transports here are artificial; never access a credential or market API."""
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import getpass
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from integrations.market_evidence import acquisition as a
from integrations.market_evidence.fixtures import fixture
from integrations.market_evidence.intake import canonical, strict_json
from tools import collect_market_data as cli

SENTINEL = 'LOCAL_TEST_SECRET_0123456789'


class AcquisitionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.fixture = self.root/'fixture'
        fixture(self.fixture)
        self.evidence = self.root/'test-access.txt'
        self.evidence.write_text('TEST ONLY: simulated user scope evidence, not actual permission.', encoding='utf-8')
        self.spec = a.plan('600000.SH','2024-01-02','2024-01-08')
        self.output = self.root/'capture'
        self.reader = Mock(return_value=SENTINEL)
        self.requests = []

    def transport(self, raw):
        request = json.loads(raw)
        self.requests.append(request)
        self.assertEqual(request['token'], SENTINEL)
        return (self.fixture/'raw'/(request['api_name']+'.json')).read_bytes()

    def run_collection(self, **overrides):
        values = dict(access_declared=True,network_allowed=True,credential_reader=self.reader,
                      transport=self.transport,mode='TEST_TRANSPORT_NOT_REAL',pause=lambda _:None)
        values.update(overrides)
        return a._collect(self.spec,self.output,self.evidence,**values)

    def assert_no_secret(self):
        if self.output.exists():
            for p in self.output.rglob('*'):
                if p.is_file():
                    self.assertNotIn(SENTINEL.encode(),p.read_bytes(),str(p))

    def test_plan_has_four_bounded_requests(self):
        self.assertEqual(len(self.spec['requests']),4)
        self.assertEqual(self.spec['max_requests'],4)
        self.assertEqual(self.spec['automatic_retries'],0)
        self.assertEqual(self.spec['endpoint'],'https://api.tushare.pro/')
        self.assertFalse(self.spec['execution_authorized'])
        self.assertNotIn('token',json.dumps(self.spec))

    def test_calendar_has_no_open_day_filter(self):
        self.assertEqual(self.spec['requests'][3]['params'],
                         {'exchange':'SSE','start_date':'20240102','end_date':'20240108'})

    def test_shenzhen_exchange_is_explicit(self):
        p=a.plan('000001.SZ','2024-01-02','2024-01-08')
        self.assertEqual(p['requests'][3]['params']['exchange'],'SZSE')

    def test_unsupported_symbol(self):
        for s in (None,'AAPL','600000','600000.SH,000001.SZ','688001.SH'):
            with self.subTest(s=s),self.assertRaises(a.AcquisitionError):
                a.plan(s,'2024-01-02','2024-01-08')

    def test_current_day_and_future_rejected(self):
        for end in (a.now().date().isoformat(),(a.now().date()+a.timedelta(days=1)).isoformat()):
            with self.subTest(end=end),self.assertRaisesRegex(a.AcquisitionError,'CLOSED_HISTORY'):
                a.plan('600000.SH',end,end)

    def test_range_limit_and_reversed(self):
        for start,end in [('2023-01-01','2024-02-01'),('2024-02-01','2024-01-01')]:
            with self.subTest(start=start),self.assertRaisesRegex(a.AcquisitionError,'SAMPLE_RANGE'):
                a.plan('600000.SH',start,end)

    def test_malformed_dates_rejected(self):
        for d in ('2024-02-30','20240101','bad',None):
            with self.subTest(d=d),self.assertRaises(a.AcquisitionError):
                a.plan('600000.SH',d,'2024-01-08')

    def test_no_access_no_credential_no_files(self):
        with self.assertRaisesRegex(a.AcquisitionError,'ACCESS_CONFIRMATION'):
            self.run_collection(access_declared=False)
        self.reader.assert_not_called();self.assertFalse(self.output.exists())

    def test_no_network_no_credential_no_files(self):
        with self.assertRaisesRegex(a.AcquisitionError,'NETWORK_CONFIRMATION'):
            self.run_collection(network_allowed=False)
        self.reader.assert_not_called();self.assertFalse(self.output.exists())

    def test_missing_evidence_before_credential(self):
        self.evidence.unlink()
        with self.assertRaisesRegex(a.AcquisitionError,'LOCAL_EVIDENCE_REQUIRED'):
            self.run_collection()
        self.reader.assert_not_called()

    def test_empty_evidence_before_credential(self):
        self.evidence.write_bytes(b'')
        with self.assertRaisesRegex(a.AcquisitionError,'LOCAL_EVIDENCE_SIZE'):
            self.run_collection()
        self.reader.assert_not_called()

    def test_known_synthetic_license_rejected(self):
        self.evidence.write_bytes(b'SYNTHETIC TEST ARTIFACT. NOT A LICENSE.')
        with self.assertRaisesRegex(a.AcquisitionError,'TEST_EVIDENCE_FORBIDDEN'):
            self.run_collection()
        self.reader.assert_not_called()

    def test_existing_output_untouched(self):
        self.output.mkdir();(self.output/'keep').write_bytes(b'private-old-data')
        with self.assertRaisesRegex(a.AcquisitionError,'OUTPUT_EXISTS'):
            self.run_collection()
        self.assertEqual((self.output/'keep').read_bytes(),b'private-old-data')
        self.reader.assert_not_called()

    def test_parent_must_exist(self):
        self.output=self.root/'absent'/'capture'
        with self.assertRaisesRegex(a.AcquisitionError,'OUTPUT_PARENT_REQUIRED'):
            self.run_collection()
        self.reader.assert_not_called()

    def test_plan_cannot_change_endpoint(self):
        self.spec['endpoint']='https://attacker.invalid/'
        with self.assertRaisesRegex(a.AcquisitionError,'PLAN_CHANGED'):
            self.run_collection()
        self.reader.assert_not_called()

    def test_plan_cannot_add_interface(self):
        self.spec['requests'].append({'api_name':'arbitrary'})
        with self.assertRaisesRegex(a.AcquisitionError,'PLAN_CHANGED'):
            self.run_collection()
        self.reader.assert_not_called()

    def test_invalid_credential_does_not_create_files(self):
        for value in ('short',None,'a'*300,'x'*20+'\n'):
            with self.subTest(value=type(value).__name__),self.assertRaises(a.AcquisitionError):
                self.run_collection(credential_reader=lambda:value)
        self.assertFalse(self.output.exists())

    def test_four_saved_originals_audited_and_no_secret(self):
        receipt=self.run_collection()
        self.assertEqual(receipt['status'],'CAPTURED_MAPPING_CHECKED')
        self.assertEqual(len(receipt['attempts']),4)
        self.assertFalse((self.output/'.incomplete').exists())
        for api in a.REQUIRED:
            self.assertEqual((self.output/'raw'/(api+'.json')).read_bytes(),
                             (self.fixture/'raw'/(api+'.json')).read_bytes())
        self.assertTrue((self.output/'review'/'index.html').exists())
        self.assertEqual(receipt['review_state'],'SYNTHETIC_FIXTURE_ONLY')
        self.assertFalse(receipt['execution_authorized'])
        self.assert_no_secret()

    def test_test_seam_never_claims_provider_origin(self):
        self.run_collection()
        m=strict_json((self.output/'bundle'/'bundle.json').read_bytes())
        self.assertEqual(m['origin'],'synthetic_fixture')
        self.assertIsNone(m['license_review'])
        self.assertIsNone(m['market_facts'])

    def test_receipt_identity_and_per_request_time(self):
        receipt=self.run_collection()
        on_disk=json.loads((self.output/'collection.json').read_bytes())
        identifier=on_disk.pop('receipt_id')
        self.assertEqual(identifier,a.sha(canonical(on_disk)))
        for request in receipt['attempts']:
            self.assertLessEqual(request['started_at'],request['finished_at'])
            self.assertTrue(request['finished_at'].endswith('+08:00'))

    def test_runtime_source_identity_is_nonempty(self):
        identity=a.implementation_identity()
        self.assertEqual(len(identity['files']),5)
        self.assertEqual(identity['sha256'],a.sha(canonical(identity['files'])))
        self.assertEqual(self.run_collection()['implementation'],identity)

    def test_network_failure_keeps_prior_response_not_bundle(self):
        def fail(raw):
            if len(self.requests)==1: raise OSError(SENTINEL)
            return self.transport(raw)
        receipt=self.run_collection(transport=fail)
        self.assertEqual(receipt['status'],'FAILED')
        self.assertEqual(len(receipt['attempts']),2)
        self.assertEqual(len(list((self.output/'raw').iterdir())),1)
        self.assertTrue((self.output/'.incomplete').exists())
        self.assertFalse((self.output/'bundle').exists())
        self.assert_no_secret()

    def test_access_rejection_saves_no_provider_message(self):
        raw=canonical({'code':2002,'msg':'permission denied','data':None})
        receipt=self.run_collection(transport=lambda _:raw)
        self.assertEqual(receipt['attempts'][0]['error_code'],'PROVIDER_ACCESS_REJECTED')
        self.assertEqual(len(receipt['attempts']),1)
        self.assertEqual(list((self.output/'raw').iterdir()),[])
        self.assertNotIn(b'permission denied',(self.output/'collection.json').read_bytes())

    def test_provider_failure_never_retried(self):
        t=Mock(return_value=canonical({'code':-2001,'msg':'error','data':None}))
        receipt=self.run_collection(transport=t)
        self.assertEqual(t.call_count,1)
        self.assertEqual(receipt['attempts'][0]['error_code'],'PROVIDER_REPORTED_FAILURE')

    def test_reflected_secret_in_raw_rejected(self):
        receipt=self.run_collection(transport=lambda _:canonical({'code':0,'msg':SENTINEL,'data':None}))
        self.assertEqual(receipt['attempts'][0]['error_code'],'SENSITIVE_RESPONSE_REJECTED')
        self.assert_no_secret()

    def test_escaped_reflected_secret_rejected(self):
        escaped=''.join('\\u%04x'%ord(c) for c in SENTINEL)
        raw=(' {"code":0,"msg":"'+escaped+'","data":null}').encode()
        self.assertNotIn(SENTINEL.encode(),raw)
        receipt=self.run_collection(transport=lambda _:raw)
        self.assertEqual(receipt['attempts'][0]['error_code'],'SENSITIVE_RESPONSE_REJECTED')
        self.assert_no_secret()

    def test_sensitive_fields_duplicate_keys_nonfinite_rejected(self):
        bad=[b'{"code":0,"token":"hidden"}',b'{"code":0,"code":0}',
             b'{"code":0,"data":NaN}',b'not json']
        for i,raw in enumerate(bad):
            with self.subTest(i=i):
                self.output=self.root/f'bad-{i}'
                result=self.run_collection(transport=lambda _:raw)
                self.assertEqual(result['status'],'FAILED')
                self.assertEqual(list((self.output/'raw').iterdir()),[])

    def test_oversized_and_empty_response_rejected(self):
        for i,raw in enumerate([b'',b'x'*(a.MAX_FILE+1)]):
            self.output=self.root/f'size-{i}'
            r=self.run_collection(transport=lambda _:raw)
            self.assertEqual(r['attempts'][0]['error_code'],'RESPONSE_SIZE')

    def test_missing_field_and_has_more_fail_closed(self):
        for kind in ('field','more'):
            self.output=self.root/kind
            payload=json.loads((self.fixture/'raw'/'daily.json').read_bytes())
            if kind=='field':payload['data']['fields'][2]='unknown'
            else:payload['data']['has_more']=True
            r=self.run_collection(transport=lambda _:canonical(payload))
            self.assertEqual(r['status'],'FAILED')

    def test_extra_field_rejected(self):
        p=json.loads((self.fixture/'raw'/'daily.json').read_bytes())
        p['data']['fields'].append('unrequested')
        for row in p['data']['items']:row.append('value')
        r=self.run_collection(transport=lambda _:canonical(p))
        self.assertEqual(r['attempts'][0]['error_code'],'UNREQUESTED_FIELDS')

    def test_calendar_gap_preserved_as_blocker(self):
        def gap(raw):
            data=self.transport(raw)
            if self.requests[-1]['api_name']=='trade_cal':
                p=json.loads(data);p['data']['items'].pop();data=canonical(p)
            return data
        r=self.run_collection(transport=gap)
        self.assertEqual(r['status'],'CAPTURED_WITH_DATA_BLOCKERS')
        self.assertFalse(r['execution_authorized'])
        self.assertTrue((self.output/'review'/'report.json').exists())

    def test_wrong_symbol_blocked_without_rewriting(self):
        def wrong(raw):
            data=self.transport(raw)
            if self.requests[-1]['api_name']=='daily':
                p=json.loads(data);p['data']['items'][0][0]='000001.SZ';data=canonical(p)
            return data
        r=self.run_collection(transport=wrong)
        self.assertEqual(r['status'],'CAPTURED_WITH_DATA_BLOCKERS')
        self.assertIn(b'000001.SZ',(self.output/'raw'/'daily.json').read_bytes())

    def test_interruption_is_not_success(self):
        def stop(_): raise KeyboardInterrupt()
        r=self.run_collection(transport=stop)
        self.assertEqual(r['error_code'],'INTERRUPTED')
        self.assertTrue((self.output/'.incomplete').exists())

    def test_no_plaintext_or_redirect_following(self):
        conn=Mock();conn.getresponse.return_value.status=302
        with patch.object(a.http.client,'HTTPSConnection',return_value=conn) as factory:
            with self.assertRaisesRegex(a.AcquisitionError,'HTTP_STATUS_REJECTED'):
                a.https_post(b'{}')
            self.assertEqual(factory.call_count,1)
            self.assertEqual(factory.call_args.args,('api.tushare.pro',443))
        conn.close.assert_called_once()

    def test_tls_failure_sanitized(self):
        conn=Mock();conn.request.side_effect=OSError(SENTINEL)
        with patch.object(a.http.client,'HTTPSConnection',return_value=conn):
            with self.assertRaisesRegex(a.AcquisitionError,'TLS_OR_NETWORK_ERROR') as e:
                a.https_post(b'{}')
        self.assertNotIn(SENTINEL,str(e.exception));conn.close.assert_called_once()

    def test_http_transport_enforces_type_size_and_length(self):
        for headers,raw,expected in [
            ({'Content-Type':'text/html'},b'{}','RESPONSE_CONTENT_TYPE'),
            ({'Content-Type':'application/json','Content-Encoding':'gzip'},b'{}','RESPONSE_ENCODING_REJECTED'),
            ({'Content-Type':'application/json','Content-Length':'999999999'},b'{}','RESPONSE_SIZE'),
            ({'Content-Type':'application/json','Content-Length':'5'},b'{}','RESPONSE_TRUNCATED')]:
            with self.subTest(expected=expected):
                conn=Mock();resp=conn.getresponse.return_value;resp.status=200
                resp.getheader.side_effect=lambda key,default=None:headers.get(key,default)
                resp.read.return_value=raw
                with patch.object(a.http.client,'HTTPSConnection',return_value=conn):
                    with self.assertRaisesRegex(a.AcquisitionError,expected):a.https_post(b'{}')

    def test_http_transport_success_does_not_change_bytes(self):
        conn=Mock();resp=conn.getresponse.return_value;resp.status=200
        headers={'Content-Type':'application/json; charset=utf-8','Content-Length':'3'}
        resp.getheader.side_effect=lambda key,default=None:headers.get(key,default)
        resp.read.return_value=b'{}\n'
        with patch.object(a.http.client,'HTTPSConnection',return_value=conn):
            self.assertEqual(a.https_post(b'{}'),b'{}\n')
        resp.read.assert_called_once_with(a.MAX_FILE+1)

    def test_credential_from_env_is_not_written(self):
        with patch.dict(os.environ,{'TUSHARE_TOKEN':SENTINEL}),patch.object(a.getpass,'getpass') as prompt:
            self.assertEqual(a.read_credential(),SENTINEL);prompt.assert_not_called()

    def test_hidden_input_fallback_disabled(self):
        with patch.dict(os.environ,{},clear=True),patch.object(a.getpass,'getpass',side_effect=getpass.GetPassWarning('hidden unavailable')):
            with self.assertRaisesRegex(a.AcquisitionError,'HIDDEN_INPUT_UNAVAILABLE'):
                a.read_credential()

    def test_cli_plan_does_not_collect(self):
        with patch.object(cli,'collect') as collect,redirect_stdout(io.StringIO()):
            code=cli.main(['plan','--symbol','600000.SH','--start-date','2024-01-02','--end-date','2024-01-08'])
        self.assertEqual(code,0);collect.assert_not_called()

    def test_cli_accidental_secret_argument_is_not_echoed(self):
        err=io.StringIO()
        with redirect_stderr(err),self.assertRaises(SystemExit):
            cli.main(['plan','--token',SENTINEL])
        self.assertNotIn(SENTINEL,err.getvalue())

    def test_cli_missing_consent_has_no_credential_read(self):
        with patch.object(a,'read_credential') as reader,redirect_stderr(io.StringIO()),redirect_stdout(io.StringIO()):
            code=cli.main(['collect','--symbol','600000.SH','--start-date','2024-01-02','--end-date','2024-01-08',
                           '--output',str(self.output),'--evidence',str(self.evidence)])
        self.assertEqual(code,2);reader.assert_not_called()

    def test_wizard_cancelled_before_access(self):
        answers=['600000.SH','2024-01-02','2024-01-08',str(self.evidence),str(self.output),'NO']
        with patch('builtins.input',side_effect=answers),patch.object(cli,'collect') as collect,redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(['wizard']),1)
        collect.assert_not_called()

    def test_import_has_no_network_and_no_prompt(self):
        root=Path(__file__).resolve().parents[1]
        script="import socket,getpass; socket.socket=lambda *a,**k: (_ for _ in ()).throw(AssertionError('network')); getpass.getpass=lambda *a,**k: (_ for _ in ()).throw(AssertionError('prompt')); import integrations.market_evidence.acquisition; import tools.collect_market_data"
        r=subprocess.run([sys.executable,'-c',script],cwd=root,capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)


if __name__=='__main__':
    unittest.main()
