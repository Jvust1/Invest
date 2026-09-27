"""Local HTML/JSON report writer. Does not copy raw or license evidence bodies."""
from __future__ import annotations
from html import escape
import json
from pathlib import Path

from .intake import canonical, require, sha

LABELS = {
    'RAW_MAPPING_CHECKED':'原始字段转换已核对', 'MATCHED_WITH_BLOCKERS':'转换已检查，仍有数据阻塞',
    'INVALID_INPUT':'输入拒绝，未生成可用数据', 'MATCH':'逐字段一致', 'MISMATCH':'发现差异',
    'NOT_SUPPLIED':'未提供待对照数据集', 'MISSING':'缺少材料',
    'DECLARED_SCOPE_MATCH':'声明范围匹配，未独立验证授权', 'SCOPE_NOT_SATISFIED':'许可声明范围不满足',
    'CLAIM_STRUCTURE_CONSISTENT':'事实声明结构一致，未独立核实',
    'INCOMPLETE_OR_CONFLICTING':'事实缺失或有冲突', 'SYNTHETIC_FIXTURE_ONLY':'仅人工合成测试',
    'EVIDENCE_INCOMPLETE':'证据尚不完整', 'AWAITING_INDEPENDENT_REVIEW':'等待独立审阅',
    'synthetic_fixture':'人工合成样本', 'provider_export':'用户声明的供应商导出（真实性未认证）',
}


def label(value):
    return escape(LABELS.get(value,value))


def html_report(report: dict) -> str:
    summary = [('样本来源',report.get('origin','UNREAD')),('转换核验',report['integrity']),
               ('规范化对照',report.get('candidate_comparison',{}).get('status','NOT_SUPPLIED')),
               ('许可材料',report.get('license_review',{}).get('status','MISSING')),
               ('市场事实',report.get('market_facts',{}).get('status','MISSING')),
               ('审阅阶段',report.get('review_state','EVIDENCE_INCOMPLETE'))]
    cards = ''.join(f'<div class="card"><small>{escape(k)}</small><strong>{label(v)}</strong></div>' for k,v in summary)
    issues = report.get('issues',[]) + report.get('market_facts',{}).get('issues',[])
    differences = report.get('candidate_comparison',{}).get('differences',[])
    rows = ''.join('<tr><td>'+escape(str(x.get('date','—')) or '—')+'</td><td>'+escape(x['code'])+'</td></tr>' for x in issues)
    diffrows = ''.join('<tr><td>'+escape(x.get('section',''))+'</td><td>'+escape(x.get('date','—'))+'</td><td>'+escape(x.get('field',''))+'</td></tr>' for x in differences)
    lineage = []
    for row in report.get('lineage',[]):
        details = '; '.join(f"{t['field']} ← {t['endpoint']}.items[{t['item_index']}].{t['input_field']} ({t['transform']})" for t in row['fields'])
        lineage.append(f'<tr><td>{escape(row["date"])}</td><td>{row["normalized_csv_line"]}</td><td>{escape(details)}</td></tr>')
    return f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'none'; base-uri 'none'">
<title>Invest · 真实数据材料核验</title><style>
*{{box-sizing:border-box}}body{{margin:0;background:#f4f6f8;color:#18313e;font:16px/1.6 system-ui,"Microsoft YaHei",sans-serif}}
main{{max-width:1140px;margin:auto;padding:32px 24px}}h1{{font-size:32px;line-height:1.25;margin:12px 0}}h2{{margin-top:32px;font-size:23px}}
.notice{{border-left:5px solid #c28a23;padding:16px;background:#fff7e8}}.grid{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:24px 0}}
.card{{background:white;border:1px solid #dce4e8;border-radius:10px;padding:18px}}small{{color:#56707c;display:block}}strong{{display:block;margin-top:8px;font-size:18px}}
.scroll{{overflow-x:auto;max-width:100%;border:1px solid #dce4e8;border-radius:8px;background:white}}table{{border-collapse:collapse;width:100%}}td,th{{text-align:left;vertical-align:top;padding:12px 16px;border-bottom:1px solid #e4eaed}}th{{background:#edf3f5}}td{{overflow-wrap:anywhere}}.hash{{font:12px/1.6 monospace;overflow-wrap:anywhere}}a{{color:#176079}}
.trace th:first-child,.trace td:first-child{{min-width:125px;white-space:nowrap}}
@media(max-width:700px){{main{{padding:18px 14px}}h1{{font-size:26px}}.grid{{grid-template-columns:1fr}}.trace{{min-width:700px}}}}
</style><main><small>INVEST / ENG-04A · LOCAL DATA INTAKE</small><h1>原始数据与证据核验</h1>
<p class="notice">本报告不认证真实行情或数据许可，也不授权交易。执行字段保持未知；没有券商调用，没有打开留出集。<br>来源：{label(report.get('origin','UNREAD'))}</p>
<div class="grid">{cards}</div><p>逐行检查证券、日期、OHLC、手/股换算、复权因子和涨跌停价。许可与市场事实分别显示，不把结构完整当作已授权。</p>
<h2>数据与事实问题 · {len(issues)}</h2><div class="scroll"><table><thead><tr><th>日期</th><th>诊断代码</th></tr></thead><tbody>{rows or '<tr><td colspan="2">没有发现该检查范围内的冲突；不代表真实来源与授权已核实。</td></tr>'}</tbody></table></div>
<h2>待对照数据集差异 · {len(differences)}</h2><div class="scroll"><table><thead><tr><th>部分</th><th>日期</th><th>字段</th></tr></thead><tbody>{diffrows or '<tr><td colspan="3">没有列出的差异。请同时查看上方对照状态，未提供数据集不算对照通过。</td></tr>'}</tbody></table></div>
<h2>逐行来源追踪 · {len(lineage)}</h2><div class="scroll"><table class="trace"><thead><tr><th>日期</th><th>CSV行号</th><th>原始响应位置与转换</th></tr></thead><tbody>{''.join(lineage)}</tbody></table></div>
<p>items 从0计数，CSV行号包括表头。完整原始文件SHA-256见 report.json。停牌/公司行动不会从行情缺行或复权因子不变推定为否。</p>
<h2>保存与继续</h2><p>原始响应、许可正文和事实附件没有复制到本报告目录。规范化数据仍属于本机研究材料，分享前须独立检查数据权利与隐私。</p>
<p><a href="report.json">查看机器可读核验记录</a></p><p class="hash">报告身份：{escape(report['report_id'])}</p></main></html>'''


def write_report(result: dict, output: Path, *, input_root: Path | None = None) -> None:
    """Create a new report directory. Refuse any existing target or input subtree."""
    output = Path(output)
    if input_root is not None:
        require(not output.resolve().is_relative_to(Path(input_root).resolve()),'OUTPUT_INSIDE_INPUT')
    require(not output.exists() and not output.is_symlink(),'OUTPUT_EXISTS')
    payloads = dict(result['artifacts'])
    payloads.update({'report.json':canonical(result['report']), 'RUN_CONTEXT.json':canonical(result['context']),
                     'index.html':html_report(result['report']).encode('utf-8')})
    sums = {name:{'sha256':sha(raw),'bytes':len(raw)} for name,raw in sorted(payloads.items())}
    payloads['SHA256SUMS.json']=canonical(sums)
    output.mkdir(parents=True,exist_ok=False)
    (output/'.incomplete').write_text('Report write has not completed.\n',encoding='utf-8')
    for name,raw in payloads.items():
        with (output/name).open('xb') as f:
            f.write(raw)
    (output/'.incomplete').unlink()
