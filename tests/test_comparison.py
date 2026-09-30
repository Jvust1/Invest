"""Core contract tests use a labelled transport fixture, never pretend it is RQAlpha."""
from copy import deepcopy
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from invest import comparison as c
from invest.comparison_scenarios import synthetic_dataset, costs, order, scenarios
from invest.data import dataset_identity

ROOT=Path(__file__).resolve().parents[1]


def simple_case():
    return c.prepare_case(synthetic_dataset(),'600000.SH',[order('buy',1,'BUY'),order('sell',2,'SELL')],costs())


def transport_fixture(case):
    """NOT an engine: a copy for structural tampering tests only."""
    value=c.run_invest(case)
    value.update(engine='rqalpha',network_attempts=0,real_provider_calls=0,
                 identity=dict(commit=c.RQ_COMMIT,source_verification='EXACT_NORMALIZED_PYTHON_FILES',
                               source_identity=c.RQ_SOURCE_IDENTITY,python_files=151))
    return value


class CaseContractTests(unittest.TestCase):
    def setUp(self): self.data=synthetic_dataset();self.orders=[order('b',1,'BUY')]
    def prepare(self,data=None,orders=None,p=None):
        return c.prepare_case(data or self.data,'600000.SH',self.orders if orders is None else orders,p or costs())
    def test_normalized_input_is_immutable(self):
        before=deepcopy(self.data);case=self.prepare();c.run_invest(case)
        self.assertEqual(before,self.data);c.validate_case(case)
    def test_rejects_real_source_even_with_valid_identity(self):
        self.data['meta']['source_kind']='akshare';self.data['id']=dataset_identity(self.data)
        with self.assertRaisesRegex(ValueError,'合成'): self.prepare()
    def test_stale_dataset_identity(self):
        self.data['bars'][1]['close']=11
        with self.assertRaises(ValueError):self.prepare()
    def test_empty_orders_never_pass(self):
        with self.assertRaises(ValueError):self.prepare(orders=[])
    def test_order_fields_do_not_accept_reference_fills(self):
        self.orders[0]['fill_price']=10
        with self.assertRaises(ValueError):self.prepare()
    def test_duplicate_ids(self):
        with self.assertRaises(ValueError):self.prepare(orders=self.orders*2)
    def test_future_and_same_day_signals(self):
        for day in ['2025-01-07','2025-01-08']:
            with self.subTest(day=day),self.assertRaises(ValueError):self.prepare(orders=[dict(self.orders[0],signal_date=day)])
    def test_missing_calendar_sessions(self):
        self.data['calendar'].pop(2);self.data['id']=dataset_identity(self.data)
        with self.assertRaises(ValueError):self.prepare()
    def test_order_dates_cannot_target_warmup_or_absent_day(self):
        for day in ['2025-01-06','2025-01-11']:
            with self.subTest(day=day),self.assertRaises(ValueError):self.prepare(orders=[dict(self.orders[0],date=day)])
    def test_order_time_must_be_monotone(self):
        with self.assertRaises(ValueError):self.prepare(orders=[order('b',2,'BUY'),order('c',1,'BUY')])
    def test_control_chars_and_html_in_ids(self):
        for key in ['bad\n','<script>','空',1,'a'*65]:
            with self.subTest(key=key),self.assertRaises(ValueError):self.prepare(orders=[dict(self.orders[0],id=key)])
    def test_quantity_and_side_types(self):
        for update in [dict(quantity=True),dict(quantity=100.0),dict(quantity=0),dict(quantity=10**7+100),dict(quantity=99),dict(side=[]),dict(side='SHORT')]:
            with self.subTest(update=update),self.assertRaises(ValueError):self.prepare(orders=[dict(self.orders[0],**update)])
    def test_per_day_capacity(self):
        with self.assertRaises(ValueError):self.prepare(orders=[order(f'o{i}',1,'BUY') for i in range(11)])
    def test_unknown_cost_parameter(self):
        with self.assertRaises(ValueError):self.prepare(p=costs(holdout_open=True))
    def test_explicit_cost_acknowledgement(self):
        with self.assertRaises(ValueError):self.prepare(p=costs(cost_model_acknowledged=False))
    def test_nonfinite_costs(self):
        for value in [float('nan'),float('inf'),True]:
            with self.subTest(value=value),self.assertRaises(ValueError):self.prepare(p=costs(commission_rate=value))
    def test_company_actions_and_factors(self):
        for field,value in [('corporate_action',True),('adj_factor',2),('volume_shares',100.0)]:
            data=synthetic_dataset();data['bars'][1][field]=value;data['id']=dataset_identity(data)
            with self.subTest(field=field),self.assertRaises(ValueError):self.prepare(data=data)
    def test_case_revalidated_before_execution(self):
        case=self.prepare();case['purpose']='REAL_TRADING'
        with self.assertRaises(ValueError):c.run_invest(case)
        with patch.object(c.subprocess,'run') as run,self.assertRaises(ValueError):
            c.run_rqalpha(case,python_executable=sys.executable,license_acknowledged=True)
        run.assert_not_called()
    def test_transported_unknown_fields_rejected(self):
        case=self.prepare();case['expected_fills']=[]
        with self.assertRaises(ValueError):c.validate_case(case)
    def test_all_declared_scenarios_have_unique_nonempty_identity(self):
        xs=scenarios();self.assertEqual(len(xs),24)
        self.assertEqual(len({x['name'] for x in xs}),24)
        self.assertEqual(sum(x['expected_status']=='DIVERGED' for x in xs),6)
        for x in xs:c.validate_case(x['case'])


class OutputContractTests(unittest.TestCase):
    def setUp(self):self.case=simple_case();self.result=transport_fixture(self.case)
    def validate(self,result=None):c.validate_result(self.case,self.result if result is None else result,'rqalpha')
    def test_transport_fixture_validates_but_is_not_integration_evidence(self): self.validate()
    def test_case_hash_mismatch(self):
        self.result['case_id']='0'*64
        with self.assertRaises(ValueError):self.validate()
    def test_missing_and_duplicate_valuations(self):
        for change in ['missing','duplicate','wrong_type']:
            d=deepcopy(self.result)
            if change=='missing':d['curve'].pop()
            elif change=='duplicate':d['curve'][1]=d['curve'][0]
            else:d['curve'][0]=None
            with self.subTest(change=change),self.assertRaises(ValueError):self.validate(d)
    def test_missing_or_malformed_orders(self):
        for value in [None,[],[None],self.result['orders']*2]:
            d=dict(self.result,orders=value)
            with self.subTest(value=value),self.assertRaises(ValueError):self.validate(d)
    def test_nonfinite_or_missing_money(self):
        for value in [None,True,float('nan'),float('inf'),'10000']:
            d=deepcopy(self.result);d['curve'][0]['cash']=value
            with self.subTest(value=value),self.assertRaises(ValueError):self.validate(d)
        del self.result['curve'][0]['cash']
        with self.assertRaises(ValueError):self.validate()
    def test_tampered_intermediate_cash_not_hidden_by_correct_final_nav(self):
        self.result['curve'][0]['cash']+=1
        with self.assertRaisesRegex(ValueError,'现金持仓'):self.validate()
    def test_tampered_nav(self):
        self.result['curve'][0]['equity']+=1
        with self.assertRaisesRegex(ValueError,'净值'):self.validate()
    def test_shares_boolean_invalid(self):
        self.result['curve'][0]['shares']=True
        with self.assertRaises(ValueError):self.validate()
    def test_status_requires_consistent_quantity(self):
        self.result['orders'][0]['status']='PARTIAL'
        with self.assertRaises(ValueError):self.validate()
    def test_negative_fees(self):
        self.result['orders'][0]['fills'][0]['fees']=-1
        with self.assertRaises(ValueError):self.validate()
    def test_fee_sum_not_just_final_net(self):
        self.result['orders'][0]['fills'][0]['commission']=1
        with self.assertRaises(ValueError):self.validate()
    def test_trade_list_cannot_omit_order_fills(self):
        self.result['trades']=[]
        with self.assertRaises(ValueError):self.validate()
    def test_required_source_identity_and_network_boundary(self):
        for mutation in ['commit','source_identity','python_files','network_attempts','real_provider_calls']:
            d=deepcopy(self.result)
            if mutation in d['identity']:d['identity'][mutation]=0
            else:d[mutation]=1
            with self.subTest(mutation=mutation),self.assertRaises(ValueError):self.validate(d)
    def test_false_is_not_zero_network_evidence(self):
        self.result['network_attempts']=False
        with self.assertRaises(ValueError):self.validate()
    def test_no_silent_empty_comparison(self):
        with self.assertRaises(ValueError):c.compare_results(self.case,{}, {})
    def test_html_escapes_report_text(self):
        report=c.compare_results(self.case,c.run_invest(self.case),self.result)
        report['limitations'].append('<script>alert(1)</script>')
        text=c.render_html(report)
        self.assertIn('&lt;script&gt;',text);self.assertNotIn('<script>',text)


class IsolationTests(unittest.TestCase):
    def setUp(self):self.case=simple_case()
    def test_license_ack_required(self):
        with patch.object(c.subprocess,'run') as run,self.assertRaises(ValueError):
            c.run_rqalpha(self.case,python_executable=sys.executable,license_acknowledged=False)
        run.assert_not_called()
    def test_python_must_be_absolute_existing_file(self):
        for path in ['python','/not-existing-python',None]:
            with self.subTest(path=path),self.assertRaises(ValueError):
                c.run_rqalpha(self.case,python_executable=path,license_acknowledged=True)
    def test_timeout_validation(self):
        for timeout in [0,181,True,1.5]:
            with self.subTest(timeout=timeout),self.assertRaises(ValueError):
                c.run_rqalpha(self.case,python_executable=sys.executable,license_acknowledged=True,timeout=timeout)
    def test_missing_source_lock(self):
        with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):
            c.run_rqalpha(self.case,python_executable=sys.executable,license_acknowledged=True,root=Path(tmp))
    def test_changed_source_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'integrations/rqalpha';path.mkdir(parents=True)
            (path/'source-lock.json').write_text('{"commit":"'+c.RQ_COMMIT+'","python_files":{}}')
            with self.assertRaises(ValueError):c.run_rqalpha(self.case,python_executable=sys.executable,license_acknowledged=True,root=Path(tmp))
    def test_timeout_does_not_accept_partial_output(self):
        with patch.object(c.subprocess,'run',side_effect=subprocess.TimeoutExpired('test',1)),self.assertRaisesRegex(ValueError,'超时'):
            c.run_rqalpha(self.case,python_executable=sys.executable,license_acknowledged=True)
    def test_subprocess_arguments_and_environment_exclude_private_tokens(self):
        def fake_run(args,**kwargs):
            self.assertEqual(args[1],'-I');self.assertTrue(Path(args[2]).is_absolute())
            self.assertNotIn('INVEST_SECRET',kwargs['env']);self.assertNotIn('PYTHONPATH',kwargs['env'])
            payload=json.loads(kwargs['input']);self.assertEqual(set(payload),{'case','source_lock','license_acknowledged'})
            self.assertNotIn('trades',payload['case']);self.assertFalse(kwargs.get('shell',False))
            kwargs['stdout'].write(b'{"ok":false,"error":"TEST_ONLY"}')
            return subprocess.CompletedProcess(args,2)
        with patch.dict(c.os.environ,INVEST_SECRET='not-a-real-secret',PYTHONPATH='injected'),patch.object(c.subprocess,'run',side_effect=fake_run),self.assertRaisesRegex(ValueError,'TEST_ONLY'):
            c.run_rqalpha(self.case,python_executable=sys.executable,license_acknowledged=True)
    def test_transport_non_object_and_bad_json(self):
        for raw in [b'[]',b'bad json']:
            def fake(args,**kw):
                kw['stdout'].write(raw);return subprocess.CompletedProcess(args,0)
            with self.subTest(raw=raw),patch.object(c.subprocess,'run',side_effect=fake),self.assertRaises(ValueError):
                c.run_rqalpha(self.case,python_executable=sys.executable,license_acknowledged=True)
    def test_worker_import_has_no_execution_side_effects(self):
        spec=importlib.util.spec_from_file_location('comparison_worker_test',ROOT/'integrations/rqalpha/worker.py')
        mod=importlib.util.module_from_spec(spec)
        before='rqalpha' in sys.modules;spec.loader.exec_module(mod)
        self.assertEqual('rqalpha' in sys.modules,before);mod.validate_case(self.case)
        self.assertEqual(mod.SOURCE_IDENTITY,c.RQ_SOURCE_IDENTITY)
    def test_worker_checks_transport_without_invest_import(self):
        spec=importlib.util.spec_from_file_location('comparison_worker_validate',ROOT/'integrations/rqalpha/worker.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        for field,value in [('orders',[]),('currency','USD'),('purpose','REAL_TRADING'),('symbol','300001.SZ')]:
            d=deepcopy(self.case);d[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):mod.validate_case(d)
    def test_worker_network_hook_denies_connection_and_dns(self):
        spec=importlib.util.spec_from_file_location('comparison_worker_network',ROOT/'integrations/rqalpha/worker.py')
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
        for event in ['socket.connect','socket.getaddrinfo','socket.sendto']:
            with self.assertRaisesRegex(RuntimeError,'OUTBOUND_NETWORK_DISABLED'):mod.deny_network(event,())
        self.assertEqual(len(mod.NETWORK_ATTEMPTS),3)
        mod.deny_network('open',())


class LabDeliveryTests(unittest.TestCase):
    @staticmethod
    def module(name):
        spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/(name+'.py'))
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
    def test_tools_are_import_safe(self):
        with patch.object(subprocess,'run') as run:
            for name in ['run_engine_lab','setup_engine_lab','verify_engine_lab_browser']:self.module(name)
        run.assert_not_called()
    def test_existing_report_directory_never_overwritten(self):
        mod=self.module('run_engine_lab')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'precious.txt';p.write_text('keep')
            with patch.object(mod,'run_rqalpha') as run,self.assertRaises(ValueError):mod.run_suite(sys.executable,tmp)
            self.assertEqual(p.read_text(),'keep');run.assert_not_called()
    def test_invalid_scenario_creates_no_directory(self):
        mod=self.module('run_engine_lab')
        with tempfile.TemporaryDirectory() as tmp:
            output=Path(tmp)/'new'
            with self.assertRaises(ValueError):mod.run_suite(sys.executable,output,'unknown')
            self.assertFalse(output.exists())
    def test_errors_are_retained_and_suite_fails(self):
        mod=self.module('run_engine_lab')
        with tempfile.TemporaryDirectory() as tmp,patch.object(mod,'run_rqalpha',side_effect=ValueError('unit-test-only failure')),patch.object(mod,'probe_network',return_value={'blocked':True}):
            output=Path(tmp)/'new';result=mod.run_suite(sys.executable,output,'round_trip')
            self.assertEqual(result['status'],'FAIL');self.assertEqual(result['counts']['errors'],1)
            self.assertIn('unit-test-only failure',(output/'cases/round_trip.error.json').read_text())
            manifest=json.loads((output/'SHA256SUMS.json').read_text());self.assertIn('summary.json',manifest)
    def test_wrong_archive_rejected_before_install(self):
        mod=self.module('setup_engine_lab')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.zip';p.write_bytes(b'not the pinned source')
            with self.assertRaisesRegex(ValueError,'SHA256'):mod.verify_archive(p)
    def test_protocol_checks_refuse_empty_agreement(self):
        mod=self.module('run_engine_lab');definition=scenarios()[0];case=definition['case']
        # Two internally consistent copies that both reject every order still fail hand targets.
        left=c.run_invest(case);right=transport_fixture(case)
        for r in [left,right]:
            for row in r['orders']:row.update(filled_quantity=0,status='REJECTED',fills=[])
            r['trades']=[]
            for point in r['curve']:point.update(cash=10000,equity=10000,shares=0)
        report=c.compare_results(case,left,right)
        self.assertEqual(report['status'],'MATCH')
        checks=mod.outcome('round_trip',report,definition);self.assertFalse(all(checks.values()))
