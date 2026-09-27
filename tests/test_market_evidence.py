from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from invest.data import dataset_identity, fetch_tushare
from integrations.market_evidence import intake as i
from integrations.market_evidence.fixtures import AS_OF, fixture, put


class MarketEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)/'input'
        self.m = fixture(self.root,complete=True,candidate=True)

    def save(self):
        put(self.root,'bundle.json',self.m)

    def audit(self):
        self.save()
        return i.audit_bundle(self.root,as_of=AS_OF)

    def raw(self,n,mutator):
        obj = json.loads((self.root/self.m['raw'][n]['path']).read_bytes())
        mutator(obj)
        self.m['raw'][n] = put(self.root,'raw/'+n+'.json',obj)

    def fact(self,mutator):
        obj = json.loads((self.root/self.m['market_facts']['path']).read_bytes())
        mutator(obj)
        self.m['market_facts'] = put(self.root,'evidence/facts.json',obj)

    def candidate(self,mutator,*,rehash=True):
        obj = json.loads((self.root/self.m['normalized_candidate']['path']).read_bytes())
        mutator(obj)
        if rehash:
            obj['id'] = dataset_identity(obj)
        self.m['normalized_candidate'] = put(self.root,'normalized/candidate.json',obj)

    def code(self,code):
        r = self.audit()
        self.assertIn(code,[e['code'] for e in r['report']['issues']])
        self.assertFalse(r['report']['execution_authorized'])
        return r

    def test_complete_fixture_is_not_authorized(self):
        r = self.audit()['report']
        self.assertEqual(r['integrity'],'RAW_MAPPING_CHECKED')
        self.assertEqual(r['review_state'],'SYNTHETIC_FIXTURE_ONLY')
        self.assertEqual(r['candidate_comparison']['status'],'MATCH')
        self.assertEqual(r['license_review']['status'],'DECLARED_SCOPE_MATCH')
        self.assertEqual(r['market_facts']['status'],'CLAIM_STRUCTURE_CONSISTENT')
        self.assertFalse(r['execution_authorized'])
        self.assertFalse(r['holdout_opened'])
        self.assertFalse(r['independently_verified_source'])
        self.assertEqual(r['provider_calls_by_auditor'],0)

    def test_exact_volume_and_lineage(self):
        r = self.audit()
        ds = json.loads(r['artifacts']['normalized.json'])
        self.assertEqual(ds['bars'][0]['volume_shares'],1234)
        traces = r['report']['lineage'][0]
        self.assertEqual(traces['normalized_csv_line'],2)
        t = next(t for t in traces['fields'] if t['field']=='volume_shares')
        self.assertEqual(t['transform'],'decimal_times_100')
        self.assertEqual(t['raw_sha256'],self.m['raw']['daily']['sha256'])
        self.assertFalse(ds['audit']['backtest_ready'])
        self.assertIsNone(ds['bars'][0]['suspended'])
        self.assertIsNone(ds['bars'][0]['corporate_action'])

    def test_equivalent_existing_adapter_values(self):
        tables = {}
        for n,d in self.m['raw'].items():
            obj = json.loads((self.root/d['path']).read_bytes())['data']
            tables[n]=[dict(zip(obj['fields'],row)) for row in obj['items']]
        with patch('invest.data._api',side_effect=lambda n,*args:tables[n]):
            ds = fetch_tushare(self.m['symbol'],self.m['start_date'],self.m['end_date'],token='synthetic-test-only')
        self.m['normalized_candidate'] = put(self.root,'normalized/candidate.json',ds)
        self.assertEqual(self.audit()['report']['candidate_comparison']['status'],'MATCH')

    def test_repeated_output_and_report_identity(self):
        a,b=self.audit(),self.audit()
        self.assertEqual(a,b)
        r=deepcopy(a['report']);identifier=r.pop('report_id')
        self.assertEqual(identifier,i.sha(i.canonical(r)))

    def test_raw_bytes_not_rewritten(self):
        before={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.audit()
        after={p.relative_to(self.root):p.read_bytes() for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(before,after)

    def test_no_network(self):
        with patch('socket.socket',side_effect=AssertionError('network forbidden')):
            self.assertEqual(self.audit()['report']['integrity'],'RAW_MAPPING_CHECKED')

    def test_missing_license_is_separate_from_mapping(self):
        self.m['license_review']=None
        r=self.audit()['report']
        self.assertEqual(r['integrity'],'RAW_MAPPING_CHECKED')
        self.assertEqual(r['license_review']['status'],'MISSING')

    def test_expired_license(self):
        self.m['license_review']['valid_until']='2024-01-09'
        r=self.audit()['report']['license_review']
        self.assertEqual(r['status'],'SCOPE_NOT_SATISFIED')
        self.assertFalse(r['checks']['audit_date'])

    def test_license_scope_conflicts(self):
        original=deepcopy(self.m['license_review'])
        for field,value in [('provider','another'),('symbol','000001.SZ'),('data_end','2024-01-04'),
                            ('valid_from','2024-01-10'),('permitted_uses',[]),('decision','unknown'),('decision','denied')]:
            with self.subTest(field=field,value=value):
                self.m['license_review']=dict(original,**{field:value})
                self.assertEqual(self.audit()['report']['license_review']['status'],'SCOPE_NOT_SATISFIED')

    def test_missing_license_artifact(self):
        (self.root/self.m['license_review']['artifact']['path']).unlink()
        self.code('ARTIFACT_MISSING')

    def test_no_candidate_is_not_a_comparison_pass(self):
        self.m['normalized_candidate']=None
        self.assertEqual(self.audit()['report']['candidate_comparison']['status'],'NOT_SUPPLIED')

    def test_candidate_price_change_even_rehashed(self):
        self.candidate(lambda d:d['bars'][0].update(close=10.21))
        r=self.code('RAW_NORMALIZED_MISMATCH')['report']['candidate_comparison']
        self.assertIn('close',[e['field'] for e in r['differences']])

    def test_candidate_bad_hash(self):
        self.candidate(lambda d:d['bars'][0].update(close=10.21),rehash=False)
        self.code('CANDIDATE_IDENTITY_MISMATCH')

    def test_candidate_unit_change(self):
        self.candidate(lambda d:d['meta'].update(volume_unit='lot'))
        self.code('RAW_NORMALIZED_MISMATCH')

    def test_candidate_fills_unknown_flags(self):
        self.candidate(lambda d:d['bars'][0].update(suspended=False,corporate_action=False))
        r=self.code('RAW_NORMALIZED_MISMATCH')['report']['candidate_comparison']
        self.assertEqual({e['field'] for e in r['differences']},{'suspended','corporate_action'})

    def test_candidate_missing_and_extra_rows(self):
        self.candidate(lambda d:d['bars'].pop())
        self.code('RAW_NORMALIZED_MISMATCH')

    def test_candidate_duplicate_rows(self):
        self.candidate(lambda d:d['bars'].append(deepcopy(d['bars'][0])))
        self.code('CANDIDATE_DUPLICATE_BAR')

    def test_candidate_booleans_not_numbers(self):
        self.candidate(lambda d:d['bars'][0].update(adj_factor=True))
        self.code('RAW_NORMALIZED_MISMATCH')

    def test_candidate_calendar_mismatch(self):
        self.candidate(lambda d:d['calendar'].pop())
        self.code('RAW_NORMALIZED_MISMATCH')

    def test_raw_hash_mismatch(self):
        (self.root/'raw/daily.json').write_bytes(b'{}')
        self.code('ARTIFACT_HASH_MISMATCH')

    def test_raw_duplicate_json_key(self):
        self.m['raw']['daily']=put(self.root,'raw/daily.json',b'{"code":0,"code":0,"msg":null,"data":{}}')
        self.code('DUPLICATE_JSON_KEY')

    def test_raw_nonfinite(self):
        for raw in (b'{"x":NaN}',b'{"x":1e999}',b'{"x":Infinity}'):
            with self.subTest(raw=raw):
                self.m['raw']['daily']=put(self.root,'raw/daily.json',raw)
                self.assertEqual(self.audit()['report']['integrity'],'INVALID_INPUT')

    def test_no_secret_in_failure_output(self):
        self.m['raw']['daily']=put(self.root,'raw/daily.json',b'{"token":"do-not-leak-this-value"}')
        r=self.code('SENSITIVE_FIELD')
        self.assertNotIn('do-not-leak-this-value',json.dumps(r))

    def test_provider_failure_not_empty_success(self):
        self.raw('daily',lambda d:d.update(code=2002,msg='private-provider-message'))
        r=self.code('PROVIDER_REPORTED_FAILURE')
        self.assertNotIn('private-provider-message',json.dumps(r))
        self.assertFalse(r['artifacts'])

    def test_provider_boolean_status(self):
        self.raw('daily',lambda d:d.update(code=False))
        self.code('PROVIDER_CODE_TYPE')

    def test_truncation(self):
        self.raw('daily',lambda d:d['data'].update(has_more=True))
        self.code('TRUNCATED_RESPONSE')

    def test_duplicate_columns(self):
        self.raw('daily',lambda d:d['data']['fields'].append('open'))
        self.code('DUPLICATE_TABLE_FIELD')

    def test_missing_provider_field(self):
        self.raw('daily',lambda d:d['data']['fields'].remove('vol'))
        self.code('MISSING_PROVIDER_FIELD')

    def test_ragged_row(self):
        self.raw('daily',lambda d:d['data']['items'][0].pop())
        self.code('RAGGED_TABLE')

    def test_missing_price_start_and_end(self):
        original=json.loads((self.root/'raw/daily.json').read_bytes())
        for index in (0,-1):
            with self.subTest(index=index):
                obj=deepcopy(original);obj['data']['items'].pop(index)
                self.m['raw']['daily']=put(self.root,'raw/daily.json',obj)
                self.code('MISSING_SESSION_NOT_ASSUMED_SUSPENDED')

    def test_duplicate_provider_rows(self):
        self.raw('daily',lambda d:d['data']['items'].append(d['data']['items'][0]))
        self.code('DUPLICATE_PROVIDER_ROW')

    def test_wrong_security(self):
        self.raw('daily',lambda d:d['data']['items'][0].__setitem__(0,'000001.SZ'))
        self.code('SYMBOL_MISMATCH')

    def test_wrong_exchange(self):
        self.raw('trade_cal',lambda d:d['data']['items'][0].__setitem__(0,'SZSE'))
        self.code('EXCHANGE_MISMATCH')

    def test_closed_day_price(self):
        self.raw('trade_cal',lambda d:d['data']['items'][0].__setitem__(2,'0'))
        self.code('PRICE_ON_CLOSED_DAY')

    def test_calendar_natural_day_gap(self):
        self.raw('trade_cal',lambda d:d['data']['items'].pop(4))
        self.code('CALENDAR_NATURAL_DAY_GAP')

    def test_noninteger_volume_conversion(self):
        self.raw('daily',lambda d:d['data']['items'][0].__setitem__(6,'0.001'))
        self.code('VOLUME_NOT_INTEGER_SHARES')

    def test_subcent_price_rejected(self):
        self.raw('daily',lambda d:d['data']['items'][0].__setitem__(2,'10.001'))
        self.code('SUBCENT_PRICE_UNSUPPORTED')

    def test_missing_supplement(self):
        self.raw('adj_factor',lambda d:d['data']['items'].pop())
        self.code('SUPPLEMENT_MISSING_FOR_PRICE')

    def test_factor_change_is_not_no_action(self):
        self.raw('adj_factor',lambda d:d['data']['items'][-1].__setitem__(2,'1.1'))
        self.code('FACTOR_CHANGE_REQUIRES_ACTION_REVIEW')

    def test_float_precision_loss_rejected(self):
        self.raw('adj_factor',lambda d:d['data']['items'][0].__setitem__(2,'1.00000000000000001'))
        self.code('CORE_NUMERIC_REPRESENTATION_LOSS')

    def test_out_of_request_date(self):
        self.raw('daily',lambda d:d['data']['items'][0].__setitem__(1,'20240101'))
        self.code('ROW_OUT_OF_RANGE')

    def test_future_capture_and_wrong_time_zone(self):
        self.m['captured_at']='2024-01-11T00:00:00+08:00'
        self.code('CAPTURE_TIME_ORDER')
        self.m['captured_at']='2024-01-09T00:00:00'
        self.code('TIME_FORMAT')

    def test_equivalent_timezone_normalized(self):
        self.m['captured_at']='2024-01-09T04:00:00Z'
        self.assertEqual(self.audit()['report']['captured_at'],'2024-01-09T12:00:00+08:00')

    def test_unsafe_paths(self):
        original=deepcopy(self.m['raw']['daily'])
        for name in ('../a','/tmp/a','raw/../../a','C:/secret','raw\\daily.json','raw//daily.json','./raw/daily.json'):
            with self.subTest(name=name):
                self.m['raw']['daily']=dict(original,path=name)
                self.code('UNSAFE_PATH')

    def test_file_size_limit(self):
        with patch.object(i,'MAX_FILE',10):
            self.code('FILE_SIZE')

    def test_total_size_limit(self):
        with patch.object(i,'MAX_TOTAL',20):
            self.code('BUNDLE_SIZE')

    def test_missing_facts(self):
        self.m['market_facts']=None
        self.assertEqual(self.audit()['report']['market_facts']['status'],'MISSING')

    def test_fact_evidence_missing(self):
        self.fact(lambda f:f['sessions'][0].update(evidence_id='absent'))
        self.code('EVIDENCE_REF_MISSING')

    def test_fact_scope_mismatch(self):
        self.fact(lambda f:f.update(symbol='000001.SZ'))
        self.code('FACT_SCOPE_MISMATCH')

    def test_fact_calendar_conflict(self):
        self.fact(lambda f:f['calendar'][0].update(is_open=False))
        self.assertIn('EXTERNAL_CALENDAR_DISAGREES_OR_INCOMPLETE',[e['code'] for e in self.audit()['report']['market_facts']['issues']])

    def test_fact_unknown_kept_unknown(self):
        self.fact(lambda f:f['sessions'][0].update(suspended=None))
        self.assertIn('FACT_UNKNOWN',[e['code'] for e in self.audit()['report']['market_facts']['issues']])

    def test_suspension_conflict(self):
        self.fact(lambda f:f['sessions'][0].update(suspended=True))
        self.assertIn('SUSPENSION_VOLUME_CONFLICT',[e['code'] for e in self.audit()['report']['market_facts']['issues']])

    def test_corporate_action_unsupported(self):
        self.fact(lambda f:f['sessions'][0].update(corporate_action=True))
        self.assertIn('CORPORATE_ACTION_UNSUPPORTED',[e['code'] for e in self.audit()['report']['market_facts']['issues']])

    def test_rule_gaps(self):
        self.fact(lambda f:f['rules'].clear())
        self.assertIn('RULE_COVERAGE_GAP',[e['code'] for e in self.audit()['report']['market_facts']['issues']])

    def test_rule_overlaps(self):
        self.fact(lambda f:f['rules'].append(deepcopy(f['rules'][0])))
        self.assertIn('RULE_COVERAGE_OVERLAP',[e['code'] for e in self.audit()['report']['market_facts']['issues']])

    def test_late_evidence_not_pit_verified(self):
        self.fact(lambda f:f['evidence']['fixture'].update(published_at='2024-01-03T12:00:00+08:00'))
        self.assertIn('FACT_NOT_KNOWN_AT_DECLARED_CUTOFF',[e['code'] for e in self.audit()['report']['market_facts']['issues']])

    def test_evidence_url_cannot_embed_secret(self):
        self.fact(lambda f:f['evidence']['fixture'].update(source_url='https://host.invalid/a?token=hidden'))
        r=self.code('EVIDENCE_URL')
        self.assertNotIn('hidden',json.dumps(r))

    def test_claimed_provider_origin_still_not_authorization(self):
        self.m['origin']='provider_export'
        r=self.audit()['report']
        self.assertEqual(r['review_state'],'AWAITING_INDEPENDENT_REVIEW')
        self.assertFalse(r['execution_authorized'])
        self.assertFalse(r['license_review']['independently_verified'])
        self.assertFalse(r['market_facts']['independently_verified'])

    def test_unhashed_audit_ready_claim_cannot_pass(self):
        self.candidate(lambda d:d['audit'].update(backtest_ready=True))
        self.code('RAW_NORMALIZED_MISMATCH')

    def test_early_same_day_capture(self):
        self.m['captured_at']='2024-01-08T12:00:00+08:00'
        self.code('CAPTURE_BEFORE_DECLARED_EOD_CUTOFF')

    def test_incomplete_bundle_marker(self):
        (self.root/'.incomplete').write_text('interrupted',encoding='utf-8')
        self.code('INCOMPLETE_BUNDLE')

    def test_assemble_preserves_raw_and_never_grants_rights(self):
        output=Path(self.tmp.name)/'assembled'
        i.assemble_exports(self.root/'raw',output,symbol=self.m['symbol'],start_date=self.m['start_date'],
                           end_date=self.m['end_date'],captured_at=self.m['captured_at'])
        for n in i.REQUIRED:
            self.assertEqual((self.root/'raw'/(n+'.json')).read_bytes(),(output/'raw'/(n+'.json')).read_bytes())
        r=i.audit_bundle(output,as_of=AS_OF)['report']
        self.assertEqual(r['integrity'],'RAW_MAPPING_CHECKED')
        self.assertEqual(r['review_state'],'EVIDENCE_INCOMPLETE')
        self.assertEqual(r['license_review']['status'],'MISSING')
        self.assertFalse(r['execution_authorized'])

    def test_html_escapes_all_record_content(self):
        from integrations.market_evidence.report import html_report
        r=self.audit()['report']
        r['issues'].append({'code':'<script>alert(1)</script>','date':'<img onerror=x>'})
        text=html_report(r)
        self.assertNotIn('<script>',text)
        self.assertIn('&lt;script&gt;',text)

    def test_output_refuses_overwrite(self):
        from integrations.market_evidence.report import write_report
        out=Path(self.tmp.name)/'report'
        r=self.audit()
        write_report(r,out,input_root=self.root)
        before=(out/'report.json').read_bytes()
        with self.assertRaisesRegex(i.IntakeError,'OUTPUT_EXISTS'):
            write_report(r,out,input_root=self.root)
        self.assertEqual(before,(out/'report.json').read_bytes())

    def test_output_refuses_input_subtree(self):
        from integrations.market_evidence.report import write_report
        with self.assertRaisesRegex(i.IntakeError,'OUTPUT_INSIDE_INPUT'):
            write_report(self.audit(),self.root/'reports',input_root=self.root)
        self.assertFalse((self.root/'reports').exists())

    def test_output_checksums_and_evidence_not_copied(self):
        from integrations.market_evidence.report import write_report
        out=Path(self.tmp.name)/'report'
        write_report(self.audit(),out,input_root=self.root)
        sums=json.loads((out/'SHA256SUMS.json').read_bytes())
        self.assertEqual(set(sums),{p.name for p in out.iterdir()}-{'SHA256SUMS.json'})
        for name,item in sums.items():
            raw=(out/name).read_bytes()
            self.assertEqual(item,{'sha256':i.sha(raw),'bytes':len(raw)})
        self.assertFalse((out/'raw').exists())
        self.assertFalse((out/'evidence').exists())
        self.assertFalse((out/'.incomplete').exists())

    def test_cli_exit_does_not_mean_permission(self):
        import subprocess,sys
        out=Path(self.tmp.name)/'cli'
        proc=subprocess.run([sys.executable,str(Path(__file__).resolve().parents[1]/'tools/market_evidence.py'),
            'audit','--input',str(self.root),'--output',str(out),'--as-of',AS_OF],capture_output=True,text=True)
        self.assertEqual(proc.returncode,0,proc.stderr)
        self.assertFalse(json.loads(proc.stdout)['execution_authorized'])
