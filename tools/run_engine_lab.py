"""Run genuine isolated RQAlpha comparisons and retain every result/failure.

Source-only add-on; no broker or real-data mode exists. No files are overwritten.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from invest.comparison import prepare_case,run_invest,run_rqalpha,compare_results,render_html,RQ_COMMIT
from invest.comparison_scenarios import scenarios,synthetic_dataset,costs,order,DAYS
from invest.data import dataset_identity
from invest.workspace import canonical,digest

# Hand-specified execution quantities; equality of two empty results is insufficient.
QUANTITIES={
 'round_trip':([100,100],[100,100]), 'shenzhen':([100,100],[100,100]),
 'same_day_t1':([100,0,100],[100,0,100]),'cash_shortfall':([0],[0]),
 'suspension':([0],[0]),'zero_volume':([0],[0]),'upper_limit_buy':([0],[0]),
 'upper_limit_sell':([100,100],[100,100]),'lower_limit_sell':([100,0],[100,0]),
 'lower_limit_buy':([100],[100]),'oversell':([100,0],[100,0]),
 'old_new_lots':([100,100,0],[100,100,0]),'partial_volume':([0],[100]),
 'day_volume_reuse':([100,100],[100,0]),'exact_volume':([100],[100]),
 'sub_lot_volume':([0],[0]),'min_fee_tax':([100,100],[100,100]),
 'fractional_fees':([100,100],[100,100]),'transfer_fee':([100,100],[100,100]),
 'slippage_tick':([100,100],[100,100]),'slippage_ohlc':([0],[100]),
 'mark_to_close':([100,100],[100,100]),'cash_exact':([100],[100]),'no_inventory':([0],[0])}


def save_json(path,obj): path.write_text(json.dumps(obj,ensure_ascii=True,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def outcome(name,report,definition):
    fields={x['field'] for x in report['differences']}
    checks={'expected_status':report['status']==definition['expected_status'],
            'required_difference_fields':set(definition['required_difference_fields'])<=fields}
    for engine,qty in zip(('invest','rqalpha'),QUANTITIES[name]):
        checks[engine+'_hand_specified_quantities']=[o['filled_quantity'] for o in report[engine]['orders']]==qty
    if name=='round_trip':
        checks['hand_calculated_final_cash']=all(report[e]['curve'][-1]['cash']==10100 for e in ('invest','rqalpha'))
    if name=='min_fee_tax':
        checks['hand_calculated_cash_after_costs']=all(report[e]['curve'][-1]['cash']==10089.45 for e in ('invest','rqalpha'))
    return checks


def probe_network(python):
    # A real audit-hook invocation rejects DNS before any OS network request.
    source="""import importlib.util,json,socket,sys
p=sys.argv[1];s=importlib.util.spec_from_file_location('w',p);w=importlib.util.module_from_spec(s);s.loader.exec_module(w)
sys.addaudithook(w.deny_network)
try: socket.getaddrinfo('invest-verification.invalid',443)
except RuntimeError as e:
 print(json.dumps({'blocked':str(e)=='OUTBOUND_NETWORK_DISABLED_FOR_SYNTHETIC_VERIFICATION','attempts':w.NETWORK_ATTEMPTS}));sys.exit(0)
raise SystemExit('network guard did not intercept DNS')
"""
    env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','LD_LIBRARY_PATH') if k in os.environ}
    p=subprocess.run([python,'-I','-c',source,str(ROOT/'integrations/rqalpha/worker.py')],capture_output=True,text=True,env=env,timeout=30,check=True)
    result=json.loads(p.stdout)
    if result!={'blocked':True,'attempts':['socket.getaddrinfo']}:raise ValueError('Network isolation probe failed')
    return result


def future_probes(python,folder,base):
    rows=[]
    for cutoff in range(1,5):
        for step in [-.6,-.2,.2,.6]:
            name=f'cutoff-{cutoff}-shift-{step:+.1f}'
            data=synthetic_dataset()
            for bar in data['bars'][cutoff+1:]:
                for k in ('open','high','low','close'):bar[k]=round(bar[k]+step,2)
            data['id']=dataset_identity(data)
            case=prepare_case(data,'600000.SH',[order('buy',1,'BUY'),order('sell',2,'SELL')],costs())
            result=run_rqalpha(case,python_executable=python,license_acknowledged=True)
            native=run_invest(case)
            checks={}
            for engine,r in [('invest',native),('rqalpha',result)]:
                for key in ('orders','curve','trades'):
                    prefix=[x for x in r[key] if x['date']<=DAYS[cutoff]]
                    expected=[x for x in base[engine][key] if x['date']<=DAYS[cutoff]]
                    checks[engine+'_'+key]=prefix==expected
            evidence={'name':name,'cutoff':DAYS[cutoff],'shift':step,'case':case,'invest':native,'rqalpha':result,'checks':checks}
            save_json(folder/(name+'.json'),evidence)
            rows.append({'name':name,'passed':all(checks.values()),'case_id':digest(case),'checks':checks})
    return rows


def render_index(summary):
    e=lambda value:html.escape(str(value))
    trs=[]
    for row in summary['scenarios']:
        name=row['name']; url='cases/'+name+'.html'
        detail='<a href="'+url+'">逐笔报告</a>' if row['status']!='ERROR' else e(row.get('error',''))
        trs.append('<tr>'+''.join('<td>'+x+'</td>' for x in [e(row['title']),e(row['expected']),e(row['status']),e(row['difference_count']),e('通过' if row['passed'] else '失败'),detail])+'</tr>')
    limit='<p><strong>仅人工合成数据。</strong>使用固定股数意图，而非独立策略信号。日期是声明测试会话，不是官方交易日历。日线开收盘代理事件及整日成交量是回顾性测试假设，不是开盘时真实可知的流动性。没有实盘、未见留出或真实前向观察。</p>'
    return '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Invest 双引擎实验室</title><style>
body{font:16px/1.6 system-ui,sans-serif;background:#f2f5f8;color:#243546;max-width:1160px;margin:36px auto;padding:0 22px}header,section{background:white;padding:28px;border-radius:14px;margin:22px 0}h1{margin:0}p{max-width:1000px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border-bottom:1px solid #dce4eb;padding:12px;text-align:left}a{color:#175a84}.scroll{overflow-x:auto}code{overflow-wrap:anywhere}.metrics{font-size:20px;font-weight:600}small{color:#50677b}</style><header><small>INVEST / RQALPHA / 独立执行 · 合成研究</small><h1>双引擎对照实验室</h1>'''+ '<p class="metrics">'+str(summary['counts']['match'])+' 组一致 · '+str(summary['counts']['diverged'])+' 组分歧 · '+str(summary['counts']['errors'])+' 组运行错误</p><p>验证套件：'+e(summary['status'])+'。套件通过表示观察符合逐项检查，不等于所有引擎结果一致，更不代表可盈利。</p>'+limit+'</header><section><h2>结果与差异</h2><div class="scroll"><table><tr><th>场景</th><th>预期关系</th><th>实际关系</th><th>差异数</th><th>检查</th><th>详情</th></tr>'+''.join(trs)+'</table></div></section><section><h2>可复现与防误判</h2><p>未来日期行情扰动：'+str(summary['robustness']['future_probe_count'])+' 组；重复运行：'+e(summary['robustness']['repeat'])+'；出站网络拦截验证：'+e(summary['robustness']['network_probe'])+'。</p><p>每个子报告保存两边完整意图结果、成交、每日现金/持仓/净值、费用、来源身份与参数；SHA256SUMS.json 可核验整个输出目录。</p><p>RQAlpha 固定源码 <code>'+RQ_COMMIT+'</code>。原始执行与匹配模块未被替换。第三方包的许可与数据许可不因本报告而获得授权。</p></section></html>'


def run_suite(python,output,selected=None):
    definitions=scenarios()
    if selected:
        definitions=[d for d in definitions if d['name']==selected]
        if not definitions:raise ValueError('不存在的场景名称')
    output=Path(output).resolve()
    if output.exists():raise ValueError('输出目录已经存在；为保留历史证据，请使用新的目录')
    if not output.parent.is_dir():raise ValueError('输出父目录不存在')
    output.mkdir();(output/'cases').mkdir();(output/'robustness').mkdir()
    save_json(output/'protocol.json',{'schema':'invest-engine-lab-protocol-v1','scenarios':definitions,'hand_specified_fill_quantities':QUANTITIES,
        'scope':'SYNTHETIC_BROKER_ACCOUNT_COMPARISON','prior_exploratory_corrections':'docs/RQALPHA_RESEARCH.md'})
    rows=[];reports={}
    for definition in definitions:
        name=definition['name'];case=definition['case']
        row=dict(name=name,title=definition['title'],expected=definition['expected_status'],status='ERROR',passed=False,difference_count=0)
        try:
            native=run_invest(case)
            rq=run_rqalpha(case,python_executable=python,license_acknowledged=True)
            report=compare_results(case,native,rq);reports[name]=report
            checks=outcome(name,report,definition)
            row.update(status=report['status'],difference_count=report['difference_count'],passed=all(checks.values()),checks=checks)
            save_json(output/'cases'/(name+'.json'),report)
            (output/'cases'/(name+'.html')).write_text(render_html(report),encoding='utf-8')
        except Exception as exc:
            row['error']=str(exc)[:4000]
            save_json(output/'cases'/(name+'.error.json'),{'case':case,**row})
        rows.append(row)
        print(f"{name}: {row['status']} / {'PASS' if row['passed'] else 'FAIL'}",flush=True)
    robust=dict(future_probe_count=0,repeat='NOT_RUN',network_probe='NOT_RUN');extra_ok=True
    try:
        save_json(output/'robustness/network-probe.json',probe_network(python));robust['network_probe']='PASS'
        if not selected and 'round_trip' in reports:
            base=reports['round_trip'];case=base['case']
            repeat=run_rqalpha(case,python_executable=python,license_acknowledged=True)
            robust['repeat']='PASS' if canonical(repeat)==canonical(base['rqalpha']) else 'FAIL'
            save_json(output/'robustness/repeat.json',{'matched':robust['repeat']=='PASS','result':repeat})
            future=future_probes(python,output/'robustness',base)
            save_json(output/'robustness/future-summary.json',future)
            robust['future_probe_count']=len(future);robust['future_probes_passed']=sum(x['passed'] for x in future)
            extra_ok=robust['repeat']=='PASS' and len(future)==16 and all(x['passed'] for x in future)
        elif not selected:extra_ok=False
    except Exception as exc:
        extra_ok=False;robust['error']=str(exc)[:4000]
    summary=dict(schema='invest-engine-lab-suite-v1',status='PASS' if rows and all(r['passed'] for r in rows) and extra_ok else 'FAIL',
        scenarios=rows,counts={'scenarios':len(rows),'match':sum(r['status']=='MATCH' for r in rows),'diverged':sum(r['status']=='DIVERGED' for r in rows),
        'errors':sum(r['status']=='ERROR' for r in rows),'checks_passed':sum(r['passed'] for r in rows)},robustness=robust,
        real_market_validated=False,all_empirical_gates_passed=False,licensed_real_data_used=False)
    save_json(output/'summary.json',summary)
    (output/'index.html').write_text(render_index(summary),encoding='utf-8')
    save_json(output/'RUN_CONTEXT.json',{'observed_at_utc':datetime.now(timezone.utc).isoformat(),'host_python':sys.version,'platform':platform.platform(),
        'rqalpha_commit':RQ_COMMIT,'runner_source_sha256':hashlib.sha256(Path(__file__).read_text(encoding='utf-8').encode()).hexdigest(),
        'business_records_contain_no_run_timestamp':True,'note':'Source declaration, not a trusted timestamp or signed runtime attestation.'})
    files={p.relative_to(output).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(output.rglob('*')) if p.is_file()}
    save_json(output/'SHA256SUMS.json',files)
    return summary


def main(argv=None):
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rqalpha-python',required=True,help='Absolute Python path in the pinned optional environment')
    ap.add_argument('--acknowledge-rqalpha-license',action='store_true',help='Confirm you have read and may use the upstream LICENSE for this synthetic research')
    ap.add_argument('--output',required=True,help='New directory only; never overwrites')
    ap.add_argument('--scenario',choices=[x['name'] for x in scenarios()])
    args=ap.parse_args(argv)
    if not args.acknowledge_rqalpha_license:ap.error('Explicit RQAlpha license acknowledgement is required')
    try:
        result=run_suite(args.rqalpha_python,args.output,args.scenario)
        print(json.dumps({'status':result['status'],'counts':result['counts'],'robustness':result['robustness']},ensure_ascii=False))
        return 0 if result['status']=='PASS' else 1
    except (ValueError,OSError) as exc:print(str(exc),file=sys.stderr);return 2


if __name__=='__main__':raise SystemExit(main())
