"""ENG-03: sealed execution policies, cumulative liquidity, and native binding.

This module is an additive research reference. It does not change Invest v1,
RQAlpha's matcher, existing records, or the desktop. Profiles describe declared
synthetic experiments, NOT exchange rules or recommended execution assumptions.
"""
from __future__ import annotations
from copy import deepcopy
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, localcontext
import hashlib
from pathlib import Path

from invest.comparison import (validate_case, validate_result, compare_results,
                               run_rqalpha, RQ_COMMIT, RQ_SOURCE_IDENTITY)
from invest.workspace import canonical, digest

PROFILE_NAMES = ('strict-partial-v1', 'strict-aon-v1', 'native-parity-v1')
REQUEST_SCHEMA = 'invest-execution-contract-request-v2'
RESULT_SCHEMA = 'invest-execution-contract-result-v2'
REFERENCE_VERSION = 'invest-contract-reference-v2'
CENT = Decimal('0.01')
EPSILON = Decimal('0.000001')
ROOT = Path(__file__).resolve().parents[2]
# Fixed adapter binding: changing this adapter requires a new policy binding review.
NATIVE_WORKER_SHA256 = '2077ef539200ad247ce43e4244b4aa4f5fc233cc2d90cee7892673805286516a'


def identity(value):
    return digest(value)


def profile(name: str) -> dict:
    """Return a fresh, fully explicit content-addressed policy; no loose overrides."""
    if not isinstance(name, str) or name not in PROFILE_NAMES:
        raise ValueError('Unknown execution contract profile')
    native = name == 'native-parity-v1'
    rules = {
        'scope': 'SYNTHETIC_SINGLE_MAINBOARD_STOCK_NO_CORPORATE_ACTIONS',
        'currency': 'CNY',
        'liquidity': 'SHARED_SYMBOL_SESSION_BOTH_SIDES',
        'session': 'ONE_DECLARED_OPEN_PROXY_PER_DATE',
        'capacity': 'DECLARED_WHOLE_DAY_VOLUME_NOT_KNOWN_AT_OPEN',
        'participation': '1.0',
        'quantity_step': 100,
        'partial_fill': 'ALL_OR_NONE' if name == 'strict-aon-v1' else 'PARTIAL_IOC',
        'remainder': 'CANCEL_IMMEDIATELY_NO_CARRY',
        'order_priority': 'INPUT_ARRAY_ORDER',
        'cash_check': 'FULL_REQUEST_AT_EXECUTION_PRICE_NO_CASH_RESIZE',
        'sell_check': 'FULL_REQUEST_AGAINST_PRIOR_DATE_INVENTORY',
        'inventory': 'T_PLUS_1_FIFO_SYNTHETIC',
        'price': 'PERCENT_LIMIT_CLAMP' if native else 'ADVERSE_CENT_REJECT_OUTSIDE_OHLC',
        'tick': 'NOT_ROUNDED' if native else '0.01',
        'fees': 'UNROUNDED_COMPONENTS' if native else 'COMPONENT_CENT_HALF_UP',
        'commission_minimum': 'PER_ORDER_SINGLE_FILL',
        'tax': 'SELL_ONLY_EXPLICIT_ILLUSTRATIVE_RATE',
        'transfer_fee': 'ZERO_ONLY' if native else 'BOTH_SIDES_EXPLICIT_ILLUSTRATIVE_RATE',
        'mark': 'DECLARED_CLOSE_AFTER_ORDERS',
        'numeric_comparison_tolerance': '0.000001',
        'signal': 'DECLARED_PRIOR_DATE_NOT_INDEPENDENTLY_GENERATED',
        'real_market_validated': False,
    }
    value = {'schema': 'invest-execution-policy-v1', 'name': name, 'rules': rules}
    return dict(value, id=identity(value))


def prepare_request(case: dict, name: str = 'strict-partial-v1') -> dict:
    request = {'schema': REQUEST_SCHEMA, 'contract': profile(name), 'case': deepcopy(case)}
    validate_request(request)
    return request


def validate_request(request: dict) -> None:
    if not isinstance(request, dict) or set(request) != {'schema', 'contract', 'case'}:
        raise ValueError('Execution request fields do not match the versioned contract')
    if request['schema'] != REQUEST_SCHEMA or not isinstance(request['contract'], dict):
        raise ValueError('Unsupported request schema or contract')
    supplied = request['contract']
    if canonical(supplied) != canonical(profile(supplied.get('name'))):
        raise ValueError('Execution contract was altered; a rehashed unknown policy is not accepted')
    validate_case(request['case'])
    # No company actions or initial inventory exist; all inventory is round lots.
    if any(o['quantity'] % 100 for o in request['case']['orders']):
        raise ValueError('v2 requires round-lot intentions on both sides; no silent quantity rounding')
    if supplied['rules']['transfer_fee'] == 'ZERO_ONLY' and request['case']['parameters']['transfer_fee_rate'] != 0:
        raise ValueError('native-parity-v1 requires transfer_fee_rate=0; no silent fee removal')


def reference_identity() -> dict:
    files = {p.name: hashlib.sha256(p.read_text(encoding='utf-8').encode()).hexdigest()
             for p in sorted(Path(__file__).parent.glob('*.py'))}
    return {'engine_version': REFERENCE_VERSION, 'code_identity': identity(files),
            'source_files': files, 'scope': 'OPTIONAL_REFERENCE_NOT_DESKTOP_ENGINE'}


def _d(v):
    return Decimal(str(v))


def _fee_terms(price, quantity, params, native):
    gross = price * quantity
    commission = max(gross * _d(params['commission_rate']), _d(params['min_commission']))
    # Tax direction is handled by the caller, not guessed from signed quantities.
    if not native:
        gross = gross.quantize(CENT, rounding=ROUND_HALF_UP)
        commission = commission.quantize(CENT, rounding=ROUND_HALF_UP)
    return gross, commission


def _fees(price, quantity, params, side, native):
    gross, commission = _fee_terms(price, quantity, params, native)
    stamp = gross * _d(params['stamp_tax_rate']) if side == 'SELL' else Decimal(0)
    transfer = gross * _d(params['transfer_fee_rate'])
    if not native:
        stamp = stamp.quantize(CENT, rounding=ROUND_HALF_UP)
        transfer = transfer.quantize(CENT, rounding=ROUND_HALF_UP)
    return gross, commission, stamp, transfer


def _terms(bar, intent, params, native):
    if bar['suspended']:
        return None, 'SUSPENDED'
    if bar['volume_shares'] == 0:
        return None, 'ZERO_VOLUME'
    side = intent['side']; opening = _d(bar['open'])
    if side == 'BUY' and opening >= _d(bar['up_limit']):
        return None, 'UP_LIMIT_BUY'
    if side == 'SELL' and opening <= _d(bar['down_limit']):
        return None, 'DOWN_LIMIT_SELL'
    ratio = _d(params['slippage_bps']) / 10000
    price = opening * (1 + ratio if side == 'BUY' else 1 - ratio)
    if native:
        # This is an explicit opt-in policy, not a claim of tick-valid market fills.
        price = min(_d(bar['up_limit']), max(_d(bar['down_limit']), price))
    else:
        price = price.quantize(CENT, rounding=ROUND_CEILING if side == 'BUY' else ROUND_FLOOR)
        if not _d(bar['low']) <= price <= _d(bar['high']):
            return None, 'OUTSIDE_DECLARED_OHLC'
    return price, ''


def _trace(case, execution):
    """Derived occupancy, never presented as RQAlpha's internal matcher trace."""
    volumes = {b['date']: b['volume_shares'] for b in case['bars']}
    used = {}; rows = []
    for o in execution['orders']:
        day = o['date']; before = used.get(day, 0); after = before + o['filled_quantity']
        rows.append({'id': o['id'], 'date': day, 'symbol': case['symbol'],
                     'session_capacity': volumes[day], 'used_before': before,
                     'remaining_before': volumes[day] - before, 'filled': o['filled_quantity'],
                     'used_after': after, 'remaining_after': volumes[day] - after,
                     'cancelled_quantity': o['requested_quantity'] - o['filled_quantity']})
        used[day] = after
    return rows


def _envelope(request, execution, producer):
    return {'schema': RESULT_SCHEMA, 'status': 'EXECUTED',
            'producer': producer, 'request_id': identity(request),
            'contract_id': request['contract']['id'], 'execution': execution,
            'capacity_trace': _trace(request['case'], execution),
            'trace_origin': 'DERIVED_FROM_OBSERVED_FILLS_NOT_NATIVE_INTERNAL_TELEMETRY',
            'real_market_validated': False}


def run_reference(request: dict) -> dict:
    validate_request(request)
    case = request['case']; p = case['parameters']; rules = request['contract']['rules']
    native = rules['fees'] == 'UNROUNDED_COMPONENTS'
    orders, trades, curve, lots = [], [], [], []
    with localcontext() as ctx:
        ctx.prec = 40
        cash = _d(p['initial_cash'])
        for bar in case['bars'][1:]:
            day = bar['date']; used = 0
            for intent in (o for o in case['orders'] if o['date'] == day):
                requested = intent['quantity']; side = intent['side']
                price, reason = _terms(bar, intent, p, native)
                eligible = sum(q for d, q in lots if d < day)
                if not reason and side == 'SELL' and requested > eligible:
                    reason = 'INSUFFICIENT_PRIOR_DATE_INVENTORY'
                if not reason and side == 'BUY':
                    full = _fees(price, requested, p, side, native)
                    if sum(full) > cash:
                        reason = 'INSUFFICIENT_CASH_FOR_FULL_REQUEST'
                available = (bar['volume_shares'] - used) // 100 * 100
                filled = 0
                if not reason:
                    if rules['partial_fill'] == 'ALL_OR_NONE' and available < requested:
                        reason = 'ALL_OR_NONE_CAPACITY_SHORTFALL'
                    elif available < 100:
                        reason = 'SESSION_CAPACITY_EXHAUSTED'
                    else:
                        filled = min(requested, available)
                if filled and side == 'SELL':
                    gross, commission, stamp, transfer = _fees(price, filled, p, side, native)
                    if cash + gross - commission - stamp - transfer < 0:
                        filled = 0; reason = 'SELL_FEES_WOULD_OVERDRAW_CASH'
                row = {'id': intent['id'], 'date': day, 'side': side,
                       'requested_quantity': requested, 'filled_quantity': filled,
                       'status': 'FILLED' if filled == requested else 'PARTIAL' if filled else 'REJECTED',
                       'native_status': 'REFERENCE_V2', 'reason': reason, 'fills': []}
                if filled:
                    gross, commission, stamp, transfer = _fees(price, filled, p, side, native)
                    fee = commission + stamp + transfer
                    if side == 'BUY':
                        cash -= gross + fee; lots.append([day, filled])
                    else:
                        cash += gross - fee; left = filled
                        for lot in lots:
                            if lot[0] < day:
                                take = min(left, lot[1]); lot[1] -= take; left -= take
                    used += filled
                    fill = {'id': intent['id'], 'date': day, 'symbol': case['symbol'], 'side': side,
                            'quantity': filled, 'price': float(price), 'commission': float(commission),
                            'stamp_tax': float(stamp), 'other_fees': float(transfer), 'fees': float(fee)}
                    row['fills'] = [fill]; trades.append(fill)
                    if filled < requested:
                        row['reason'] = 'PARTIAL_FILLED_REMAINDER_CANCELLED'
                orders.append(row)
            shares = sum(q for _, q in lots)
            equity = cash + shares * _d(bar['close'])
            curve.append({'date': day, 'cash': float(cash), 'shares': shares, 'equity': float(equity)})
    execution = {'engine': 'invest', 'case_id': identity(case), 'orders': orders,
                 'curve': curve, 'trades': trades, 'identity': reference_identity(),
                 'cost_model': rules['fees']}
    result = _envelope(request, execution, 'REFERENCE_V2')
    audit_result(request, result)
    return result


def native_compatibility(request: dict) -> dict:
    validate_request(request)
    native_rules = profile('native-parity-v1')['rules']; given = request['contract']['rules']
    differences = [{'rule': k, 'requested': v, 'native_supported': native_rules[k]}
                   for k, v in given.items() if v != native_rules[k]]
    if request['case']['parameters']['transfer_fee_rate'] != 0:
        differences.append({'rule': 'transfer_fee_rate',
                            'requested': request['case']['parameters']['transfer_fee_rate'], 'native_supported': 0})
    return {'supported': not differences, 'differences': differences,
            'contract_id': request['contract']['id'], 'rqalpha_commit': RQ_COMMIT,
            'worker_sha256': NATIVE_WORKER_SHA256,
            'binding_scope': 'UNCHANGED_NATIVE_WORKER_CURRENT_BAR_SINGLE_OPEN_PROXY'}


def _verify_native_config(case, result):
    p = case['parameters']
    cfg = result.get('requested_native_config', {})
    try:
        checks = [cfg['base']['rqdatac_uri'] == 'disabled',
                  cfg['base']['accounts']['STOCK'] == p['initial_cash'],
                  cfg['base']['start_date'] == case['bars'][1]['date'],
                  cfg['base']['end_date'] == case['bars'][-1]['date'],
                  cfg['mod']['sys_accounts']['stock_t1'] is True,
                  cfg['mod']['sys_accounts']['auto_switch_order_value'] is False]
        sim = cfg['mod']['sys_simulation']; cost = cfg['mod']['sys_transaction_cost']
        for k, v in {'matching_type': 'current_bar', 'signal': False, 'price_limit': True,
                     'volume_limit': True, 'volume_percent': 1.0, 'inactive_limit': True,
                     'slippage': p['slippage_bps'] / 10000}.items():
            checks.append(type(sim[k]) is type(v) and sim[k] == v)
        for k, v in {'enabled': True, 'stock_commission_multiplier': p['commission_rate'] / .0008,
                     'stock_min_commission': p['min_commission'],
                     'tax_multiplier': p['stamp_tax_rate'] / .0005, 'pit_tax': False}.items():
            checks.append(cost[k] == v)
        checks += [cfg['mod']['sys_risk']['enabled'] is True,
                   result['identity']['worker_sha256'] == NATIVE_WORKER_SHA256]
        if not all(checks):
            raise ValueError('Native configuration does not implement the requested contract')
    except (KeyError, TypeError) as exc:
        raise ValueError('Native configuration evidence incomplete') from exc


def run_native(request: dict, *, python_executable: str, license_acknowledged: bool) -> dict:
    support = native_compatibility(request)
    if license_acknowledged is not True:
        raise ValueError('Explicit upstream license acknowledgement required')
    if not support['supported']:
        return {'schema': RESULT_SCHEMA, 'status': 'UNSUPPORTED_CONTRACT',
                'request_id': identity(request), 'contract_id': request['contract']['id'],
                'compatibility': support, 'execution': None, 'provider_calls': 0}
    worker = ROOT / 'integrations/rqalpha/worker.py'
    if hashlib.sha256(worker.read_text(encoding='utf-8').encode()).hexdigest() != NATIVE_WORKER_SHA256:
        raise ValueError('Native adapter changed; sealed binding cannot be reused')
    raw = run_rqalpha(request['case'], python_executable=python_executable,
                     license_acknowledged=True)
    _verify_native_config(request['case'], raw)
    result = _envelope(request, raw, 'RQALPHA_NATIVE')
    result['compatibility'] = support
    audit_result(request, result)
    return result


def audit_result(request: dict, result: dict) -> dict:
    """Check invariants, accounting and declared policies, never execute an engine.

    This is not a third independent matcher or an independent human review.
    Raw native fees/prices are retained; tolerances do not rewrite observations.
    """
    validate_request(request)
    if (not isinstance(result, dict) or result.get('schema') != RESULT_SCHEMA
            or result.get('status') != 'EXECUTED' or result.get('request_id') != identity(request)
            or result.get('contract_id') != request['contract']['id']
            or result.get('real_market_validated') is not False):
        raise ValueError('Result request/contract identity or status invalid')
    producer = result.get('producer'); engine = 'rqalpha' if producer == 'RQALPHA_NATIVE' else 'invest'
    if producer not in ('REFERENCE_V2', 'RQALPHA_NATIVE'):
        raise ValueError('Unknown execution producer')
    case = request['case']; raw = result['execution']; rules = request['contract']['rules']
    validate_result(case, raw, engine)
    if engine == 'invest' and raw['identity'] != reference_identity():
        raise ValueError('Reference implementation identity changed')
    if engine == 'rqalpha':
        if not native_compatibility(request)['supported']:
            raise ValueError('Unsupported native contract must not contain an execution')
        _verify_native_config(case, raw)
        if result.get('compatibility') != native_compatibility(request):
            raise ValueError('Native policy binding mismatch')
    trace = _trace(case, raw)
    if result.get('capacity_trace') != trace:
        raise ValueError('Capacity or cancelled remainder trace mismatch')
    if result.get('trace_origin') != 'DERIVED_FROM_OBSERVED_FILLS_NOT_NATIVE_INTERNAL_TELEMETRY':
        raise ValueError('Occupancy trace provenance is not declared')
    bars = {b['date']: b for b in case['bars']}; acquired = {}; sold = 0
    native = rules['fees'] == 'UNROUNDED_COMPONENTS'; params = case['parameters']
    observed_cash = _d(params['initial_cash'])
    for intent, row, occupancy in zip(case['orders'], raw['orders'], trace):
        bar = bars[row['date']]; qty = row['filled_quantity']; requested = intent['quantity']
        if occupancy['used_after'] > occupancy['session_capacity'] or occupancy['remaining_after'] < 0:
            raise ValueError('Shared session capacity exceeded')
        if qty % 100 or len(row['fills']) > 1:
            raise ValueError('Round lot or single-fill-per-intention policy violated')
        if rules['partial_fill'] == 'ALL_OR_NONE' and qty not in (0, requested):
            raise ValueError('All-or-none contract partially filled')
        # An accounting-consistent empty or underfilled result is not automatically valid.
        # These are policy checks, not an independent execution-engine claim.
        eligible_before = sum(q for d, q in acquired.items() if d < row['date']) - sold
        allowed_price, prohibited = _terms(bar, intent, params, native)
        possible = min(requested, occupancy['remaining_before'] // 100 * 100)
        if prohibited or row['side'] == 'SELL' and requested > eligible_before:
            possible = 0
        if not prohibited and row['side'] == 'BUY' and sum(_fees(allowed_price, requested, params, 'BUY', native)) > observed_cash + (EPSILON if native else 0):
            possible = 0
        if rules['partial_fill'] == 'ALL_OR_NONE' and possible != requested:
            possible = 0
        if possible and row['side'] == 'SELL':
            gross, commission, stamp, transfer = _fees(allowed_price, possible, params, 'SELL', native)
            if observed_cash + gross - commission - stamp - transfer < -(EPSILON if native else 0):
                possible = 0
        if qty != possible:
            raise ValueError('Observed fill quantity violates executable capacity/risk policy')
        if qty:
            if bar['suspended'] or bar['volume_shares'] == 0:
                raise ValueError('Fill violates suspension/volume facts')
            eligible = sum(q for d, q in acquired.items() if d < row['date']) - sold
            if row['side'] == 'SELL' and requested > eligible:
                raise ValueError('Full requested sell violates T+1 available inventory')
            if row['side'] == 'BUY':
                acquired[row['date']] = acquired.get(row['date'], 0) + qty
            else:
                sold += qty
            for f in row['fills']:
                observed = _d(f['price']); base = _d(bar['open'])
                ratio = _d(params['slippage_bps']) / 10000
                expected_price = base * (1 + ratio if row['side'] == 'BUY' else 1 - ratio)
                if native:
                    expected_price = min(_d(bar['up_limit']), max(_d(bar['down_limit']), expected_price))
                else:
                    expected_price = expected_price.quantize(CENT, rounding=ROUND_CEILING if row['side'] == 'BUY' else ROUND_FLOOR)
                    if not _d(bar['low']) <= observed <= _d(bar['high']) or observed % CENT:
                        raise ValueError('Fill violates OHLC or tick contract')
                if abs(expected_price-observed) > EPSILON:
                    raise ValueError('Fill price does not follow declared policy')
                if row['side']=='BUY' and base>=_d(bar['up_limit']) or row['side']=='SELL' and base<=_d(bar['down_limit']):
                    raise ValueError('Fill at forbidden directional limit')
                gross = expected_price * qty
                components = [max(gross*_d(params['commission_rate']), _d(params['min_commission'])),
                              gross*_d(params['stamp_tax_rate']) if row['side']=='SELL' else Decimal(0),
                              gross*_d(params['transfer_fee_rate'])]
                if not native:
                    components = [x.quantize(CENT, rounding=ROUND_HALF_UP) for x in components]
                flow = observed * qty
                observed_cash += (-flow if row['side']=='BUY' else flow) - _d(f['fees'])
                for name, expected in zip(('commission','stamp_tax','other_fees'), components):
                    if abs(_d(f[name])-expected) > EPSILON:
                        raise ValueError('Fill fee component violates contract: '+name)
    return {'status':'PASS', 'orders':len(raw['orders']), 'scope':'CONTRACT_INVARIANTS_AND_ACCOUNTING'}


def compare(request: dict, reference: dict, native: dict) -> dict:
    audit_result(request, reference)
    if native.get('status') == 'UNSUPPORTED_CONTRACT':
        expected = native_compatibility(request)
        if expected['supported'] or native.get('compatibility') != expected or native.get('request_id') != identity(request) or native.get('contract_id') != request['contract']['id'] or native.get('execution') is not None:
            raise ValueError('Invalid unsupported-contract evidence')
        return {'schema':'invest-contract-comparison-v2', 'status':'UNSUPPORTED_CONTRACT',
                'request_id':identity(request), 'contract_id':request['contract']['id'],
                'request':request, 'reference':reference, 'native':native,
                'real_market_validated':False}
    audit_result(request, native)
    comparison = compare_results(request['case'], reference['execution'], native['execution'])
    return {'schema':'invest-contract-comparison-v2', 'status':comparison['status'],
            'request_id':identity(request), 'contract_id':request['contract']['id'],
            'request':request, 'reference':reference, 'native':native,
            'comparison':comparison, 'real_market_validated':False}
