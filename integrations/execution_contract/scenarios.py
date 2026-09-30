"""Predeclared new scenarios and hand-specified quantities for ENG-03.

The original v1 fixtures and expected divergences remain immutable.
"""
from copy import deepcopy
from invest.comparison_scenarios import scenarios as legacy_scenarios, synthetic_dataset, costs, order
from invest.comparison import prepare_case
from invest.data import dataset_identity

# Golden quantities were specified from the contract, not learned from a native run.
GOLDEN = {
    'session_reset': {'strict-partial-v1':[100,100], 'strict-aon-v1':[100,100], 'native-parity-v1':[100,100]},
    'sell_uses_capacity': {'strict-partial-v1':[100,100,0], 'strict-aon-v1':[100,100,0], 'native-parity-v1':[100,100,0]},
    'failed_order_capacity': {'strict-partial-v1':[0,100], 'strict-aon-v1':[0,100], 'native-parity-v1':[0,100]},
    'partial_then_small': {'strict-partial-v1':[200,0], 'strict-aon-v1':[0,100], 'native-parity-v1':[200,0]},
    'full_request_cash_check': {'strict-partial-v1':[0], 'strict-aon-v1':[0], 'native-parity-v1':[0]},
    'partial_min_fee': {'strict-partial-v1':[100], 'strict-aon-v1':[0], 'native-parity-v1':[100]},
    'upper_price_clamp': {'strict-partial-v1':[0], 'strict-aon-v1':[0], 'native-parity-v1':[100]},
    'lower_price_clamp': {'strict-partial-v1':[100,0], 'strict-aon-v1':[100,0], 'native-parity-v1':[100,100]},
    'ordered_two_strategies': {'strict-partial-v1':[200,0], 'strict-aon-v1':[0,100], 'native-parity-v1':[200,0]},
}


def additions():
    out=[]
    def add(name,title,intents,changes=None,parameters=None):
        data=synthetic_dataset()
        for index, values in (changes or {}).items():data['bars'][index].update(values)
        data['id']=dataset_identity(data)
        out.append({'name':name,'title':title,'case':prepare_case(data,'600000.SH',intents,parameters or costs())})
    add('session_reset','跨日重置，但同日不重置',[order('a',1,'BUY'),order('b',2,'BUY')],{1:{'volume_shares':100},2:{'volume_shares':100}})
    add('sell_uses_capacity','买卖共用成交量，卖出不释放容量',[order('a',1,'BUY'),order('s',2,'SELL'),order('b',2,'BUY')],{2:{'volume_shares':100}})
    add('failed_order_capacity','拒单不占用后续订单容量',[order('s',1,'SELL'),order('b',1,'BUY')],{1:{'volume_shares':100}})
    add('partial_then_small','部分成交或整笔拒绝改变后续可成交量',[order('large',1,'BUY',300),order('small',1,'BUY')],{1:{'volume_shares':250}})
    add('full_request_cash_check','全额意图现金不足，不依容量自动缩单',[order('b',1,'BUY',300)],{1:{'volume_shares':150}},costs(initial_cash=1005))
    add('partial_min_fee','部分成交最低佣金仅收一次',[order('b',1,'BUY',300)],{1:{'volume_shares':150}},costs(min_commission=5))
    add('upper_price_clamp','越界滑点：保守拒绝与原生涨停价裁剪',[order('b',1,'BUY')],{1:{'open':11.99,'close':11.99,'low':11,'high':12,'up_limit':12}},costs(slippage_bps=1000))
    add('lower_price_clamp','卖出越界滑点与跌停价裁剪',[order('b',1,'BUY'),order('s',2,'SELL')],{2:{'open':1.01,'close':1.01,'low':1,'high':2,'down_limit':1}},costs(slippage_bps=1000))
    add('ordered_two_strategies','同日策略按显式数组顺序竞争共享容量',[order('strategy_a',1,'BUY',300),order('strategy_b',1,'BUY')],{1:{'volume_shares':200}})
    return out


def definitions():
    return deepcopy(legacy_scenarios()+additions())
