"""G3: manual CNY accounting review, NOT a broker or simulated fill engine.

Append-only events, idempotency, Decimal cash, declared cash dividends and
valuation-based unitisation. Legacy PaperLedger remains the execution model.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from .data import is_mainboard_symbol
from .workspace import Workspace, canonical, instant, text

CENT = Decimal('0.01')
SHANGHAI = timezone(timedelta(hours=8))


def amount(value, *, positive=False):
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError('金额必须是人民币数值')
    try:
        v = Decimal(str(value))
        if not v.is_finite() or v < 0 or v > Decimal('1000000000') or v != v.quantize(CENT):
            raise ValueError('金额必须非负、有限、精确到分且不超过十亿元')
        if positive and v <= 0:
            raise ValueError('金额必须大于零')
    except InvalidOperation:
        raise ValueError('金额格式错误') from None
    return v.quantize(CENT)


def symbol(value):
    if not is_mainboard_symbol(value):
        raise ValueError('仅接受沪深主板股票代码')
    return value


def create_review(workspace, payload):
    if not isinstance(payload, dict) or payload.get('manual_record_acknowledged') is not True:
        raise ValueError('请确认这是人工复盘账本，不是券商成交或自动模拟成交')
    profile = {'schema':'invest-manual-review-v1', 'name':text(payload.get('name'),'账户名称',80),
               'initial_cash':str(amount(payload.get('initial_cash'),positive=True)),
               'client_key':text(payload.get('client_key'),'创建幂等键',100),
               'mode':'MANUAL_REPLAY_NO_EXECUTION_CLAIM', 'currency':'CNY'}
    return workspace.put('review',profile)


def normalize_event(raw):
    if not isinstance(raw, dict):
        raise ValueError('复盘事件必须是对象')
    kind = raw.get('type')
    allowed = {'DEPOSIT':{'amount'}, 'WITHDRAWAL':{'amount'}, 'FEE':{'amount'},
               'DIVIDEND':{'amount','symbol'}, 'BUY':{'symbol','quantity','price','fee'},
               'SELL':{'symbol','quantity','price','fee'}, 'MARK':{'prices'},
               'DECISION':{'reason','evidence_at'}, 'FAILURE':{'reason'}, 'RETRY':{'reason'}}
    if kind not in allowed or set(raw) != {'type','occurred_at','source'} | allowed[kind]:
        raise ValueError('事件字段不完整或包含不支持的字段')
    moment = instant(raw['occurred_at'])
    if moment > datetime.now(timezone.utc):
        raise ValueError('不能把未来事件记为已经发生')
    event = {'type':kind,'occurred_at':moment.isoformat(),'source':text(raw['source'],'证据来源',1000)}
    if 'amount' in raw:
        event['amount'] = str(amount(raw['amount'],positive=True))
    if 'symbol' in raw:
        event['symbol'] = symbol(raw['symbol'])
    if kind in ('BUY','SELL'):
        n = raw['quantity']
        if type(n) is not int or not 1 <= n <= 100000000:
            raise ValueError('股数必须为正整数且不超过一亿股')
        if kind == 'BUY' and n % 100:
            raise ValueError('买入股数必须是100股的整数倍')
        event.update(quantity=n,price=str(amount(raw['price'],positive=True)),fee=str(amount(raw['fee'])))
    if kind == 'MARK':
        prices = raw['prices']
        if not isinstance(prices, dict) or len(prices)>100:
            raise ValueError('估值价格必须是至多100只股票的对象')
        event['prices'] = {symbol(s):str(amount(v,positive=True)) for s,v in sorted(prices.items())}
    if 'reason' in raw:
        event['reason'] = text(raw['reason'],'记录理由',4000)
    if kind == 'DECISION':
        evidence = instant(raw['evidence_at'])
        if evidence > moment:
            raise ValueError('决策不能引用当时尚未可见的证据')
        event['evidence_at'] = evidence.isoformat()
    return event


def replay(profile, events, *, as_of=None):
    if profile.get('schema') != 'invest-manual-review-v1':
        raise ValueError('复盘账户版本不支持')
    initial = cash = amount(profile['initial_cash'],positive=True)
    units = initial
    net_flows = total_fees = dividends = Decimal(0)
    holdings, marks, buys = {}, {}, {}
    last = None
    nav_peak = Decimal(1)
    max_drawdown = Decimal(0)
    points = []
    def equity():
        if any(q and s not in marks for s,q in holdings.items()):
            return None
        return cash + sum(Decimal(q) * marks[s][0] for s,q in holdings.items() if q)
    for event in events:
        normalized = normalize_event(event)
        if normalized != event:
            raise ValueError('事件不是规范化记录')
        now = instant(event['occurred_at'])
        if last is not None and now < last:
            raise ValueError('不能追加倒序事件；请建立独立复盘账户处理历史更正')
        last = now
        kind = event['type']
        value = Decimal(event.get('amount','0'))
        if kind in ('DEPOSIT','WITHDRAWAL'):
            if any(q and (s not in marks or marks[s][1] != now) for s,q in holdings.items()):
                raise ValueError('存在持仓时，资金进出前须提交同一时刻的完整MARK估值')
            before = equity()
            signed = value if kind == 'DEPOSIT' else -value
            if signed < 0 and cash < value:
                raise ValueError('可取现金不足')
            if before is None or before <= 0 or units <= 0:
                raise ValueError('净值归零后请新建账户，不延续旧收益率')
            nav = before / units
            if before + signed <= 0:
                raise ValueError('全部退出请保留原账本并新建账户；不计算零资产收益率')
            units += signed / nav
            cash += signed
            net_flows += signed
        elif kind == 'FEE':
            if value > cash:
                raise ValueError('现金不足以支付费用')
            cash -= value
            total_fees += value
        elif kind == 'DIVIDEND':
            if holdings.get(event['symbol'],0) <= 0:
                raise ValueError('没有相应持仓，不能登记持仓现金股息')
            cash += value
            dividends += value
        elif kind in ('BUY','SELL'):
            s,n = event['symbol'],event['quantity']
            gross,fee = Decimal(event['price'])*n,Decimal(event['fee'])
            day = now.astimezone(SHANGHAI).date()
            if gross > Decimal('1000000000'):
                raise ValueError('单笔成交额超过账本限制')
            if kind == 'BUY':
                if cash < gross + fee:
                    raise ValueError('可用现金不足')
                cash -= gross + fee
                holdings[s] = holdings.get(s,0) + n
                buys.setdefault(s,[]).append([day,n])
            else:
                available = sum(q for d,q in buys.get(s,[]) if d < day)
                if n > available or n > holdings.get(s,0):
                    raise ValueError('持仓或T+1可卖股数不足')
                if n % 100 and n != available:
                    raise ValueError('零股必须一次卖出全部可卖数量')
                remaining = n
                for lot in buys.get(s,[]):
                    if lot[0] < day:
                        taken = min(lot[1],remaining)
                        lot[1] -= taken
                        remaining -= taken
                if cash + gross - fee < 0:
                    raise ValueError('卖出款不足以支付费用')
                cash += gross - fee
                holdings[s] -= n
            total_fees += fee
            marks.pop(s,None)  # declared fill is NOT a current valuation quote
        elif kind == 'MARK':
            active = {s for s,q in holdings.items() if q}
            if set(event['prices']) != active:
                raise ValueError('MARK必须且只能覆盖所有当前持仓')
            marks = {s:(Decimal(v),now) for s,v in event['prices'].items()}
        value_now = equity()
        # Performance observations require one coherent valuation instant.
        coherent = value_now is not None and all(marks[s][1] == now for s,q in holdings.items() if q)
        nav = value_now/units if coherent and units>0 else None
        if nav is not None:
            nav_peak = max(nav_peak,nav)
            max_drawdown = max(max_drawdown,(nav_peak-nav)/nav_peak)
        points.append({'occurred_at':event['occurred_at'],'type':kind,'cash':str(cash),
                       'equity':str(value_now) if coherent else None,
                       'unit_nav':str(nav) if nav is not None else None})
    latest = instant(as_of) if as_of is not None else datetime.now(timezone.utc)
    if last and latest < last:
        raise ValueError('查询时刻不能早于账本最后事件')
    value_now = equity()
    positions = []
    for s,q in sorted(holdings.items()):
        if not q:
            continue
        mark = marks.get(s)
        positions.append({'symbol':s,'quantity':q,'marked_price':str(mark[0]) if mark else None,
                          'marked_at':mark[1].isoformat() if mark else None,
                          'quote_age_hours':(latest-mark[1]).total_seconds()/3600 if mark else None,
                          'market_value':str(mark[0]*q) if mark else None})
    complete = value_now is not None
    coherent = complete and (not positions or (last is not None and all(marks[p['symbol']][1] == last for p in positions)))
    weights = [Decimal(p['market_value'])/value_now for p in positions] if complete and value_now>0 else []
    last_nav = value_now/units if coherent and units>0 else None
    warnings = ['仅核对人工声明的历史事件，不核实成交、股息归属、税率或除权；不是实盘或自动模拟成交',
                '股息是人工确认的税后现金总额；不自动处理送转、拆股、配股或退市']
    if not complete:
        warnings.append('缺少持仓估值，净资产和收益显示为空')
    if any(p['quote_age_hours'] is None or p['quote_age_hours']>24 for p in positions):
        warnings.append('持仓价格缺失或超过24个自然小时；该提示不推断交易所开市日')
    if not coherent:
        warnings.append('没有同一时刻的完整估值；本次收益率为空')
    return {'mode':profile['mode'],'currency':'CNY','cash':str(cash),'positions':positions,
            'initial_cash':str(initial),'net_external_flows':str(net_flows),
            'net_assets_on_last_marks':str(value_now) if complete else None,
            'profit_on_last_marks':str(value_now-initial-net_flows) if complete else None,
            'total_fees':str(total_fees),'cash_dividends':str(dividends),
            'time_weighted_return':float(last_nav-1) if last_nav is not None else None,
            'max_drawdown_on_observed_nav':float(max_drawdown),
            'largest_position_weight_on_last_marks':float(max(weights)) if weights else (0 if not positions else None),
            'event_count':len(events),'valuation_points':points,'warnings':warnings,
            'forward_observation_accepted':False}


def append_event(workspace: Workspace, review_id, key, raw):
    profile = workspace.get(review_id,'review')['payload']
    event = normalize_event(raw)
    return workspace.append(review_id,key,event,lambda events:replay(profile,events))


def snapshot(workspace, review_id):
    doc = workspace.get(review_id,'review')
    records = workspace.events(review_id)
    state = replay(doc['payload'],[r['event'] for r in records])
    return {'review':doc,'state':state,'events':records,'chain_head':records[-1]['hash'] if records else '0'*64}
