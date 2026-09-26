"""Isolated, synthetic-only RQAlpha execution worker; never imports Invest.

The data/event adapter supplies TWO DECLARED daily proxy events, not real minute
or auction data. Unmodified RQAlpha broker, matcher, positions and risk checks
execute the order intentions. No reference fills or balances enter this process.
"""
from __future__ import annotations
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
from datetime import date, datetime, time

COMMIT = '0d98adefa87956e26f3e7ca5b26b5f3fc7ca834f'
SOURCE_IDENTITY = '4617f50229799b78a31692c3edfbe2c1b99b004ef4d95a93bdc98242a9494260'
MAX_INPUT = 4 * 1024 * 1024
NETWORK_ATTEMPTS = []


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def sha(obj):
    return hashlib.sha256(canonical(obj).encode()).hexdigest()


def deny_network(event, args):
    if event in {'socket.connect', 'socket.connect_ex', 'socket.getaddrinfo', 'socket.sendto'}:
        NETWORK_ATTEMPTS.append(event)
        raise RuntimeError('OUTBOUND_NETWORK_DISABLED_FOR_SYNTHETIC_VERIFICATION')


def verify_source(lock):
    if not isinstance(lock,dict) or sha(lock.get('python_files'))!=SOURCE_IDENTITY:
        raise ValueError('UNTRUSTED_SOURCE_LOCK')
    spec = importlib.util.find_spec('rqalpha')
    if spec is None or not spec.origin:
        raise ValueError('RQALPHA_NOT_INSTALLED: install the pinned optional environment')
    root = Path(spec.origin).resolve().parent
    actual = {}
    for path in sorted(root.rglob('*.py')):
        rel = path.relative_to(root).as_posix()
        if rel == '_version.py' or '__pycache__' in path.parts:
            continue
        if path.is_symlink() or path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError('UNSUPPORTED_RQALPHA_SOURCE_FILE')
        actual[rel] = hashlib.sha256(path.read_text(encoding='utf-8').encode()).hexdigest()
    if lock.get('commit') != COMMIT or actual != lock.get('python_files') or not actual:
        raise ValueError('RQALPHA_SOURCE_MISMATCH: installed source differs from the archived commit')
    return {'repository': 'ricequant/rqalpha', 'commit': COMMIT,
            'source_identity': sha(actual), 'python_files': len(actual),
            'worker_sha256': hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode('utf-8')).hexdigest(),
            'source_verification': 'EXACT_NORMALIZED_PYTHON_FILES',
            'excluded_generated_file': '_version.py'}


def validate_case(case):
    """Independent boundary checks only; this does not implement matching rules."""
    import re
    if not isinstance(case,dict) or set(case)!={'schema','purpose','source_kind','dataset_id',
          'symbol','currency','bars','orders','parameters','first_row_is_warmup','signal_validation'}:
        raise ValueError('INVALID_CASE_FIELDS')
    if (case['schema']!='invest-order-intentions-v1' or case['purpose']!='SYNTHETIC_ENGINE_VERIFICATION'
        or case['source_kind']!='demo' or case['currency']!='CNY' or case['first_row_is_warmup'] is not True
        or case['signal_validation']!='strictly_before_execution_date'):
        raise ValueError('ONLY_SYNTHETIC_ENGINE_VERIFICATION_SUPPORTED')
    if not isinstance(case['symbol'],str) or not re.fullmatch(r'(?:60[0-9]{4}\.SH|00[0-9]{4}\.SZ)',case['symbol']):
        raise ValueError('UNSUPPORTED_SYMBOL')
    if not isinstance(case['dataset_id'],str) or not re.fullmatch('[0-9a-f]{64}',case['dataset_id']):
        raise ValueError('INVALID_DATASET_ID')
    def number(v):
        if type(v) not in (int,float) or not math.isfinite(v): raise ValueError('INVALID_NUMBER')
        return v
    rows=case['bars']; orders=case['orders']; p=case['parameters']
    if not isinstance(rows,list) or not 2<=len(rows)<=2000 or not isinstance(orders,list) or not 1<=len(orders)<=2000:
        raise ValueError('CASE_SIZE_OUT_OF_RANGE')
    days=[]
    for r in rows:
        if not isinstance(r,dict) or set(r)!={'date','symbol','open','high','low','close','volume_shares',
              'up_limit','down_limit','suspended','corporate_action','adj_factor'}:
            raise ValueError('INVALID_BAR_FIELDS')
        if r['symbol']!=case['symbol'] or type(r['date']) is not str or date.fromisoformat(r['date']).isoformat()!=r['date']:
            raise ValueError('INVALID_BAR_IDENTITY')
        days.append(r['date'])
        if type(r['suspended']) is not bool or r['corporate_action'] is not False or number(r['adj_factor'])!=1:
            raise ValueError('UNSUPPORTED_MARKET_FACTS')
        for k in ('open','high','low','close','up_limit','down_limit'):
            if not 0<number(r[k])<=1e6: raise ValueError('INVALID_PRICE')
        if not r['down_limit']<=r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high']<=r['up_limit']:
            raise ValueError('INVALID_PRICE_ENVELOPE')
        if type(r['volume_shares']) is not int or not 0<=r['volume_shares']<=10**12:
            raise ValueError('INVALID_VOLUME')
    if days!=sorted(set(days)): raise ValueError('UNSORTED_OR_DUPLICATE_DATES')
    if not isinstance(p,dict) or set(p)!={'initial_cash','commission_rate','min_commission','stamp_tax_rate',
        'transfer_fee_rate','slippage_bps','cost_model_acknowledged'} or p['cost_model_acknowledged'] is not True:
        raise ValueError('INVALID_COST_FIELDS')
    if not 0<number(p['initial_cash'])<=1e9: raise ValueError('INVALID_INITIAL_CASH')
    for k,cap in [('commission_rate',.02),('stamp_tax_rate',.02),('transfer_fee_rate',.02),('min_commission',1000),('slippage_bps',1000)]:
        if not 0<=number(p[k])<=cap: raise ValueError('INVALID_COST')
    seen=set(); previous=''; per_day={}
    for o in orders:
        if not isinstance(o,dict) or set(o)!={'id','date','signal_date','side','quantity'}:
            raise ValueError('INVALID_ORDER_FIELDS')
        if type(o['id']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}',o['id']) or o['id'] in seen:
            raise ValueError('INVALID_ORDER_ID')
        if type(o['date']) is not str or type(o['signal_date']) is not str or o['date'] not in days[1:] or o['signal_date'] not in days or not o['signal_date']<o['date'] or o['date']<previous:
            raise ValueError('INVALID_ORDER_TIME')
        if o['side'] not in ('BUY','SELL') or type(o['quantity']) is not int or not 1<=o['quantity']<=10**7:
            raise ValueError('INVALID_ORDER_SIZE')
        if o['side']=='BUY' and o['quantity']%100: raise ValueError('INVALID_BUY_LOT')
        seen.add(o['id']); previous=o['date']; per_day[previous]=per_day.get(previous,0)+1
        if per_day[previous]>10: raise ValueError('TOO_MANY_DAILY_ORDERS')


def run_case(case):
    import numpy as np
    import pandas as pd
    from rqalpha import run_func
    from rqalpha.api import order_shares, subscribe
    from rqalpha.const import INSTRUMENT_TYPE, TRADING_CALENDAR_TYPE
    from rqalpha.core.events import EVENT, Event
    from rqalpha.environment import Environment
    from rqalpha.interface import AbstractDataSource, AbstractEventSource, AbstractMod
    from rqalpha.model.instrument import Instrument

    rows = case['bars']
    by_day = {r['date']: r for r in rows}
    days = list(by_day)
    symbol = case['symbol']
    code = symbol.replace('.SH', '.XSHG').replace('.SZ', '.XSHE')
    p = case['parameters']
    evaluation_days = days[1:]  # first declared day provides previous-close state
    intentions = case['orders']
    order_results = {}
    valuation_rows = []
    trade_events = []
    active_intention = [None]
    rejections = {}
    native_classes = {}
    dtype = [('datetime', 'i8'), ('open', 'f8'), ('high', 'f8'), ('low', 'f8'),
             ('close', 'f8'), ('volume', 'f8'), ('total_turnover', 'f8'),
             ('limit_up', 'f8'), ('limit_down', 'f8')]
    instrument = Instrument({'order_book_id': code, 'symbol': 'SYNTHETIC ONLY',
        'type': 'CS', 'exchange': code.split('.')[1], 'board_type': 'MainBoard',
        'round_lot': 100, 'market_tplus': 1, 'listed_date': '1990-01-01',
        'de_listed_date': '2999-12-31', 'sector_code': 'Synthetic',
        'industry_code': 'Synthetic', 'status': 'Active'})

    class Source(AbstractDataSource):
        def get_instruments(self, id_or_syms=None, types=None):
            if id_or_syms is not None:
                return [instrument] if code in id_or_syms or instrument.symbol in id_or_syms else []
            return [instrument] if types is None or INSTRUMENT_TYPE.CS in types or 'CS' in types else []

        def get_trading_calendars(self):
            return {TRADING_CALENDAR_TYPE.EXCHANGE: pd.DatetimeIndex(days)}

        def available_data_range(self, frequency):
            return date.fromisoformat(days[0]), date.fromisoformat(days[-1])

        def get_bar(self, ins, dt, frequency):
            r = by_day[dt.strftime('%Y-%m-%d')]
            # At proxy-open, the native current-bar matcher sees only the opening
            # price as close. Day volume is a declared retrospective bound, NOT
            # known intraday liquidity. No evening orders are submitted.
            price = r['open'] if dt.hour < 12 else r['close']
            record = np.zeros(1, dtype=dtype)
            record[0] = (int(dt.strftime('%Y%m%d%H%M%S')), r['open'], r['high'], r['low'],
                price, r['volume_shares'], r['volume_shares'] * price,
                r['up_limit'], r['down_limit'])
            return record[0]

        def history_bars(self, ins, bar_count, frequency, fields, dt, skip_suspended=True,
                         include_now=False, adjust_type='pre', adjust_orig=None):
            eligible = [r for r in rows if r['date'] <= dt.strftime('%Y-%m-%d')]
            if skip_suspended:
                eligible = [r for r in eligible if not r['suspended']]
            data = np.array([self.get_bar(ins, datetime.combine(date.fromisoformat(r['date']), time(15)), '1d')
                             for r in eligible[-bar_count:]], dtype=dtype)
            return data[fields] if fields else data

        def get_dividend(self, ins): return None
        def get_split(self, ins): return None
        def get_share_transformation(self, order_book_id): return None
        def get_yield_curve(self, start_date, end_date, tenor=None): return None
        def is_suspended(self, order_book_id, dates):
            return [by_day[pd.Timestamp(d).strftime('%Y-%m-%d')]['suspended'] for d in dates]
        def is_st_stock(self, order_book_id, dates): return [False for _ in dates]

    class Events(AbstractEventSource):
        def events(self, start_date, end_date, frequency):
            for d in evaluation_days:
                day = date.fromisoformat(d)
                for ev, hm in [(EVENT.BEFORE_TRADING, (8, 30)), (EVENT.BAR, (9, 31)),
                               (EVENT.BAR, (15, 0)), (EVENT.AFTER_TRADING, (15, 30))]:
                    dt = datetime.combine(day, time(*hm))
                    yield Event(ev, calendar_dt=dt, trading_dt=dt)

    class Mod(AbstractMod):
        def start_up(self, env, mod_config):
            env.set_data_source(Source())
            env.set_event_source(Events())
            def traded(event):
                t = event.trade
                if active_intention[0] is None:
                    raise ValueError('UNEXPECTED_NATIVE_FILL_OUTSIDE_INTENTION')
                trade_events.append({'id': active_intention[0], 'date': env.trading_dt.strftime('%Y-%m-%d'),
                    'symbol': symbol, 'side': t.side.name, 'quantity': int(t.last_quantity),
                    'price': float(t.last_price), 'commission': float(t.commission),
                    'stamp_tax': float(t.tax), 'other_fees': 0.0,
                    'fees': float(t.transaction_cost)})
            def rejected(event):
                if active_intention[0] is not None:
                    rejections[active_intention[0]]=str(event.reason)
            env.event_bus.add_listener(EVENT.TRADE, traded)
            env.event_bus.add_listener(EVENT.ORDER_CREATION_REJECT, rejected)
        def tear_down(self, code, exception=None): return None

    # Use the public Mod loader; don't patch RQAlpha's broker, matching or account.
    import types
    module = types.ModuleType('invest_rqalpha_fixture_mod')
    module.load_mod = Mod
    sys.modules[module.__name__] = module

    def init(context):
        subscribe(code)

    def handle_bar(context, bar_dict):
        if context.now.hour >= 12:
            return
        day = context.now.strftime('%Y-%m-%d')
        for intent in [x for x in intentions if x['date'] == day]:
            active_intention[0] = intent['id']
            start = len(trade_events)
            native = order_shares(code, intent['quantity'] if intent['side'] == 'BUY' else -intent['quantity'])
            fills = trade_events[start:]
            qty = sum(x['quantity'] for x in fills)
            order_results[intent['id']] = {'id': intent['id'], 'date': day, 'side': intent['side'],
                'requested_quantity': intent['quantity'], 'filled_quantity': qty,
                'status': 'FILLED' if qty == intent['quantity'] else 'PARTIAL' if qty else 'REJECTED',
                'native_status': native.status.name if native is not None else 'API_RETURNED_NONE',
                'reason': native.message if native is not None else rejections.get(intent['id'],'Native risk/position/order API refused the intention'),
                'fills': fills}
            if native is not None and not native.is_final():
                from rqalpha.api import cancel_order
                cancel_order(native)
            active_intention[0] = None

    def after_trading(context):
        from rqalpha.const import POSITION_DIRECTION
        env = Environment.get_instance()
        account = env.portfolio.accounts['STOCK']
        position = account.get_position(code, POSITION_DIRECTION.LONG)
        for name,obj in [('broker',env.broker),('portfolio',env.portfolio),('account',account),('position',position)]:
            native_classes[name]=type(obj).__module__+'.'+type(obj).__qualname__
        # Observe instantiated matching classes without creating/altering matchers.
        native_classes['matchers']=sorted({type(m).__module__+'.'+type(m).__qualname__ for m in env.broker._matchers.values()})
        valuation_rows.append({'date': context.now.strftime('%Y-%m-%d'),
            'cash': float(account.total_cash), 'shares': int(position.quantity),
            'equity': float(account.total_value)})

    config = {'base': {'start_date': evaluation_days[0], 'end_date': evaluation_days[-1],
        'frequency': '1d', 'accounts': {'STOCK': p['initial_cash']}, 'run_type': 'b',
        'rqdatac_uri': 'disabled'},
        'extra': {'log_level': 'error', 'enable_profiler': False},
        'mod': {'sys_accounts': {'enabled': True, 'stock_t1': True, 'auto_switch_order_value': False},
            'sys_simulation': {'enabled': True, 'matching_type': 'current_bar', 'signal': False,
                'price_limit': True, 'volume_limit': True, 'volume_percent': 1.0,
                'inactive_limit': True, 'slippage': p['slippage_bps'] / 10000},
            'sys_transaction_cost': {'enabled': True, 'stock_commission_multiplier': p['commission_rate'] / 0.0008,
                'stock_min_commission': p['min_commission'], 'tax_multiplier': p['stamp_tax_rate'] / 0.0005,
                'pit_tax': False, 'etf_commission': {'default': {'commission_rate': 0, 'min_commission': 0}}},
            'sys_risk': {'enabled': True}, 'sys_analyser': {'enabled': False},
            'sys_progress': {'enabled': False}, 'sys_scheduler': {'enabled': False},
            'fixture': {'enabled': True, 'lib': module.__name__, 'priority': 999}}}
    requested_config=json.loads(canonical(config))
    run_func(config=config, init=init, handle_bar=handle_bar, after_trading=after_trading)
    if set(order_results) != {o['id'] for o in intentions}:
        raise ValueError('NATIVE_ENGINE_DID_NOT_PROCESS_ALL_INTENTIONS')
    return {'orders': [order_results[o['id']] for o in intentions], 'curve': valuation_rows,
        'trades': trade_events, 'engine': 'rqalpha', 'case_id': sha(case),
        'execution_components': ['run_func', 'Executor', 'SimulationBroker', 'DefaultBarMatcher',
                                 'Portfolio', 'Account', 'StockPosition', 'sys_risk'],
        'cost_model': 'RQALPHA_NATIVE_FIXED_ILLUSTRATIVE',
        'semantic_differences': ['Native partial fills versus Invest all-or-none day orders',
            'Fixed-share API rejects excess sells with sys_risk enabled; value APIs are not used',
            'Native fees are not rounded per component to cents; native other_fees omits transfer fee',
            'Native percentage slippage differs from Invest adverse tick rounding and OHLC rejection'],
        'data_model': 'SYNTHETIC_DAILY_OPEN_CLOSE_PROXY_NOT_INTRADAY_DATA',
        'real_provider_calls': 0, 'requested_native_config': requested_config, 'native_classes': native_classes}


def main():
    try:
        sys.addaudithook(deny_network)
        raw = sys.stdin.buffer.read(MAX_INPUT + 1)
        if len(raw) > MAX_INPUT: raise ValueError('INPUT_TOO_LARGE')
        value = json.loads(raw, parse_constant=lambda x: (_ for _ in ()).throw(ValueError('NONFINITE_JSON')))
        if set(value) != {'case', 'source_lock', 'license_acknowledged'} or value['license_acknowledged'] is not True:
            raise ValueError('EXPLICIT_RQALPHA_LICENSE_ACKNOWLEDGMENT_REQUIRED')
        case = value['case']
        validate_case(case)
        identity = verify_source(value['source_lock'])
        import contextlib
        # stdout is a JSON-only transport; native logs go to bounded host log file.
        with contextlib.redirect_stdout(sys.stderr):
            result = run_case(case)
        if NETWORK_ATTEMPTS: raise ValueError('UNEXPECTED_NETWORK_ATTEMPT')
        result['identity'] = identity
        result['network_policy'] = 'DENY_SOCKET_CONNECT_AND_DNS'
        result['network_attempts'] = len(NETWORK_ATTEMPTS)
        sys.stdout.write(canonical({'ok': True, 'result': result}))
        return 0
    except Exception as exc:
        sys.stdout.write(canonical({'ok': False, 'error_type': type(exc).__name__, 'error': str(exc)[:4000]}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
