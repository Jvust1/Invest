"""Independent-engine laboratory: shared intentions, separate execution.

Version 1 intentionally accepts SYNTHETIC datasets only. Two outputs agreeing is
not evidence of real fills, a profitable strategy or independent data providers.
RQAlpha is an optional out-of-process dependency; normal Invest stays stdlib-only.
"""
from __future__ import annotations
from collections import Counter
from decimal import Decimal
import hashlib
import html
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .data import verify_dataset_identity
from .engine import execute_order, validate_market_window, validate_parameters, ENGINE_VERSION
from .provenance import code_identity
from .workspace import canonical, digest

SCHEMA = 'invest-independent-engine-comparison-v1'
CASE_SCHEMA = 'invest-order-intentions-v1'
RQ_COMMIT = '0d98adefa87956e26f3e7ca5b26b5f3fc7ca834f'
RQ_SOURCE_IDENTITY = '4617f50229799b78a31692c3edfbe2c1b99b004ef4d95a93bdc98242a9494260'
COST_KEYS = {'initial_cash', 'commission_rate', 'min_commission', 'stamp_tax_rate',
             'transfer_fee_rate', 'slippage_bps', 'cost_model_acknowledged'}
BAR_KEYS = {'symbol','date','open','high','low','close','volume_shares','up_limit',
            'down_limit','suspended','corporate_action','adj_factor'}
ORDER_KEYS = {'id','date','signal_date','side','quantity'}
TOLERANCE = Decimal('0.000001')


def prepare_case(dataset: dict, symbol: str, orders: list, parameters: dict) -> dict:
    verify_dataset_identity(dataset)
    if dataset['meta'].get('source_kind') != 'demo':
        raise ValueError('v1仅接收合成数据；不得为通过校验将真实行情改标为demo')
    if not isinstance(parameters, dict) or set(parameters) - COST_KEYS:
        raise ValueError('对照只接受明确成本与资金参数，不接受未知字段')
    p = validate_parameters(parameters)
    bars = validate_market_window(dataset, symbol)
    if not 2 <= len(bars) <= 2000:
        raise ValueError('需要2–2000条完整行情；第一条只用作前一日基线')
    if not isinstance(orders, list) or not 1 <= len(orders) <= 2000:
        raise ValueError('需要1–2000个下单意图，空对照不能判通过')
    if any(b['adj_factor'] != 1 or type(b['volume_shares']) is not int for b in bars):
        raise ValueError('合成v1要求复权因子为1且成交量为整数类型')
    days = [b['date'] for b in bars]
    seen, per_day, previous_index = set(), Counter(), -1
    normalized = []
    for intent in orders:
        if not isinstance(intent, dict) or set(intent) != ORDER_KEYS:
            raise ValueError('每个意图只允许id/date/signal_date/side/quantity')
        key = intent['id']
        if not isinstance(key,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',key) or key in seen:
            raise ValueError('意图ID必须唯一且为1–64字符ASCII标识')
        if intent['date'] not in days[1:] or intent['signal_date'] not in days:
            raise ValueError('意图日期或信号日期未在明确日历中')
        index = days.index(intent['date'])
        if index < previous_index or intent['signal_date'] >= intent['date']:
            raise ValueError('意图须按日期排序，信号须在执行日之前')
        if not isinstance(intent['side'],str) or intent['side'] not in {'BUY','SELL'} or type(intent['quantity']) is not int or not 1 <= intent['quantity'] <= 10**7:
            raise ValueError('意图方向/股数非法')
        if intent['side']=='BUY' and intent['quantity'] % 100:
            raise ValueError('买入意图须为100股整数倍，禁止依赖引擎自动取整')
        seen.add(key); per_day[index] += 1; previous_index = index
        if per_day[index] > 10: raise ValueError('单日意图不能超过10条')
        normalized.append(dict(intent))
    return {'schema': CASE_SCHEMA, 'purpose': 'SYNTHETIC_ENGINE_VERIFICATION',
        'source_kind':'demo','dataset_id':dataset['id'],'symbol':symbol,'currency':'CNY',
        'bars': [{k:b[k] for k in sorted(BAR_KEYS)} for b in bars],
        'orders':normalized,'parameters':{k:p[k] for k in sorted(COST_KEYS)},
        'first_row_is_warmup':True,'signal_validation':'strictly_before_execution_date'}


def validate_case(case: dict) -> None:
    """Revalidate a transported case; declared demo provenance is not data proof."""
    fields = {'schema','purpose','source_kind','dataset_id','symbol','currency',
              'bars','orders','parameters','first_row_is_warmup','signal_validation'}
    if not isinstance(case,dict) or set(case) != fields:
        raise ValueError('对照输入字段不完整或含额外字段')
    if not isinstance(case['dataset_id'],str) or not re.fullmatch('[0-9a-f]{64}',case['dataset_id']):
        raise ValueError('原数据身份无效')
    bars=case['bars']
    if not isinstance(bars,list) or not 2<=len(bars)<=2000 or any(not isinstance(b,dict) for b in bars):
        raise ValueError('行情数量或格式不合法')
    if len(canonical(case).encode('utf-8'))>3*1024*1024:
        raise ValueError('对照输入过大')
    from .data import dataset_identity
    data={'meta':{'source':'synthetic contract revalidation','source_kind':'demo',
                 'currency':'CNY','price_basis':'raw','volume_unit':'shares',
                 'calendar_source':'declared synthetic sessions'},
          'bars':bars,'calendar':[b.get('date') for b in bars]}
    data['id']=dataset_identity(data)
    normalized=prepare_case(data,case['symbol'],case['orders'],case['parameters'])
    normalized['dataset_id']=case['dataset_id']
    if canonical(normalized)!=canonical(case):
        raise ValueError('输入并非规范合成对照合同；请通过prepare_case建立')


def run_invest(case: dict) -> dict:
    validate_case(case)
    cash = Decimal(str(case['parameters']['initial_cash']))
    lots = []  # [buy date, remaining shares], so same-day inventory is not eligible
    orders, trades, curve = [], [], []
    for bar in case['bars'][1:]:
        day = bar['date']
        for intent in [o for o in case['orders'] if o['date']==day]:
            record = {'id':intent['id'],'date':day,'side':intent['side'],
                'requested_quantity':intent['quantity'],'filled_quantity':0,
                'status':'REJECTED','native_status':'REJECTED','fills':[],'reason':''}
            eligible = sum(q for d,q in lots if d < day)
            try:
                f = execute_order(bar,intent['side'],intent['quantity'],cash,eligible,case['parameters'])
                cash = f['cash_after']
                if intent['side']=='BUY': lots.append([day,intent['quantity']])
                else:
                    left = intent['quantity']
                    for lot in lots:
                        if lot[0]<day:
                            take=min(left,lot[1]);lot[1]-=take;left-=take
                fill = {'id':intent['id'],'date':day,'symbol':case['symbol'],'side':intent['side'],
                    'quantity':f['quantity'],'price':float(f['price']),
                    'commission':float(f['commission']),'stamp_tax':float(f['stamp_tax']),
                    'other_fees':float(f['transfer_fee']),'fees':float(f['fees'])}
                record.update(filled_quantity=f['quantity'],status='FILLED',native_status='FILLED',fills=[fill])
                trades.append(fill)
            except ValueError as exc:
                record['reason']=str(exc)
            orders.append(record)
        quantity=sum(q for _,q in lots)
        equity=(cash+quantity*Decimal(str(bar['close']))).quantize(Decimal('.01'))
        curve.append({'date':day,'cash':float(cash),'shares':quantity,'equity':float(equity)})
    return {'engine':'invest','case_id':digest(case),'orders':orders,'curve':curve,'trades':trades,
        'identity':{'engine_version':ENGINE_VERSION,'code_identity':code_identity()},
        'cost_model':'INVEST_CENT_ROUNDED_ALL_COMPONENTS'}


def _finite(value):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or abs(value)>1e18:
        raise ValueError('引擎输出含非法金额')
    return Decimal(str(value))


def _validate_result(case: dict, result: dict, engine: str) -> None:
    if not isinstance(result,dict) or result.get('engine')!=engine or result.get('case_id')!=digest(case):
        raise ValueError('引擎结果或输入身份不匹配')
    expected_days=[b['date'] for b in case['bars'][1:]]
    if not isinstance(result.get('curve'),list) or any(not isinstance(x,dict) for x in result['curve']) or [x.get('date') for x in result['curve']]!=expected_days:
        raise ValueError('每日估值缺失、重复或窗口不一致')
    for point in result['curve']:
        for name in ('cash','equity'): _finite(point[name])
        if type(point.get('shares')) is not int or point['shares']<0: raise ValueError('持仓数量非法')
    if not isinstance(result.get('orders'),list) or any(not isinstance(o,dict) for o in result['orders']) or [o.get('id') for o in result['orders']] != [o['id'] for o in case['orders']]:
        raise ValueError('意图结果缺失、重复或顺序不一致')
    flat=[]
    for intention, row in zip(case['orders'],result['orders']):
        if any(row.get(k)!=intention[k] for k in ('date','side')) or row.get('requested_quantity')!=intention['quantity']:
            raise ValueError('成交方向、日期或原始意图数量不匹配')
        qty=row.get('filled_quantity')
        if type(qty) is not int or not 0<=qty<=intention['quantity']: raise ValueError('成交数量不合法')
        status='FILLED' if qty==intention['quantity'] else 'PARTIAL' if qty else 'REJECTED'
        if row.get('status')!=status: raise ValueError('成交状态与数量冲突')
        if not isinstance(row.get('fills'),list) or any(not isinstance(f,dict) for f in row['fills']) or sum(f['quantity'] for f in row['fills'])!=qty:
            raise ValueError('逐笔成交与订单汇总不一致')
        for fill in row['fills']:
            if any(fill.get(k)!=row[k] for k in ('id','date','side')) or fill.get('symbol')!=case['symbol']:
                raise ValueError('逐笔成交身份不匹配')
            if type(fill['quantity']) is not int or fill['quantity']<=0: raise ValueError('逐笔成交数量非法')
            for k in ('price','commission','stamp_tax','other_fees','fees'):
                if _finite(fill[k]) < 0: raise ValueError('负数价格或费用')
            if _finite(fill['price'])<=0: raise ValueError('成交价格不能为零')
            if abs(_finite(fill['fees'])-sum(_finite(fill[k]) for k in ('commission','stamp_tax','other_fees'))) > TOLERANCE:
                raise ValueError('费用合计不一致')
            flat.append(fill)
    if result.get('trades') != flat: raise ValueError('订单与成交记录不一致')
    if not isinstance(result.get('identity'),dict) or not result['identity']:
        raise ValueError('缺少引擎来源身份')
    if engine=='rqalpha':
        i=result['identity']
        if (i.get('commit')!=RQ_COMMIT or i.get('source_verification')!='EXACT_NORMALIZED_PYTHON_FILES'
            or i.get('source_identity')!=RQ_SOURCE_IDENTITY or i.get('python_files')!=151
            or type(result.get('network_attempts')) is not int or result['network_attempts']!=0
            or type(result.get('real_provider_calls')) is not int or result['real_provider_calls']!=0):
            raise ValueError('RQAlpha源码身份或离线边界未验证')


def validate_result(case: dict, result: dict, engine: str) -> None:
    """Validate transport plus per-day accounting independently of either matcher."""
    validate_case(case)
    if engine not in ('invest','rqalpha'): raise ValueError('未知引擎')
    try:
        _validate_result(case,result,engine)
        cash=Decimal(str(case['parameters']['initial_cash'])); shares=0
        by_day={b['date']:b for b in case['bars']}
        for point in result['curve']:
            for fill in (t for t in result['trades'] if t['date']==point['date']):
                value=_finite(fill['price'])*fill['quantity']
                if fill['side']=='BUY': cash-=value+_finite(fill['fees']);shares+=fill['quantity']
                else: cash+=value-_finite(fill['fees']);shares-=fill['quantity']
            if shares<0 or cash < -TOLERANCE: raise ValueError('账本出现透支或做空')
            if shares!=point['shares'] or abs(cash-_finite(point['cash']))>TOLERANCE:
                raise ValueError('逐笔成交与每日现金持仓不一致')
            equity=cash+shares*Decimal(str(by_day[point['date']]['close']))
            if abs(equity-_finite(point['equity']))>TOLERANCE:
                raise ValueError('逐笔成交与每日净值不一致')
    except (KeyError,TypeError,AttributeError,OverflowError) as exc:
        raise ValueError('引擎输出字段缺失或格式错误') from exc


def run_rqalpha(case: dict, *, python_executable: str, license_acknowledged: bool,
                timeout: int = 60, root: Path | None = None) -> dict:
    validate_case(case)
    if license_acknowledged is not True: raise ValueError('须明确阅读并确认RQAlpha许可；本适配仅做合成验证')
    if type(timeout) is not int or not 1<=timeout<=180: raise ValueError('超时须为1–180秒')
    root = Path(__file__).resolve().parents[1] if root is None else Path(root)
    worker=root/'integrations/rqalpha/worker.py'
    try:
        lock=json.loads((root/'integrations/rqalpha/source-lock.json').read_text(encoding='utf-8'))
        if lock.get('commit')!=RQ_COMMIT or digest(lock.get('python_files'))!=RQ_SOURCE_IDENTITY:
            raise ValueError('RQAlpha固定清单不匹配')
    except (OSError,ValueError,AttributeError) as exc:
        raise ValueError('缺失或损坏的源码扩展文件；请使用完整源码交付包') from exc
    if not isinstance(python_executable,str): raise ValueError('Python路径须为文本')
    executable=Path(python_executable)
    if not executable.is_absolute() or not executable.is_file(): raise ValueError('须指定已安装依赖的Python可执行文件绝对路径')
    payload=canonical({'case':case,'source_lock':lock,'license_acknowledged':True}).encode()
    if len(payload)>4*1024*1024: raise ValueError('输入包过大')
    with tempfile.TemporaryDirectory(prefix='invest-rqalpha-') as tmp:
        # Environment allowlist excludes provider tokens, proxy credentials and user config.
        env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','LD_LIBRARY_PATH') if k in os.environ}
        env.update(HOME=tmp,USERPROFILE=tmp,TMPDIR=tmp,TEMP=tmp,TMP=tmp,MPLCONFIGDIR=tmp,
                   PYTHONUTF8='1',PYTHONIOENCODING='utf-8',OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1')
        with open(Path(tmp)/'stdout.json','w+b') as out, open(Path(tmp)/'stderr.txt','w+b') as err:
            try:
                completed=subprocess.run([str(executable),'-I',str(worker)],input=payload,
                    stdout=out,stderr=err,env=env,cwd=tmp,timeout=timeout,check=False)
            except subprocess.TimeoutExpired as exc:
                raise ValueError('RQAlpha运行超时，结果未被接受') from exc
            if out.tell()>16*1024*1024 or err.tell()>16*1024*1024: raise ValueError('引擎输出过大')
            out.seek(0);raw=out.read();err.seek(0);log=err.read(4000).decode('utf-8','replace')
        try: response=json.loads(raw)
        except (ValueError,UnicodeError) as exc: raise ValueError('RQAlpha未返回有效JSON: '+log[:300]) from exc
        if not isinstance(response,dict): raise ValueError('RQAlpha结果必须为JSON对象')
        if completed.returncode!=0 or response.get('ok') is not True:
            raise ValueError('RQAlpha失败: '+str(response.get('error',log))[:2000])
        result=response.get('result')
        validate_result(case,result,'rqalpha')
        if result['identity'].get('worker_sha256')!=hashlib.sha256(worker.read_text(encoding='utf-8').encode('utf-8')).hexdigest():
            raise ValueError('实际运行适配器版本不匹配')
        if result['identity'].get('source_identity')!=digest(lock['python_files']):
            raise ValueError('实际RQAlpha源码快照不匹配')
        validate_result(case,result,'rqalpha')
        return result


def compare_results(case: dict, left: dict, right: dict) -> dict:
    validate_result(case,left,'invest');validate_result(case,right,'rqalpha')
    differences=[]
    def check(where,key,a,b):
        if isinstance(a,(int,float)) and not isinstance(a,bool) and isinstance(b,(int,float)) and not isinstance(b,bool):
            same=abs(_finite(a)-_finite(b))<=TOLERANCE
        else: same=a==b
        if not same: differences.append({'location':where,'field':key,'invest':a,'rqalpha':b})
    for l,r in zip(left['curve'],right['curve']):
        for k in ('cash','shares','equity'): check(l['date'],k,l[k],r[k])
    for l,r in zip(left['orders'],right['orders']):
        for k in ('status','filled_quantity'): check(l['id'],k,l[k],r[k])
        for k in ('commission','stamp_tax','other_fees','fees'):
            check(l['id'],k,sum(x[k] for x in l['fills']),sum(x[k] for x in r['fills']))
        check(l['id'],'fills_count',len(l['fills']),len(r['fills']))
        for idx,(a,b) in enumerate(zip(l['fills'],r['fills'])):
            for k in ('price','quantity'):check(l['id']+f'/fill{idx}',k,a[k],b[k])
    return {'schema':SCHEMA,'case_id':digest(case),'status':'MATCH' if not differences else 'DIVERGED',
        'absolute_numeric_tolerance':str(TOLERANCE),'reference':'shared_intentions_not_shared_fills',
        'dates_compared':len(left['curve']),'intentions_compared':len(left['orders']),
        'differences':differences,'difference_count':len(differences),
        'case':case,'invest':left,'rqalpha':right,
        'real_market_validated':False,'all_growth_gates_passed':False,
        'limitations':['合成输入只验证工程行为，不代表真实市场、策略收益或前向观察。',
            '两个引擎共享同一数据与意图，不是独立数据来源，也未独立验证策略信号。',
            'RQAlpha使用声明的日线开收盘代理事件和原生成交/账户逻辑，不是真实分钟行情。',
            '不支持公司行动、ETF、融资、做空、真实账户或订单；分歧不是自动选出更优引擎。']}


def render_html(report: dict) -> str:
    esc=lambda v:html.escape(str(v))
    diffs=''.join('<tr>'+''.join('<td>'+esc(d[k])+'</td>' for k in ('location','field','invest','rqalpha'))+'</tr>' for d in report['differences'])
    if not diffs: diffs='<tr><td colspan="4">本次声明范围内未发现数值差异。</td></tr>'
    orders=''.join('<tr>'+''.join('<td>'+esc(v)+'</td>' for v in (a['id'],a['date'],a['side'],a['requested_quantity'],a['status'],b['status'],a['filled_quantity'],b['filled_quantity']))+'</tr>' for a,b in zip(report['invest']['orders'],report['rqalpha']['orders']))
    limitations=''.join('<li>'+esc(x)+'</li>' for x in report['limitations'])
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Invest 双引擎对照</title><style>body{font-family:system-ui,sans-serif;max-width:1120px;margin:40px auto;padding:0 20px;line-height:1.65;color:#192b3a;background:#f6f8fa}header,section{background:white;padding:24px;margin:18px 0;border-radius:12px}h1{margin-top:0}code{overflow-wrap:anywhere}table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;text-align:left;border-bottom:1px solid #ddd}.scroll{overflow:auto}small{color:#526577}</style><header><small>INVEST / 独立执行引擎实验室 · 仅合成验证</small><h1>Invest × RQAlpha：'+esc(report['status'])+'</h1><p>'+str(report['dates_compared'])+' 个评价日 · '+str(report['intentions_compared'])+' 个下单意图 · '+str(report['difference_count'])+' 处差异</p><p>输入身份 <code>'+esc(report['case_id'])+'</code></p><p>RQAlpha固定源码 <code>'+esc(report['rqalpha']['identity']['commit'])+'</code></p><p>结果一致不代表策略有效；有分歧时保留两边原始结果，不强行调成一致。</p></header><section><h2>逐项差异</h2><div class="scroll"><table><tr><th>位置</th><th>字段</th><th>Invest</th><th>RQAlpha</th></tr>'+diffs+'</table></div></section><section><h2>逐笔意图与成交</h2><div class="scroll"><table><tr><th>意图</th><th>日期</th><th>方向</th><th>申请股数</th><th>Invest状态</th><th>RQAlpha状态</th><th>Invest成交</th><th>RQAlpha成交</th></tr>'+orders+'</table></div></section><section><h2>证据边界</h2><ul>'+limitations+'</ul><p>两套引擎分别产生现金、持仓、成交和费用；比较的是完整每日账本，不只是最终收益。</p></section></html>'
