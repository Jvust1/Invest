"""Executable G1–G5 capability evidence. All fixtures are synthetic/manual."""
import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from invest.backup import export_backup, restore_backup
from invest.data import demo_dataset, dataset_identity, parse_csv, FIELDS
from invest.engine import backtest, execute_order
from invest.experiments import audit_receipt, replay_ledger, run_study
from invest.fundamentals import as_of, validate_bundle
from invest.review import append_event, create_review, replay, snapshot
from invest.workspace import Workspace, canonical, digest

HEADER=','.join(FIELDS)+'\n'
ROW='600000.SH,2024-01-02,10,11,9,10.5,12300,false,12,8,1,false\n'
CAL='date\n2024-01-02\n'

def csvparse(raw=HEADER+ROW,calendar=CAL,source='人工合成测试'):
    return parse_csv(raw,source=source,calendar_csv=calendar)

def fact_payload():
    base={'symbol':'600000.SH','metric':'profit','period_end':'2023-12-31','unit':'CNY','revision':1,'value':'10','available_at':'2024-03-01T16:00:00+08:00'}
    return {'source_name':'合成测试','source_text':'虚构财务数据','license_note':'人工合成，不含真实数据',
            'facts':[base,dict(base,revision=2,value='8',available_at='2024-05-01T16:00:00+08:00')]}

class G1Tests(unittest.TestCase):
    def test_receipt_identity_and_missing_evidence_visible(self):
        x=demo_dataset();r=audit_receipt(x)
        self.assertEqual(r['dataset_id'],x['id'])
        self.assertFalse(r['license_independently_verified'])
        self.assertIsNone(r['original_sha256'])
        self.assertEqual(r['license_note'],'UNKNOWN')
        self.assertEqual(r['execution_windows'][0]['status'],'PASS')
        self.assertEqual(r,audit_receipt(demo_dataset()))
    def test_raw_hash_not_truth_proof(self):
        r=audit_receipt(demo_dataset(),{'raw_text':'not market data','license_note':'UNKNOWN'})
        self.assertEqual(r['original_sha256'],hashlib.sha256(b'not market data').hexdigest())
        self.assertFalse(r['original_matches_dataset_verified'])
    def test_receipt_forged_dataset_fails(self):
        x=demo_dataset();x['bars'][0]['close']+=1
        with self.assertRaises(ValueError):audit_receipt(x)
    def test_audit_recomputed_when_cached_audit_claims_pass(self):
        x=csvparse(raw=','.join(FIELDS[:7])+'\n'+','.join(ROW.split(',')[:7])+'\n')
        x['audit']={'errors':[],'warnings':[],'backtest_ready':True,'backtest_blockers':[]}
        self.assertEqual(audit_receipt(x)['execution_windows'][0]['status'],'BLOCKED')

# Count each independent malformed input as a real unittest, not an inflated prose count.
def make_boundary(field,value):
    def test(self):
        pieces=ROW.strip().split(',');pieces[FIELDS.index(field)]=value
        try:r=csvparse(HEADER+','.join(pieces)+'\n')
        except ValueError:return
        self.assertFalse(r['audit']['backtest_ready'],(field,value))
    return test
for label,field,value in [
 ('nonfinite_open','open','NaN'),('infinite_close','close','Infinity'),('negative_low','low','-1'),
 ('subcent_price','open','10.001'),('invalid_high','high','8'),('fractional_volume','volume_shares','1.1'),
 ('negative_volume','volume_shares','-1'),('boolean_volume','volume_shares','true'),
 ('zero_factor','adj_factor','0'),('tiny_factor','adj_factor','1e-999'),
 ('ambiguous_suspension','suspended','0'),('missing_suspension','suspended',''),
 ('ambiguous_action','corporate_action','0'),('missing_action','corporate_action',''),
 ('action_present','corporate_action','true'),('missing_limit','up_limit',''),
 ('high_above_limit','up_limit','10'),('low_below_limit','down_limit','10'),
 ('wrong_exchange','symbol','600000.SZ'),('etf_not_stock','symbol','510300.SH'),
 ('invalid_date','date','2024-02-30'),('unparsed_timestamp','date','2024-01-02T08:00:00'),
 ('missing_factor','adj_factor',''),('suspended_with_volume','suspended','true')]:
    setattr(G1Tests,'test_boundary_'+label,make_boundary(field,value))

class ManualArithmeticTests(unittest.TestCase):pass
# Independently specified expected cash after one 100-share fill at 10.00.
MANUAL=[('buy_zero','BUY',{},'9000.00'),('sell_zero','SELL',{},'11000.00'),
 ('buy_min','BUY',{'min_commission':5},'8995.00'),('sell_min','SELL',{'min_commission':5},'10995.00'),
 ('buy_pct','BUY',{'commission_rate':0.01},'8990.00'),('sell_pct','SELL',{'commission_rate':0.01},'10990.00'),
 ('sell_tax','SELL',{'stamp_tax_rate':0.001},'10999.00'),('buy_not_sell_tax','BUY',{'stamp_tax_rate':0.001},'9000.00'),
 ('buy_transfer','BUY',{'transfer_fee_rate':0.001},'8999.00'),('sell_components','SELL',{'min_commission':5,'transfer_fee_rate':0.00001,'stamp_tax_rate':0.0005},'10994.49')]
def make_manual(side,changes,expected):
    def test(self):
        bar=csvparse()['bars'][0]
        params={'cost_model_acknowledged':True,'commission_rate':0,'min_commission':0,
                'transfer_fee_rate':0,'stamp_tax_rate':0,'slippage_bps':0,**changes}
        r=execute_order(bar,side,100,Decimal('10000.00'),100,params)
        self.assertEqual(r['cash_after'],Decimal(expected));self.assertEqual(r['gross'],Decimal('1000.00'))
    return test
for name,side,p,expected in MANUAL:setattr(ManualArithmeticTests,'test_'+name,make_manual(side,p,expected))

class G2Tests(unittest.TestCase):
    def test_complete_bounded_study_and_same_window(self):
        d=demo_dataset();a=run_study(d,{'symbol':'600000.SH','cost_model_acknowledged':True})
        b=run_study(d,{'symbol':'600000.SH','cost_model_acknowledged':True})
        self.assertEqual(a,b);self.assertEqual(a['summary']['planned'],18)
        self.assertEqual(a['summary']['failed'],0);self.assertFalse(a['protocol']['frozen_holdout_opened'])
        for period in a['protocol']['periods']:
            rows=[r['result'] for r in a['results'] if r['period']==period['name']]
            self.assertEqual({r['evaluation_start'] for r in rows},{period['start']})
            self.assertEqual({r['evaluation_end'] for r in rows},{period['end']})
    def test_unknown_execution_keeps_all_failures(self):
        d=demo_dataset()
        for row in d['bars']:row['suspended']=None
        d['id']=dataset_identity(d)
        r=run_study(d,{'symbol':'600000.SH','cost_model_acknowledged':True})
        self.assertEqual(r['summary']['failed'],18)
        self.assertTrue(all(x.get('reason') for x in r['results']))
    def test_input_budgets_and_acknowledgment(self):
        d=demo_dataset()
        for spec in [{},{'symbol':'600000.SH','cost_model_acknowledged':False},
                     {'symbol':'600000.SH','cost_model_acknowledged':True,'candidates':[]},
                     {'symbol':'600000.SH','cost_model_acknowledged':True,'holdout_open':True}]:
            with self.subTest(spec=spec),self.assertRaises(ValueError):run_study(d,spec)
    def test_replay_detects_changed_fee_and_curve(self):
        d=demo_dataset();r=backtest(d,{'symbol':'600000.SH','cost_model_acknowledged':True})
        self.assertEqual(replay_ledger(d,r)['status'],'PASS')
        for field in ['curve','trades','benchmark_trades']:
            altered=copy.deepcopy(r)
            altered[field][0]['equity' if field=='curve' else 'fees']+=.01
            with self.subTest(field=field),self.assertRaises(ValueError):replay_ledger(d,altered)
    def test_source_fingerprint_mismatch_rejected(self):
        d=demo_dataset();r=backtest(d,{'symbol':'600000.SH','cost_model_acknowledged':True})
        r['dataset_id']='0'*64
        with self.assertRaises(ValueError):replay_ledger(d,r)

# 16 future-perturbation tests at independent cutoffs. Only future bars change.
def make_causality(cut):
    def test(self):
        d=demo_dataset();days=d['calendar'];last=days[cut]
        p={'symbol':'600000.SH','fast':3,'slow':10,'end_date':last,'cost_model_acknowledged':True}
        r=backtest(d,p)
        changed=copy.deepcopy(d)
        for row in changed['bars']:
            if row['date']>last:
                for key in ('open','high','low','close','up_limit','down_limit'):row[key]=round(row[key]*2,2)
        changed['id']=dataset_identity(changed)
        other=backtest(changed,p)
        for key in ('metrics','curve','trades','rejected_orders','benchmark_trades'):
            self.assertEqual(r[key],other[key],key)
    return test
for cutoff in range(35,115,5):setattr(G2Tests,f'test_future_perturbation_cutoff_{cutoff}',make_causality(cutoff))

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.path=Path(self.temp.name)/'state.sqlite';self.w=Workspace(self.path)
    def tearDown(self):self.temp.cleanup()
    def test_dedup_and_reopen(self):
        a=self.w.put('receipt',{'x':1});b=self.w.put('receipt',{'x':1})
        self.assertEqual(a,b);self.assertEqual(len(self.w.list('receipt')),1)
        self.assertEqual(Workspace(self.path).get(a['id']),a)
    def test_tamper_detection_and_immutable_trigger(self):
        d=self.w.put('receipt',{'x':1})
        with self.w.connection() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM growth_documents')
            db.execute('DROP TRIGGER growth_docs_no_update')
            db.execute('UPDATE growth_documents SET payload=? WHERE id=?',('{"x":2}',d['id']))
        with self.assertRaises(ValueError):self.w.get(d['id'])
    def test_nonfinite_rejected(self):
        with self.assertRaises(ValueError):self.w.put('receipt',{'x':float('nan')})
    def test_wrong_kind_rejected(self):
        d=self.w.put('receipt',{'x':1})
        with self.assertRaises(ValueError):self.w.get(d['id'],'review')
    def test_roundtrip_backup_all_new_tables(self):
        d=self.w.put('facts',validate_bundle(fact_payload()))
        r=create_review(self.w,{'name':'测试','initial_cash':'1000','client_key':'one','manual_record_acknowledged':True})
        append_event(self.w,r['id'],'e1',{'type':'DEPOSIT','occurred_at':'2024-01-02T16:00:00+08:00','source':'test','amount':'100'})
        zipdata=export_backup(Path(self.temp.name));dest=Path(self.temp.name)/'restored'
        restore_backup(zipdata,dest);w=Workspace(dest/'state.sqlite')
        self.assertEqual(w.get(d['id']),d)
        self.assertEqual(snapshot(w,r['id']),snapshot(self.w,r['id']))
        with self.assertRaises(ValueError):restore_backup(zipdata,dest)

class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.w=Workspace(Path(self.temp.name)/'state.sqlite')
        self.doc=create_review(self.w,{'name':'手算','initial_cash':'10000','client_key':'one','manual_record_acknowledged':True})
        self.key=self.doc['id'];self.count=0
    def tearDown(self):self.temp.cleanup()
    def add(self,kind,day=2,**fields):
        self.count+=1
        return append_event(self.w,self.key,str(self.count),{'type':kind,'occurred_at':f'2024-01-{day:02d}T16:00:00+08:00','source':'人工合成手算',**fields})
    def state(self):return snapshot(self.w,self.key)['state']
    def test_cash_flow_not_profit(self):
        self.add('DEPOSIT',amount='1000');self.add('WITHDRAWAL',amount='500')
        s=self.state();self.assertEqual(s['cash'],'10500.00');self.assertEqual(s['profit_on_last_marks'],'0.00');self.assertEqual(s['time_weighted_return'],0)
    def test_buy_dividend_fee_marks_and_flow_manual_scenario(self):
        self.add('BUY',symbol='600000.SH',quantity=100,price='10',fee='5')
        self.assertIsNone(self.state()['net_assets_on_last_marks'])
        self.add('MARK',prices={'600000.SH':'10'})
        self.add('DIVIDEND',amount='10',symbol='600000.SH')
        self.add('FEE',amount='2')
        self.add('MARK',prices={'600000.SH':'11'})
        s=self.state();self.assertEqual(s['cash'],'9003.00');self.assertEqual(s['profit_on_last_marks'],'103.00')
        self.assertAlmostEqual(s['time_weighted_return'],.0103)
        self.add('DEPOSIT',amount='1010.30')
        self.assertAlmostEqual(self.state()['time_weighted_return'],.0103)
        self.assertEqual(self.state()['profit_on_last_marks'],'103.00')
    def test_sell_t1_and_fee_scenario(self):
        self.add('BUY',symbol='600000.SH',quantity=100,price='10',fee='0')
        with self.assertRaises(ValueError):self.add('SELL',symbol='600000.SH',quantity=100,price='11',fee='5')
        self.add('SELL',day=3,symbol='600000.SH',quantity=100,price='11',fee='5')
        self.assertEqual(self.state()['cash'],'10095.00')
        self.assertAlmostEqual(self.state()['time_weighted_return'],.0095)
    def test_idempotent_conflict_and_concurrent_retries(self):
        raw={'type':'DEPOSIT','occurred_at':'2024-01-02T16:00:00+08:00','source':'test','amount':'1'}
        with ThreadPoolExecutor(max_workers=6) as pool:records=list(pool.map(lambda _:append_event(self.w,self.key,'same',raw),range(12)))
        self.assertEqual(len({x['hash'] for x in records}),1);self.assertEqual(self.state()['cash'],'10001.00')
        with self.assertRaises(ValueError):append_event(self.w,self.key,'same',dict(raw,amount='2'))
    def test_no_overdraft_concurrent(self):
        def attempt(i):
            try:append_event(self.w,self.key,str(i),{'type':'WITHDRAWAL','occurred_at':'2024-01-02T16:00:00+08:00','source':'test','amount':'6000'});return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(attempt,[1,2]))
        self.assertEqual(sum(result),1);self.assertEqual(self.state()['cash'],'4000.00')
    def test_future_information_decision_rejected(self):
        with self.assertRaises(ValueError):self.add('DECISION',reason='future',evidence_at='2024-01-03T16:00:00+08:00')
    def test_missing_marks_block_flow_and_not_invent_valuation(self):
        self.add('BUY',symbol='600000.SH',quantity=100,price='10',fee='0')
        with self.assertRaises(ValueError):self.add('DEPOSIT',amount='10')
        self.assertIsNone(self.state()['time_weighted_return'])
    def test_stale_mark_blocks_new_day_flow(self):
        self.add('BUY',symbol='600000.SH',quantity=100,price='10',fee='0');self.add('MARK',prices={'600000.SH':'10'})
        with self.assertRaises(ValueError):self.add('DEPOSIT',day=3,amount='10')
        self.assertIn('24',','.join(self.state()['warnings']))
    def test_time_order_and_future_event_rejected(self):
        self.add('DEPOSIT',day=3,amount='10')
        with self.assertRaises(ValueError):self.add('DEPOSIT',day=2,amount='10')
        raw={'type':'DEPOSIT','occurred_at':(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),'source':'test','amount':'1'}
        with self.assertRaises(ValueError):append_event(self.w,self.key,'future',raw)
    def test_hash_chain_tampering(self):
        self.add('FEE',amount='1')
        with self.w.connection() as db:
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM growth_events')
            db.execute('DROP TRIGGER growth_events_no_update')
            db.execute('UPDATE growth_events SET previous_hash=?',('f'*64,))
        with self.assertRaises(ValueError):self.state()
    def test_failure_and_retry_do_not_move_cash(self):
        self.add('FAILURE',reason='来源超时');self.add('RETRY',reason='保留失败记录，人工重试')
        self.assertEqual(self.state()['cash'],'10000.00');self.assertEqual(self.state()['event_count'],2)
    def test_selling_unknown_holding_and_dividend_rejected(self):
        with self.assertRaises(ValueError):self.add('SELL',symbol='600000.SH',quantity=100,price='10',fee='0')
        with self.assertRaises(ValueError):self.add('DIVIDEND',symbol='600000.SH',amount='10')
    def test_negative_nonfinite_fractional_and_boolean_inputs(self):
        for v in [-1,True,'NaN','Infinity','.001']:
            with self.subTest(v=v),self.assertRaises(ValueError):self.add('DEPOSIT',amount=v)
    def test_extra_secret_field_rejected(self):
        with self.assertRaises(ValueError):self.add('DEPOSIT',amount='1',broker_token='do-not-store')
    def test_no_naive_times(self):
        with self.assertRaises(ValueError):append_event(self.w,self.key,'x',{'type':'DEPOSIT','occurred_at':'2024-01-01','source':'test','amount':'1'})
    def test_incomplete_and_extra_marks_rejected(self):
        self.add('BUY',symbol='600000.SH',quantity=100,price='10',fee='0')
        for prices in [{},{'600000.SH':'10','000001.SZ':'20'}]:
            with self.subTest(prices=prices),self.assertRaises(ValueError):self.add('MARK',prices=prices)
    def test_drawdown_adjusts_for_flow(self):
        self.add('FEE',amount='1000');self.add('DEPOSIT',amount='900')
        s=self.state();self.assertAlmostEqual(s['time_weighted_return'],-.1);self.assertAlmostEqual(s['max_drawdown_on_observed_nav'],.1)

class PITTests(unittest.TestCase):
    def test_revision_asof_and_disabled_isolation(self):
        b=validate_bundle(fact_payload())
        self.assertEqual(as_of(b,'600000.SH','2024-02-01T16:00:00+08:00',enabled=True)['facts'],[])
        self.assertEqual(as_of(b,'600000.SH','2024-04-01T16:00:00+08:00',enabled=True)['facts'][0]['value'],'10')
        self.assertEqual(as_of(b,'600000.SH','2024-06-01T16:00:00+08:00',enabled=True)['facts'][0]['value'],'8')
        self.assertEqual(as_of({},None,None,enabled=False)['facts'],[])
    def test_sameinstant_visibility_timezone_equivalence(self):
        b=validate_bundle(fact_payload())
        a=as_of(b,'600000.SH','2024-03-01T08:00:00Z',enabled=True)
        c=as_of(b,'600000.SH','2024-03-01T16:00:00+08:00',enabled=True)
        self.assertEqual(a,c);self.assertEqual(len(a['facts']),1)
    def test_deterministic_input_order(self):
        p=fact_payload();a=validate_bundle(p);p['facts'].reverse();b=validate_bundle(p);self.assertEqual(a,b)
    def test_duplicate_revision_rejected(self):
        p=fact_payload();p['facts'].append(p['facts'][0])
        with self.assertRaises(ValueError):validate_bundle(p)
    def test_revision_time_must_increase(self):
        p=fact_payload();p['facts'][1]['available_at']='2024-02-01T16:00:00+08:00'
        with self.assertRaises(ValueError):validate_bundle(p)
    def test_no_cross_unit_revision(self):
        p=fact_payload();p['facts'][1]['unit']='USD'
        with self.assertRaises(ValueError):validate_bundle(p)
    def test_bad_values_naive_time_and_extra_fields(self):
        for field,value in [('value','NaN'),('value',True),('available_at','2024-02-01'),('available_at','2023-01-01T00:00:00Z'),('revision',True),('symbol','510300.SH'),('account_password','secret')]:
            p=fact_payload();p['facts'][0][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(ValueError):validate_bundle(p)
    def test_tampered_hash(self):
        b=validate_bundle(fact_payload());b['facts'][0]['value']='1000'
        with self.assertRaises(ValueError):as_of(b,'600000.SH','2024-04-01T16:00:00+08:00',enabled=True)
    def test_core_output_unchanged_by_optional_extension(self):
        d=demo_dataset();p={'symbol':'600000.SH','cost_model_acknowledged':True}
        before=backtest(d,p);b=validate_bundle(fact_payload());as_of(b,'600000.SH','2024-04-01T16:00:00+08:00',enabled=True)
        self.assertEqual(before,backtest(d,p))
    def test_source_text_hash_recorded(self):
        b=validate_bundle(fact_payload());self.assertEqual(b['source_sha256'],hashlib.sha256('虚构财务数据'.encode()).hexdigest())
        self.assertFalse(b['source_truth_verified'])

if __name__=='__main__':unittest.main()
