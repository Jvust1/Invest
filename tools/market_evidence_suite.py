"""Generate declared synthetic intake scenarios and auditable offline reports."""
from __future__ import annotations
import argparse
from copy import deepcopy
from html import escape
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from invest.data import dataset_identity
from integrations.market_evidence.intake import audit_bundle, canonical, sha
from integrations.market_evidence.fixtures import AS_OF, fixture, put
from integrations.market_evidence.report import write_report


def build_suite(output: Path) -> dict:
    output=Path(output)
    output.mkdir(parents=True,exist_ok=False)
    cases=[
        ('baseline','完整人工样本','RAW_MAPPING_CHECKED',None),
        ('license_missing','缺少许可材料','RAW_MAPPING_CHECKED','MISSING_LICENSE'),
        ('facts_missing','缺少市场事实','RAW_MAPPING_CHECKED','MARKET_FACTS_MISSING'),
        ('license_expired','过期许可声明','RAW_MAPPING_CHECKED','SCOPE_NOT_SATISFIED'),
        ('price_changed','改价后重算数据指纹','MATCHED_WITH_BLOCKERS','RAW_NORMALIZED_MISMATCH'),
        ('ready_forged','未经依据改成可回测','MATCHED_WITH_BLOCKERS','RAW_NORMALIZED_MISMATCH'),
        ('hash_changed','原始文件内容替换','INVALID_INPUT','ARTIFACT_HASH_MISMATCH'),
        ('truncated','分页未取完','INVALID_INPUT','TRUNCATED_RESPONSE'),
        ('duplicate','重复行情行','INVALID_INPUT','DUPLICATE_PROVIDER_ROW'),
        ('calendar_gap','日历缺少休市自然日','INVALID_INPUT','CALENDAR_NATURAL_DAY_GAP'),
        ('wrong_symbol','证券串号','INVALID_INPUT','SYMBOL_MISMATCH'),
        ('fractional_share','不能精确换算成整数股','INVALID_INPUT','VOLUME_NOT_INTEGER_SHARES'),
        ('factor_changed','复权因子变化','MATCHED_WITH_BLOCKERS','FACTOR_CHANGE_REQUIRES_ACTION_REVIEW'),
        ('late_facts','事实在决策时点之后公布','RAW_MAPPING_CHECKED','FACT_NOT_KNOWN_AT_DECLARED_CUTOFF'),
        ('suspension_conflict','声明停牌却有成交量','RAW_MAPPING_CHECKED','SUSPENSION_VOLUME_CONFLICT'),
        ('rule_gap','规则有效期漏日','RAW_MAPPING_CHECKED','RULE_COVERAGE_GAP'),
        ('rule_overlap','规则有效期重叠','RAW_MAPPING_CHECKED','RULE_COVERAGE_OVERLAP'),
        ('corporate_action','公司行动未被当前引擎支持','RAW_MAPPING_CHECKED','CORPORATE_ACTION_UNSUPPORTED'),
        ('missing_session','开市日缺少行情','MATCHED_WITH_BLOCKERS','MISSING_SESSION_NOT_ASSUMED_SUSPENDED'),
        ('unsafe_path','文件路径越界','INVALID_INPUT','UNSAFE_PATH'),
        ('provider_failure','供应商返回失败','INVALID_INPUT','PROVIDER_REPORTED_FAILURE'),
        ('early_capture','当日行情过早导出','MATCHED_WITH_BLOCKERS','CAPTURE_BEFORE_DECLARED_EOD_CUTOFF'),
    ]
    records=[]
    for name,title,status,expected_code in cases:
        root=output/'inputs'/name
        m=fixture(root,complete=True,candidate=True)
        def raw(n,change):
            value=json.loads((root/m['raw'][n]['path']).read_bytes());change(value)
            m['raw'][n]=put(root,'raw/'+n+'.json',value)
        def fact(change):
            value=json.loads((root/m['market_facts']['path']).read_bytes());change(value)
            m['market_facts']=put(root,'evidence/facts.json',value)
        if name=='license_missing':m['license_review']=None
        if name=='facts_missing':m['market_facts']=None
        if name=='license_expired':m['license_review']['valid_until']='2024-01-09'
        if name in ('price_changed','ready_forged'):
            value=json.loads((root/m['normalized_candidate']['path']).read_bytes())
            if name=='price_changed':value['bars'][0]['close']=10.21
            else:value['audit']['backtest_ready']=True
            value['id']=dataset_identity(value)
            m['normalized_candidate']=put(root,'normalized/candidate.json',value)
        if name=='hash_changed':(root/'raw/daily.json').write_bytes(b'{}')
        if name=='truncated':raw('daily',lambda d:d['data'].update(has_more=True))
        if name=='duplicate':raw('daily',lambda d:d['data']['items'].append(d['data']['items'][0]))
        if name=='calendar_gap':raw('trade_cal',lambda d:d['data']['items'].pop(4))
        if name=='wrong_symbol':raw('daily',lambda d:d['data']['items'][0].__setitem__(0,'000001.SZ'))
        if name=='fractional_share':raw('daily',lambda d:d['data']['items'][0].__setitem__(6,'0.001'))
        if name=='factor_changed':raw('adj_factor',lambda d:d['data']['items'][-1].__setitem__(2,'1.1'))
        if name=='late_facts':fact(lambda f:f['evidence']['fixture'].update(published_at='2024-01-03T12:00:00+08:00'))
        if name=='suspension_conflict':fact(lambda f:f['sessions'][0].update(suspended=True))
        if name=='rule_gap':fact(lambda f:f['rules'].clear())
        if name=='rule_overlap':fact(lambda f:f['rules'].append(deepcopy(f['rules'][0])))
        if name=='corporate_action':fact(lambda f:f['sessions'][0].update(corporate_action=True))
        if name=='missing_session':raw('daily',lambda d:d['data']['items'].pop(0))
        if name=='unsafe_path':m['raw']['daily']['path']='../outside.json'
        if name=='provider_failure':raw('daily',lambda d:d.update(code=2002,msg='NOT A REAL PROVIDER RESPONSE'))
        if name=='early_capture':m['captured_at']='2024-01-08T12:00:00+08:00'
        put(root,'bundle.json',m)
        result=audit_bundle(root,as_of=AS_OF);r=result['report']
        codes=[x['code'] for x in r['issues']+r.get('market_facts',{}).get('issues',[])]
        if r.get('license_review',{}).get('status')=='MISSING':codes.append('MISSING_LICENSE')
        if r.get('license_review',{}).get('status')=='SCOPE_NOT_SATISFIED':codes.append('SCOPE_NOT_SATISFIED')
        ok=r['integrity']==status and (expected_code is None or expected_code in codes) and not r['execution_authorized']
        write_report(result,output/'reports'/'cases'/name,input_root=root)
        records.append({'case':name,'title':title,'expected_integrity':status,'actual_integrity':r['integrity'],
                        'expected_code':expected_code,'observed_codes':codes,'check_passed':ok,'report_id':r['report_id']})
    summary={'schema':'invest-intake-synthetic-suite-v1','cases':records,'passed':sum(r['check_passed'] for r in records),
             'total':len(records),'real_market_data_used':False,'real_license_obtained':False,'provider_calls':0}
    rows=''.join(f'<tr><td><a href="cases/{r["case"]}/index.html">{escape(r["title"])}</a></td><td>{escape(r["actual_integrity"])}</td><td>{"符合预期" if r["check_passed"] else "测试失败"}</td></tr>' for r in records)
    index='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'"><title>Invest · ENG-04A 核验演示</title><style>body{font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif;margin:0;background:#f4f6f8;color:#18313e}main{max-width:1080px;margin:auto;padding:24px}h1{font-size:30px}.notice{padding:16px;background:#fff7e8;border-left:5px solid #c28a23}.scroll{overflow:auto;background:white}table{border-collapse:collapse;width:100%}td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}a{color:#176079}td{overflow-wrap:anywhere}@media(max-width:600px){main{padding:14px}h1{font-size:24px}table{min-width:600px}}</style><main><small>INVEST / ENG-04A</small><h1>真实数据材料核验 · 人工样本演示</h1><p class="notice">全部数据与许可附件都是人工测试材料。本页展示软件如何识别问题，不是取得真实行情、数据授权或投资有效性的证据。</p>'''+f'<h2>{summary["passed"]} / {summary["total"]} 个案例符合预期</h2><p>识别出错误、缺失和不支持状态也属于测试的预期结果，并不代表输入数据可用于交易。</p><div class="scroll"><table><thead><tr><th>案例</th><th>数据转换结果</th><th>断言检查</th></tr></thead><tbody>{rows}</tbody></table></div></main></html>'
    (output/'reports'/'index.html').write_text(index,encoding='utf-8',newline='\n')
    (output/'reports'/'summary.json').write_bytes(canonical(summary))
    assert summary['passed']==summary['total'],summary
    return summary


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    s=build_suite(a.output);print(json.dumps({'passed':s['passed'],'total':s['total'],'synthetic_only':True}))


if __name__=='__main__':main()
