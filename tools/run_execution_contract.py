"""Execute sealed ENG-03 profiles and retain unsupported policy outcomes.

Source-only, synthetic-only extension. Existing desktop and v1 suite unchanged.
"""
from __future__ import annotations
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import platform
import sys

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from integrations.execution_contract import model as m
from integrations.execution_contract.scenarios import definitions, GOLDEN
from tools.run_engine_lab import QUANTITIES, probe_network

LABELS={'strict-partial-v1':'保守 · 部分成交','strict-aon-v1':'保守 · 整笔成交或拒绝','native-parity-v1':'原生兼容 · 显式选择'}


def save(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def expected_quantities(name,profile):
    if name in GOLDEN:return GOLDEN[name][profile]
    left,right=QUANTITIES[name]
    if profile=='native-parity-v1':return right
    if name=='day_volume_reuse':return [100,0]
    if name=='partial_volume' and profile=='strict-partial-v1':return [100]
    return left


def page(title,body):
    e=html.escape
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+e(title)+'</title><style>body{font:16px/1.65 system-ui,sans-serif;color:#213344;background:#f2f5f8;max-width:1180px;margin:32px auto;padding:0 20px}header,section{background:white;border-radius:14px;padding:24px;margin:20px 0}h1{margin:4px 0 16px}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:10px;border-bottom:1px solid #d9e0e7;text-align:left}.scroll{overflow-x:auto}code{overflow-wrap:anywhere}a{color:#165681}.notice{border-left:4px solid #aa741b;padding-left:14px}.metrics{font-size:22px;font-weight:650}pre{white-space:pre-wrap;overflow-wrap:anywhere}@media(max-width:600px){body{padding:0 12px}section,header{padding:16px}h1{font-size:25px}}</style>'+body+'</html>'


def render_case(row,report):
    e=lambda v:html.escape(str(v))
    body='<header><a href="../index.html">返回总览</a><h1>'+e(row['title'])+'</h1><p>'+e(LABELS[row['profile']])+' · '+e(row['status'])+'</p><p class="notice">仅合成规则验证。保守规则未获 RQAlpha 原生支持时不启动引擎；不能把规则不支持写成结果一致。</p></header>'
    if report.get('reference'):
        ref=report['reference']; native=report.get('native',{})
        body+='<section><h2>规则与输入身份</h2><p>规则 <code>'+e(ref['contract_id'])+'</code></p><p>请求 <code>'+e(ref['request_id'])+'</code></p></section>'
        trs=''.join('<tr>'+''.join('<td>'+e(t[k])+'</td>' for k in ('id','date','session_capacity','used_before','filled','used_after','remaining_after','cancelled_quantity'))+'</tr>' for t in ref['capacity_trace'])
        body+='<section><h2>参考执行器共享容量账本</h2><div class="scroll"><table><tr><th>意图</th><th>会话日期</th><th>容量</th><th>已用</th><th>本次成交</th><th>累计使用</th><th>剩余</th><th>取消余量</th></tr>'+trs+'</table></div><p>账本由逐笔成交推导，不冒充第三方引擎的内部遥测。</p></section>'
        if native.get('status')=='UNSUPPORTED_CONTRACT':
            trs=''.join('<tr><td>'+e(d['rule'])+'</td><td>'+e(d['requested'])+'</td><td>'+e(d['native_supported'])+'</td></tr>' for d in native['compatibility']['differences'])
            body+='<section><h2>原生规则不支持：未运行</h2><div class="scroll"><table><tr><th>规则</th><th>要求</th><th>原生路径支持</th></tr>'+trs+'</table></div></section>'
        else:
            body+='<section><h2>原生结果</h2><p>实际 RQAlpha 与参考规则逐日、逐单、分项费用比较：'+e(report['status'])+'。</p><p>本次原始差异数量：'+e(report.get('comparison',{}).get('difference_count','未执行'))+'；原始观察不会被四舍五入覆盖。</p></section>'
    if report.get('error'):body+='<section><h2>输入或运行诊断</h2><pre>'+e(report['error'])+'</pre></section>'
    body+='<section><h2>完整记录</h2><p><a href="'+e(row['file'])+'.json">查看逐筆 JSON</a></p><p>不包含真实行情、实盘订单、样本外有效性或连续前向观察。</p></section>'
    return page('Invest 成交合同 · '+row['title'],body)


def render_index(summary):
    e=lambda v:html.escape(str(v))
    counts=summary['counts']
    rows=''.join('<tr><td>'+e(r['title'])+'</td><td>'+e(LABELS[r['profile']])+'</td><td>'+e(r['status'])+'</td><td>'+('通过' if r['passed'] else '失败')+'</td><td><a href="cases/'+e(r['file'])+'.html">规则详情</a></td></tr>' for r in summary['scenarios'])
    body='<header><small>INVEST / ENG-03 / 版本化成交合同</small><h1>同一份订单，明确同一套规则</h1><p class="metrics">'+e(counts['native_match'])+' 组原生一致 · '+e(counts['unsupported'])+' 组原生规则不支持 · '+e(counts['input_rejected'])+' 组输入拒绝</p><p>检查结论：'+e(summary['status'])+'。不支持和输入拒绝不计入一致数量。</p><p class="notice">仅合成、单证券、固定股数验证。默认保守规则不等于原生兼容规则；兼容规则可能保留分以下费用或不按价格最小单位取整，不应直接用于真实交易。</p></header>'
    body+='<section><h2>三个明确版本，不再混用默认值</h2><p><strong>保守部分成交：</strong>共享容量，允许部分成交，余单取消，分项费用到分、价格不利方向取整并检查 OHLC。<br><strong>保守整笔规则：</strong>共用同一容量，但不足时整笔拒绝。<br><strong>原生兼容规则：</strong>显式选择原生成交与精度政策，零过户费；匹配器不被替换。</p><p>旧版 v1 六类分歧完整保留，新协议另存身份和结果。</p></section>'
    body+='<section><h2>逐项证据</h2><div class="scroll"><table><tr><th>场景</th><th>规则版本</th><th>结果</th><th>逐项检查</th><th>详情</th></tr>'+rows+'</table></div></section>'
    body+='<section><h2>稳健性与边界</h2><p>未来日期扰动 '+e(summary['robustness']['future_probes'])+' 组；重复运行 '+e(summary['robustness']['repeat'])+'；出站网络探测 '+e(summary['robustness']['network'])+'。</p><p>整日成交量是事后声明的合成边界，不是开盘可知流动性。没有真实数据许可验收、公司行动、独立信号、留出验证或前向观察。</p><p>完整规则、源码、JSON 与校验清单随包保存。不更新原 Windows EXE。</p></section>'
    return page('Invest 版本化成交合同',body)


def run_suite(python,output):
    output=Path(output).resolve()
    if output.exists() or not output.parent.is_dir():raise ValueError('Use a new output directory under an existing parent; no overwrite')
    output.mkdir();(output/'cases').mkdir();(output/'robustness').mkdir()
    defs=definitions();rows=[];native_base=None
    save(output/'protocol.json',{'schema':'invest-contract-suite-protocol-v2','profiles':[m.profile(n) for n in m.PROFILE_NAMES],
        'scenarios':defs,'hand_quantities':{d['name']:{n:expected_quantities(d['name'],n) for n in m.PROFILE_NAMES} for d in defs},
        'deliberate_input_rejection':['transfer_fee/native-parity-v1'],'fixed_before_run':True})
    for definition in defs:
        for profile in m.PROFILE_NAMES:
            row={'name':definition['name'],'title':definition['title'],'profile':profile,
                 'file':definition['name']+'--'+profile,'status':'ERROR','passed':False}
            report={}
            try:
                request=m.prepare_request(definition['case'],profile)
                ref=m.run_reference(request)
                native=m.run_native(request,python_executable=python,license_acknowledged=True)
                report=m.compare(request,ref,native)
                checks={'reference_golden_quantities':[o['filled_quantity'] for o in ref['execution']['orders']]==expected_quantities(definition['name'],profile)}
                if profile=='native-parity-v1':
                    checks['native_golden_quantities']=[o['filled_quantity'] for o in native['execution']['orders']]==expected_quantities(definition['name'],profile)
                    checks['native_match']=report['status']=='MATCH'
                    if definition['name']=='round_trip':native_base=report
                else:checks['unsupported_not_silently_downgraded']=report['status']=='UNSUPPORTED_CONTRACT' and native['execution'] is None
                row.update(status=report['status'],checks=checks,passed=all(checks.values()))
            except Exception as exc:
                allowed=definition['name']=='transfer_fee' and profile=='native-parity-v1' and 'transfer_fee_rate=0' in str(exc)
                row.update(status='INPUT_REJECTED' if allowed else 'ERROR',passed=allowed,error=str(exc))
                report={'error':str(exc),'input':definition['case'],'profile':profile,'status':row['status']}
            save(output/'cases'/(row['file']+'.json'),report)
            (output/'cases'/(row['file']+'.html')).write_text(render_case(row,report),encoding='utf-8')
            rows.append(row);print(row['file']+': '+row['status'],flush=True)
    robust={'future_probes':0,'repeat':'NOT_RUN','network':'NOT_RUN','passed':False}
    try:
        probe=probe_network(python);save(output/'robustness/network.json',probe);robust['network']='PASS'
        if native_base is None:raise ValueError('Base native run absent')
        repeated=m.run_native(native_base['request'],python_executable=python,license_acknowledged=True)
        robust['repeat']='PASS' if repeated==native_base['native'] else 'FAIL'
        save(output/'robustness/repeat.json',{'matched':robust['repeat']=='PASS','result':repeated})
        probes=[]
        for cutoff in (1,2,3,4):
            for shift in (-.4,.4):
                request=deepcopy(native_base['request'])
                for bar in request['case']['bars'][cutoff+1:]:
                    for key in ('open','high','low','close'):bar[key]=round(bar[key]+shift,2)
                ref=m.run_reference(request);rq=m.run_native(request,python_executable=python,license_acknowledged=True)
                checks={};day=request['case']['bars'][cutoff]['date']
                for name, result, baseline in [('reference',ref,native_base['reference']),('native',rq,native_base['native'])]:
                    for key in ('orders','trades','curve'):
                        checks[name+'_'+key]=[x for x in result['execution'][key] if x['date']<=day]==[x for x in baseline['execution'][key] if x['date']<=day]
                    checks[name+'_capacity']=[x for x in result['capacity_trace'] if x['date']<=day]==[x for x in baseline['capacity_trace'] if x['date']<=day]
                evidence={'request':request,'reference':ref,'native':rq,'cutoff':day,'checks':checks,'passed':all(checks.values())}
                save(output/'robustness'/f'future-{cutoff}-{shift:+.1f}.json',evidence);probes.append(evidence['passed'])
        robust.update(future_probes=len(probes),future_passed=sum(probes),passed=all(probes) and robust['repeat']=='PASS')
    except Exception as exc:robust['error']=str(exc)
    counts={'scenarios':len(rows),'native_match':sum(r['status']=='MATCH' for r in rows),
            'unsupported':sum(r['status']=='UNSUPPORTED_CONTRACT' for r in rows),'input_rejected':sum(r['status']=='INPUT_REJECTED' for r in rows),
            'errors':sum(r['status']=='ERROR' for r in rows),'checks_passed':sum(r['passed'] for r in rows)}
    summary={'schema':'invest-contract-suite-v2','status':'PASS' if all(r['passed'] for r in rows) and robust['passed'] else 'FAIL',
             'scenarios':rows,'counts':counts,'robustness':robust,'real_market_validated':False,'new_exe':False}
    save(output/'summary.json',summary);(output/'index.html').write_text(render_index(summary),encoding='utf-8')
    save(output/'RUN_CONTEXT.json',{'observed_at':datetime.now(timezone.utc).isoformat(),'platform':platform.platform(),
                                  'python':sys.version,'reference_identity':m.reference_identity(),'legacy_worker_unchanged':True})
    save(output/'SHA256SUMS.json',{p.relative_to(output).as_posix():{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(output.rglob('*')) if p.is_file()})
    return summary


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rqalpha-python',required=True);parser.add_argument('--output',required=True)
    parser.add_argument('--acknowledge-rqalpha-license',action='store_true')
    args=parser.parse_args(argv)
    if not args.acknowledge_rqalpha_license:parser.error('Read the upstream license and explicitly acknowledge permitted use')
    summary=run_suite(args.rqalpha_python,args.output)
    print(json.dumps({'status':summary['status'],'counts':summary['counts'],'robustness':summary['robustness']},ensure_ascii=False))
    return 0 if summary['status']=='PASS' else 1

if __name__=='__main__':raise SystemExit(main())
