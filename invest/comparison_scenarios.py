"""Predeclared synthetic execution scenarios, not market data or strategy tests."""
from copy import deepcopy
from .data import dataset_identity
from .comparison import prepare_case

DAYS = ['2025-01-06','2025-01-07','2025-01-08','2025-01-09','2025-01-10','2025-01-13']


def synthetic_dataset(symbol='600000.SH'):
    bars=[]
    for day,price in zip(DAYS,[10,10,11,9,12,10]):
        bars.append(dict(symbol=symbol,date=day,open=price,close=price,high=price+2,low=price-2,
                         volume_shares=1000000,up_limit=100,down_limit=1,suspended=False,
                         corporate_action=False,adj_factor=1))
    data={'meta':{'source':'INVEST SYNTHETIC EXECUTION FIXTURE — NOT OBSERVED QUOTES',
                  'source_kind':'demo','currency':'CNY','price_basis':'raw','volume_unit':'shares',
                  'calendar_source':'manually declared synthetic sessions; not official calendar'},
          'bars':bars,'calendar':list(DAYS)}
    data['id']=dataset_identity(data)
    return data


def costs(**changes):
    return dict(initial_cash=10000,commission_rate=0,min_commission=0,stamp_tax_rate=0,
                transfer_fee_rate=0,slippage_bps=0,cost_model_acknowledged=True,**{}) | changes


def order(key,day,side,quantity=100):
    return dict(id=key,date=DAYS[day],signal_date=DAYS[day-1],side=side,quantity=quantity)


def scenarios():
    """Expectations are contract hypotheses; an unexpected observation fails suite.

    MATCH never claims economic validity. DIVERGED is expected only for the named
    native-policy difference; the exact differing fields must also be observed.
    """
    output=[]
    def add(name,title,intents=None,params=None,changes=None,symbol='600000.SH',expected='MATCH',fields=()):
        data=synthetic_dataset(symbol)
        for idx, values in (changes or {}).items(): data['bars'][idx].update(values)
        data['id']=dataset_identity(data)
        case=prepare_case(data,symbol,intents or [order('buy',1,'BUY'),order('sell',2,'SELL')],params or costs())
        output.append(dict(name=name,title=title,expected_status=expected,required_difference_fields=list(fields),case=case))
    add('round_trip','人民币买入与次日卖出')
    add('shenzhen','深圳主板标识映射',symbol='000001.SZ')
    add('same_day_t1','当天买入不可当天卖出',intents=[order('buy',1,'BUY'),order('same_day_sell',1,'SELL'),order('next_day_sell',2,'SELL')])
    add('cash_shortfall','费用导致现金不足',intents=[order('buy',1,'BUY')],params=costs(initial_cash=1000,min_commission=5))
    add('suspension','明确停牌拒绝买入',intents=[order('buy',1,'BUY')],changes={1:dict(suspended=True)})
    add('zero_volume','零成交量拒绝',intents=[order('buy',1,'BUY')],changes={1:dict(volume_shares=0)})
    add('upper_limit_buy','涨停拒绝买入',intents=[order('buy',1,'BUY')],changes={1:dict(open=12,close=12,high=12,low=12,up_limit=12)})
    add('upper_limit_sell','涨停允许卖出已有可用仓位',changes={2:dict(open=12,close=12,high=12,low=12,up_limit=12)})
    add('lower_limit_sell','跌停拒绝卖出',changes={2:dict(open=8,close=8,high=8,low=8,down_limit=8)})
    add('lower_limit_buy','跌停允许买入',intents=[order('buy',1,'BUY')],changes={1:dict(open=8,close=8,high=8,low=8,down_limit=8)})
    add('oversell','固定股数API：超额卖出整笔拒绝',intents=[order('buy',1,'BUY'),order('sell',2,'SELL',200)])
    add('old_new_lots','同日新旧仓位可售量',intents=[order('buy_old',1,'BUY'),order('buy_new',2,'BUY'),order('sell',2,'SELL',200)])
    add('partial_volume','流动性不足：整笔拒绝与部分成交',intents=[order('buy',1,'BUY',300)],changes={1:dict(volume_shares=150)},expected='DIVERGED',fields=['filled_quantity','shares'])
    add('day_volume_reuse','同日多单累计流动性',intents=[order('first',1,'BUY'),order('second',1,'BUY')],changes={1:dict(volume_shares=100)},expected='DIVERGED',fields=['filled_quantity'])
    add('exact_volume','恰好一手的成交容量',intents=[order('buy',1,'BUY')],changes={1:dict(volume_shares=100)})
    add('sub_lot_volume','不足一手的成交容量',intents=[order('buy',1,'BUY')],changes={1:dict(volume_shares=99)})
    add('min_fee_tax','固定演示最低佣金与卖出税',params=costs(min_commission=5,stamp_tax_rate=.0005))
    add('fractional_fees','分项费用到分取整差异',params=costs(commission_rate=.000333,stamp_tax_rate=.000537),expected='DIVERGED',fields=['commission','stamp_tax'])
    add('transfer_fee','原生费用未包含显式过户费用',params=costs(transfer_fee_rate=.00001),expected='DIVERGED',fields=['other_fees','cash'])
    add('slippage_tick','百分比滑点与不利方向价格取整',params=costs(slippage_bps=1),expected='DIVERGED',fields=['price'])
    add('slippage_ohlc','滑点后超出声明OHLC',intents=[order('buy',1,'BUY')],params=costs(slippage_bps=1),changes={1:dict(open=10,close=10,high=10,low=10)},expected='DIVERGED',fields=['filled_quantity'])
    add('mark_to_close','开盘成交与收盘估值分离',changes={1:dict(open=10,close=11,high=12,low=8),2:dict(open=12,close=11,high=14,low=9)})
    add('cash_exact','余额恰好包含最低佣金',intents=[order('buy',1,'BUY')],params=costs(initial_cash=1005,min_commission=5))
    add('no_inventory','空仓卖出拒绝',intents=[order('sell',1,'SELL')])
    return deepcopy(output)
