"""ENG-03 contract regressions. Native execution is in a separate integration suite."""
from copy import deepcopy
from decimal import Decimal
import tempfile
import unittest
from unittest.mock import patch

from invest.comparison_scenarios import scenarios, synthetic_dataset, costs, order
from invest.comparison import prepare_case
from invest.data import dataset_identity
from integrations.execution_contract import model as m


def example(name='round_trip', profile='strict-partial-v1'):
    case = next(s['case'] for s in scenarios() if s['name'] == name)
    return m.prepare_request(case, profile)


def quantities(result):
    return [r['filled_quantity'] for r in result['execution']['orders']]


class ContractInputTests(unittest.TestCase):
    def test_three_profiles_are_distinct(self):
        self.assertEqual(len(m.PROFILE_NAMES), 3)
        self.assertEqual(len({m.profile(n)['id'] for n in m.PROFILE_NAMES}), 3)
    def test_default_profile_is_strict(self):
        r = m.prepare_request(example()['case'])
        self.assertEqual(r['contract']['name'], 'strict-partial-v1')
    def test_same_request_is_stable(self):
        self.assertEqual(m.identity(example()), m.identity(example()))
    def test_rule_change_changes_request_identity(self):
        self.assertNotEqual(m.identity(example()), m.identity(example(profile='strict-aon-v1')))
    def test_unknown_profile_rejected(self):
        with self.assertRaises(ValueError): m.profile('automatic')
    def test_mutating_returned_profile_does_not_mutate_registry(self):
        p=m.profile('strict-partial-v1');p['rules']['liquidity']='UNLIMITED'
        self.assertNotEqual(p,m.profile('strict-partial-v1'))
    def test_tampered_profile_rejected_even_with_rehashed_id(self):
        r=example();r['contract']['rules']['liquidity']='UNLIMITED'
        r['contract']['id']=m.identity({k:v for k,v in r['contract'].items() if k!='id'})
        with self.assertRaises(ValueError):m.run_reference(r)
    def test_contract_id_tampering(self):
        r=example();r['contract']['id']='0'*64
        with self.assertRaises(ValueError):m.validate_request(r)
    def test_extra_request_field(self):
        r=example();r['reference_fills']=[]
        with self.assertRaises(ValueError):m.validate_request(r)
    def test_real_mode_rejected(self):
        r=example();r['case']['purpose']='REAL_TRADING'
        with self.assertRaises(ValueError):m.run_reference(r)
    def test_odd_lot_sell_is_not_silently_rounded(self):
        r=example();r['case']['orders'][1]['quantity']=150
        with self.assertRaises(ValueError):m.run_reference(r)
    def test_unknown_case_schema(self):
        r=example();r['case']['schema']='new'
        with self.assertRaises(ValueError):m.run_reference(r)
    def test_duplicate_orders_rejected(self):
        r=example();r['case']['orders'][1]['id']='buy'
        with self.assertRaises(ValueError):m.run_reference(r)
    def test_invalid_quantities(self):
        for q in (True,0,-100,100.0,None):
            r=example();r['case']['orders'][0]['quantity']=q
            with self.subTest(q=q), self.assertRaises(ValueError):m.run_reference(r)
    def test_invalid_price(self):
        for p in (True, float('nan'), float('inf'), -1):
            r=example();r['case']['bars'][1]['open']=p
            with self.subTest(p=p),self.assertRaises(ValueError):m.run_reference(r)
    def test_prepare_copies_input(self):
        r=example();base=deepcopy(r['case']);copy=m.prepare_request(base);base['orders'].clear()
        self.assertTrue(copy['case']['orders'])


class LiquidityTests(unittest.TestCase):
    def test_shared_capacity_closes_old_reuse_gap(self):
        result=m.run_reference(example('day_volume_reuse'))
        self.assertEqual(quantities(result),[100,0])
        self.assertEqual(result['capacity_trace'][1]['remaining_before'],0)
    def test_partial_fill_cancels_remainder(self):
        result=m.run_reference(example('partial_volume'))
        self.assertEqual(quantities(result),[100])
        self.assertEqual(result['capacity_trace'][0]['cancelled_quantity'],200)
        self.assertEqual(len(result['execution']['trades']),1)
    def test_aon_rejects_whole_order(self):
        self.assertEqual(quantities(m.run_reference(example('partial_volume','strict-aon-v1'))),[0])
    def test_fractional_session_remainder_not_tradable(self):
        r=example('partial_volume');r['case']['orders'].append(dict(r['case']['orders'][0],id='second',quantity=100))
        out=m.run_reference(r);self.assertEqual(quantities(out),[100,0])
        self.assertEqual(out['capacity_trace'][1]['remaining_before'],50)
    def test_day_boundary_resets_capacity(self):
        data=synthetic_dataset()
        for b in data['bars']:b['volume_shares']=100
        data['id']=dataset_identity(data)
        r=m.prepare_request(prepare_case(data,'600000.SH',[order('a',1,'BUY'),order('b',2,'BUY')],costs()))
        result=m.run_reference(r);self.assertEqual(quantities(result),[100,100])
        self.assertEqual([x['remaining_before'] for x in result['capacity_trace']],[100,100])
    def test_selling_does_not_release_capacity(self):
        data=synthetic_dataset();data['bars'][2]['volume_shares']=100;data['id']=dataset_identity(data)
        r=m.prepare_request(prepare_case(data,'600000.SH',[order('a',1,'BUY'),order('s',2,'SELL'),order('b',2,'BUY')],costs()))
        self.assertEqual(quantities(m.run_reference(r)),[100,100,0])
    def test_rejected_order_does_not_consume_capacity(self):
        r=example('day_volume_reuse');r['case']['orders'][0]['side']='SELL'
        out=m.run_reference(r);self.assertEqual(quantities(out),[0,100])
        self.assertEqual(out['capacity_trace'][0]['used_after'],0)
    def test_aon_failure_leaves_capacity_for_next_order(self):
        r=example('partial_volume','strict-aon-v1');r['case']['orders'].append(dict(r['case']['orders'][0],id='small',quantity=100))
        self.assertEqual(quantities(m.run_reference(r)),[0,100])
    def test_order_ordering_is_material(self):
        r=example('day_volume_reuse');out=m.run_reference(r)
        r['case']['orders'].reverse();reversed_out=m.run_reference(r)
        self.assertNotEqual(m.identity(out),m.identity(reversed_out))
        self.assertEqual(reversed_out['execution']['trades'][0]['id'],'second')
    def test_insufficient_full_request_cash_not_resized_to_capacity(self):
        r=example('partial_volume');r['case']['parameters']['initial_cash']=1005.0
        self.assertEqual(quantities(m.run_reference(r)),[0])
    def test_t1_rejection_preserved(self):
        self.assertEqual(quantities(m.run_reference(example('same_day_t1'))),[100,0,100])
    def test_not_enough_eligible_inventory_no_liquidity_resize(self):
        self.assertEqual(quantities(m.run_reference(example('old_new_lots'))),[100,100,0])
    def test_zero_and_sub_lot(self):
        for name in ('zero_volume','sub_lot_volume','suspension','upper_limit_buy'):
            with self.subTest(name=name):self.assertEqual(quantities(m.run_reference(example(name))),[0])


class MoneyAndPriceTests(unittest.TestCase):
    def test_simple_round_trip_hand_cash(self):
        self.assertEqual(m.run_reference(example())['execution']['curve'][-1]['cash'],10100)
    def test_fees_hand_cash(self):
        self.assertEqual(m.run_reference(example('min_fee_tax'))['execution']['curve'][-1]['cash'],10089.45)
    def test_cent_and_unrounded_fee_contracts_differ(self):
        a=m.run_reference(example('fractional_fees'))['execution']['trades'][0]
        b=m.run_reference(example('fractional_fees','native-parity-v1'))['execution']['trades'][0]
        self.assertEqual(a['commission'],.33);self.assertEqual(b['commission'],.333)
    def test_adverse_cent_tick_vs_fractional_price(self):
        a=m.run_reference(example('slippage_tick'))['execution']['trades'][0]
        b=m.run_reference(example('slippage_tick','native-parity-v1'))['execution']['trades'][0]
        self.assertEqual(a['price'],10.01);self.assertEqual(b['price'],10.001)
    def test_ohlc_rejection_is_profile_explicit(self):
        self.assertEqual(quantities(m.run_reference(example('slippage_ohlc'))),[0])
        self.assertEqual(quantities(m.run_reference(example('slippage_ohlc','native-parity-v1'))),[100])
    def test_transfer_fee_not_dropped(self):
        f=m.run_reference(example('transfer_fee'))['execution']['trades'][0]
        self.assertEqual(f['other_fees'],.01)
    def test_native_profile_rejects_nonzero_transfer(self):
        with self.assertRaisesRegex(ValueError,'transfer_fee'):example('transfer_fee','native-parity-v1')
    def test_min_fee_once_on_partial_not_on_cancelled_remainder(self):
        r=example('partial_volume');r['case']['parameters']['min_commission']=5.0
        o=m.run_reference(r)['execution'];self.assertEqual(o['trades'][0]['fees'],5);self.assertEqual(o['curve'][0]['cash'],8995)
    def test_cash_exact(self):
        self.assertEqual(m.run_reference(example('cash_exact'))['execution']['curve'][0]['cash'],0)
    def test_native_price_clamps_to_declared_limit(self):
        r=example('slippage_tick','native-parity-v1');r['case']['bars'][1]['up_limit']=12;r['case']['parameters']['slippage_bps']=1000.0
        # 10*(1+0.1)=11 remains inside limit; this fixture protects non-tick precision.
        self.assertEqual(m.run_reference(r)['execution']['trades'][0]['price'],11)


class BindingAndAuditTests(unittest.TestCase):
    def test_strict_policy_is_not_silently_mapped_to_native(self):
        for name in ('strict-partial-v1','strict-aon-v1'):
            r=example(profile=name)
            with patch.object(m,'run_rqalpha') as run:
                result=m.run_native(r,python_executable='/missing',license_acknowledged=True)
            self.assertEqual(result['status'],'UNSUPPORTED_CONTRACT');run.assert_not_called()
    def test_native_compatibility_supported(self):
        result=m.native_compatibility(example(profile='native-parity-v1'))
        self.assertTrue(result['supported']);self.assertEqual(result['differences'],[])
    def test_license_ack_before_native_call(self):
        with patch.object(m,'run_rqalpha') as run, self.assertRaises(ValueError):
            m.run_native(example(profile='native-parity-v1'),python_executable='/missing',license_acknowledged=False)
        run.assert_not_called()
    def test_reference_result_validates(self):
        for p in m.PROFILE_NAMES:
            r=example(profile=p);m.audit_result(r,m.run_reference(r))
    def test_result_contract_swap_rejected(self):
        r=example();result=m.run_reference(r);result['contract_id']='0'*64
        with self.assertRaises(ValueError):m.audit_result(r,result)
    def test_result_request_swap_rejected(self):
        r=example();result=m.run_reference(r);result['request_id']='0'*64
        with self.assertRaises(ValueError):m.audit_result(r,result)
    def test_capacity_trace_tampering_rejected(self):
        r=example('day_volume_reuse');result=m.run_reference(r);result['capacity_trace'][0]['used_after']=0
        with self.assertRaises(ValueError):m.audit_result(r,result)
    def test_remainder_tampering_rejected(self):
        r=example('partial_volume');result=m.run_reference(r);result['capacity_trace'][0]['cancelled_quantity']=0
        with self.assertRaises(ValueError):m.audit_result(r,result)
    def test_mutated_identity_rejected(self):
        r=example();result=m.run_reference(r);result['execution']['identity']['code_identity']='0'*64
        with self.assertRaises(ValueError):m.audit_result(r,result)
    def test_deterministic_reference_results(self):
        r=example('day_volume_reuse');self.assertEqual(m.run_reference(r),m.run_reference(r))
    def test_no_invest_matching_reuse(self):
        with patch('invest.engine.execute_order',side_effect=AssertionError('not an independent v2 implementation')):
            self.assertEqual(quantities(m.run_reference(example())),[100,100])

class AdditionalFailureTests(unittest.TestCase):
    def test_valid_accounting_but_empty_execution_is_not_accepted(self):
        r=example();out=m.run_reference(r)
        out['execution']['trades']=[]
        for row in out['execution']['orders']:
            row.update(filled_quantity=0,status='REJECTED',fills=[])
        for point in out['execution']['curve']:point.update(cash=10000.,shares=0,equity=10000.)
        out['capacity_trace']=m._trace(r['case'],out['execution'])
        with self.assertRaisesRegex(ValueError,'fill quantity'):m.audit_result(r,out)
    def test_source_binding_changed_before_native_launch(self):
        r=example(profile='native-parity-v1')
        with patch.object(m,'NATIVE_WORKER_SHA256','0'*64),patch.object(m,'run_rqalpha') as run,self.assertRaises(ValueError):
            m.run_native(r,python_executable='/missing',license_acknowledged=True)
        run.assert_not_called()
    def test_unsupported_result_cannot_smuggle_execution(self):
        r=example();a=m.run_reference(r);b=m.run_native(r,python_executable='/missing',license_acknowledged=True)
        b['execution']=a['execution']
        with self.assertRaises(ValueError):m.compare(r,a,b)
    def test_unsupported_contract_id_cannot_be_swapped(self):
        r=example();a=m.run_reference(r);b=m.run_native(r,python_executable='/missing',license_acknowledged=True)
        b['contract_id']='0'*64
        with self.assertRaises(ValueError):m.compare(r,a,b)
    def test_sell_cannot_create_overdraft(self):
        r=example();r['case']['parameters'].update(initial_cash=2000.,min_commission=1000.)
        for b in r['case']['bars'][2:]:b.update(open=.02,close=.02,low=.01,high=.02,down_limit=.01)
        # Execution price is valid but sale proceeds cannot cover the fee from zero cash.
        out=m.run_reference(r);self.assertEqual(quantities(out),[100,0]);self.assertEqual(out['execution']['curve'][-1]['cash'],0)
    def test_native_limit_clamp_is_not_ohlc_clamp(self):
        r=example('slippage_tick','native-parity-v1')
        b=r['case']['bars'][1];b.update(open=11.99,close=11.99,low=11,high=12,up_limit=12)
        r['case']['parameters']['slippage_bps']=1000.
        self.assertEqual(m.run_reference(r)['execution']['trades'][0]['price'],12)
    def test_strict_price_outside_limit_rejected(self):
        r=example('slippage_tick');b=r['case']['bars'][1];b.update(open=11.99,close=11.99,low=11,high=12,up_limit=12)
        r['case']['parameters']['slippage_bps']=1000.
        self.assertEqual(quantities(m.run_reference(r))[0],0)
    def test_underfilled_valid_balance_is_rejected(self):
        r=example('partial_volume');r['case']['bars'][1]['volume_shares']=250
        out=m.run_reference(r);self.assertEqual(quantities(out),[200])
        f=out['execution']['trades'][0];f['quantity']=100
        out['execution']['orders'][0]['filled_quantity']=100
        for point,bar in zip(out['execution']['curve'],r['case']['bars'][1:]):point.update(cash=9000.,shares=100,equity=9000.+100*bar['close'])
        out['capacity_trace']=m._trace(r['case'],out['execution'])
        with self.assertRaisesRegex(ValueError,'fill quantity'):m.audit_result(r,out)


if __name__=='__main__':
    unittest.main()
