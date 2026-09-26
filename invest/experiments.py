"""G1/G2: audit receipts, bounded chronological experiments and ledger replay.

These are exploratory comparisons, not an automatically opened frozen holdout.
The existing opening/evaluation validators retain responsibility for that gate.
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
import hashlib
from .data import verify_dataset_identity
from .engine import backtest, validate_market_window, validate_parameters
from .workspace import canonical, digest, text
from .provenance import code_identity, SCHEME as CODE_IDENTITY_SCHEME

SCHEMA = 'invest-exploratory-study-v1'
CENT = Decimal('0.01')


def audit_receipt(dataset, declaration=None):
    verify_dataset_identity(dataset)
    declaration = {} if declaration is None else declaration
    if not isinstance(declaration, dict):
        raise ValueError('来源声明必须是对象')
    rows = dataset['bars']
    symbols = sorted({r['symbol'] for r in rows})
    execution = []
    for symbol in symbols:
        try:
            window = validate_market_window(dataset, symbol)
            execution.append({'symbol': symbol, 'status': 'PASS', 'rows': len(window)})
        except ValueError as exc:
            execution.append({'symbol': symbol, 'status': 'BLOCKED', 'reason': str(exc)})
    license_note = declaration.get('license_note', 'UNKNOWN')
    license_note = text(license_note, '数据许可声明', 2000)
    original = declaration.get('raw_text')
    if original is not None and (not isinstance(original, str) or len(original.encode()) > 2 * 1024 * 1024):
        raise ValueError('原始来源文本超过限制')
    return {'schema': 'invest-audit-receipt-v1', 'dataset_id': dataset['id'],
            'code_identity': code_identity(), 'code_identity_scheme': CODE_IDENTITY_SCHEME, 'source_kind': dataset['meta'].get('source_kind'),
            'source': dataset['meta'].get('source'), 'currency': dataset['meta'].get('currency'),
            'price_basis': dataset['meta'].get('price_basis'), 'volume_unit': dataset['meta'].get('volume_unit'),
            'timezone': 'Asia/Shanghai (daily date convention)',
            'normalized_bytes': len(canonical({'bars': rows, 'calendar': dataset['calendar']}).encode()),
            'original_sha256': hashlib.sha256(original.encode()).hexdigest() if original is not None else None,
            'original_bytes': len(original.encode()) if original is not None else None,
            'license_note': license_note, 'license_independently_verified': False,
            'original_matches_dataset_verified': False,
            'execution_windows': execution, 'parser_audit': dataset['audit'],
            'row_locator': 'bars[zero_based_index]; symbol + date are the stable row key',
            'limitations': ['来源文本哈希只证明所提交文本身份，不证明来源真实、许可有效或与行情一致',
                           '执行窗口检查仅验证输入声明与计算合同，不证明交易所历史事实']}


def replay_ledger(dataset, result):
    """Independent arithmetic replay; deliberately does NOT call execute_order.

    Checks both strategy and benchmark, every daily cash/NAV, fees and T+1.
    It is not an independent market-data provider or second trading engine.
    """
    verify_dataset_identity(dataset)
    if result.get('dataset_id') != dataset['id']:
        raise ValueError('回放结果的数据集身份不匹配')
    bars = {b['date']: b for b in dataset['bars'] if b['symbol'] == result['symbol']}
    p = result['parameters']
    initial = Decimal(str(p['initial_cash']))
    def money(v):
        return Decimal(str(v)).quantize(CENT, rounding=ROUND_HALF_UP)
    checked = 0
    for benchmark in (False, True):
        cash, qty, fees = initial, 0, Decimal(0)
        trades = result['benchmark_trades'] if benchmark else result['trades']
        by_day = {}
        for trade in trades:
            day = trade['date']
            if day not in bars or day in by_day or trade.get('signal_date', day) >= day:
                raise ValueError('交易日期、重复成交或信号时间不一致')
            by_day[day] = trade
        last_buy = None
        curve_days = [c['date'] for c in result['curve']]
        if curve_days != sorted(set(curve_days)) or not set(by_day).issubset(curve_days):
            raise ValueError('曲线日期或交易覆盖不一致')
        for point in result['curve']:
            day = point['date']
            t = by_day.get(day)
            if t:
                price, n, side = Decimal(str(t['price'])), t['quantity'], t['side']
                if type(n) is not int or n <= 0 or side not in ('BUY', 'SELL'):
                    raise ValueError('回放成交格式错误')
                gross = money(price * n)
                commission = money(max(gross * Decimal(str(p['commission_rate'])), Decimal(str(p['min_commission']))))
                tax = money(gross * Decimal(str(p['stamp_tax_rate']))) if side == 'SELL' else Decimal(0)
                transfer = money(gross * Decimal(str(p['transfer_fee_rate'])))
                total = commission + tax + transfer
                for key, value in [('gross',gross), ('commission',commission), ('stamp_tax',tax), ('transfer_fee',transfer), ('fees',total)]:
                    if money(t[key]) != value:
                        raise ValueError('独立账本费用或成交额不一致: ' + key)
                if side == 'BUY':
                    if n % 100:
                        raise ValueError('回放买入数量不合法')
                    cash -= gross + total
                    qty += n
                    last_buy = day
                else:
                    if n > qty or last_buy == day:
                        raise ValueError('回放持仓或T+1不一致')
                    cash += gross - total
                    qty -= n
                if cash < 0 or money(t['cash_after']) != cash:
                    raise ValueError('独立账本现金不一致')
                fees += total
            equity = money(cash + qty * Decimal(str(bars[day]['close'])))
            field = 'benchmark_equity' if benchmark else 'equity'
            if money(point[field]) != equity:
                raise ValueError('独立账本净值不一致')
            if not benchmark and (money(point['cash']) != cash or point['shares'] != qty):
                raise ValueError('曲线现金或数量不一致')
            checked += 1
        fee_key = 'benchmark_total_fees' if benchmark else 'total_fees'
        if money(result['metrics'][fee_key]) != fees:
            raise ValueError('累计费用不一致')
    return {'status': 'PASS', 'checked_daily_valuations': checked,
            'scope': 'independent_arithmetic_replay_not_independent_market_validation'}


def run_study(dataset, specification):
    verify_dataset_identity(dataset)
    if not isinstance(specification, dict) or specification.get('cost_model_acknowledged') is not True:
        raise ValueError('必须确认成本为演示情景，不代表券商实际收费')
    if set(specification) - {'symbol','candidates','initial_cash','cost_model_acknowledged'}:
        raise ValueError('研究规格含有不支持的字段；不能通过此接口打开留出集')
    symbol = specification.get('symbol')
    candidates = specification.get('candidates', [{'name':'MA 5/20','fast':5,'slow':20}, {'name':'MA 10/30','fast':10,'slow':30}])
    if not isinstance(candidates, list) or not 1 <= len(candidates) <= 3:
        raise ValueError('候选假设必须为1–3个')
    checked, names = [], set()
    for c in candidates:
        if not isinstance(c, dict) or set(c) != {'name','fast','slow'}:
            raise ValueError('每个候选须包含name/fast/slow三个字段')
        name = text(c['name'], '候选名称', 60)
        if name in names:
            raise ValueError('候选名称不能重复')
        names.add(name)
        validate_parameters({'symbol':symbol, 'fast':c['fast'], 'slow':c['slow'], 'cost_model_acknowledged':True}, require_strategy=True)
        checked.append(dict(c, name=name))
    warmup = max(c['slow'] for c in checked)
    bars = [b for b in dataset['bars'] if b['symbol'] == symbol]
    if len(bars) < warmup + 30:
        raise ValueError('共同预热后至少需要30个交易日，才能形成三个比较区间')
    cash = specification.get('initial_cash',100000)
    validate_parameters({'initial_cash': cash, 'cost_model_acknowledged':True})
    cost_scenarios = [
        {'name':'低成本演示', 'commission_rate':0.0001, 'min_commission':0, 'stamp_tax_rate':0.0005,'transfer_fee_rate':0.00001,'slippage_bps':0},
        {'name':'中成本演示', 'commission_rate':0.0003, 'min_commission':5, 'stamp_tax_rate':0.0005,'transfer_fee_rate':0.00001,'slippage_bps':5},
        {'name':'高成本演示', 'commission_rate':0.001, 'min_commission':10, 'stamp_tax_rate':0.0005,'transfer_fee_rate':0.00002,'slippage_bps':20},
    ]
    count = len(bars) - warmup
    periods = [{'name':f'连续样本段 {i+1}', 'start':bars[warmup+count*i//3]['date'],
                'end':bars[warmup+count*(i+1)//3-1]['date']} for i in range(3)]
    protocol = {'schema':SCHEMA, 'dataset_id':dataset['id'], 'symbol':symbol, 'initial_cash':cash,
                'candidates':checked,'costs':cost_scenarios,'periods':periods,'shared_warmup':warmup,
                'mode':'EXPLORATORY_CHRONOLOGICAL_SLICES', 'code_identity':code_identity(),
                'code_identity_scheme':CODE_IDENTITY_SCHEME,
                'parameter_budget':len(checked)*9, 'frozen_holdout_opened':False}
    results = []
    for period in periods:
        for cost in cost_scenarios:
            for candidate in checked:
                record = {'period':period['name'],'candidate':candidate['name'],'cost':cost['name']}
                params = {k:v for k,v in cost.items() if k != 'name'}
                params.update({'initial_cash':cash,'symbol':symbol,'fast':candidate['fast'],'slow':candidate['slow'],
                               'start_date':period['start'],'end_date':period['end'],'cost_model_acknowledged':True})
                try:
                    run = backtest(dataset, params)
                    if run['evaluation_start'] != period['start'] or run['evaluation_end'] != period['end']:
                        raise ValueError('各候选的共同评价窗口不一致')
                    record.update(status='PASS', result=run, replay=replay_ledger(dataset,run),
                                  cash_baseline_return=0.0,
                                  excess_vs_buy_hold=run['metrics']['total_return']-run['metrics']['benchmark_return'])
                except ValueError as exc:
                    record.update(status='FAILED', reason=str(exc))
                results.append(record)
    return {'schema':SCHEMA, 'protocol':protocol,'protocol_id':digest(protocol),'results':results,
            'summary':{'planned':len(results),'succeeded':sum(r['status']=='PASS' for r in results),
                       'failed':sum(r['status']=='FAILED' for r in results),
                       'below_buy_hold':sum(r.get('excess_vs_buy_hold',0)<0 for r in results)},
            'source_kind':dataset['meta'].get('source_kind'),
            'limitations':['三个连续样本段不等于已核实的三种真实市场环境',
                           '结果全部保留，包括失败和落后基准的结果；没有自动选优或调参',
                           '冻结留出集未打开；探索比较不构成样本外有效性验收',
                           'MA候选属于同一思想族，独立账本只验证算术，不是第二个成交引擎']}
