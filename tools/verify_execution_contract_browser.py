"""Browser smoke for generated ENG-03 reports; no web service or external assets."""
import argparse
import json
from pathlib import Path
import shutil


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--report-dir',required=True);p.add_argument('--evidence',required=True)
    args=p.parse_args(argv);root=Path(args.report_dir).resolve();out=Path(args.evidence).resolve()
    out.mkdir(parents=True,exist_ok=False)
    summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    from playwright.sync_api import sync_playwright
    errors=[];external=[];checks=[]
    with sync_playwright() as pw:
        candidates=[shutil.which('chromium'),shutil.which('google-chrome'),r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']
        exe=next((x for x in candidates if x and Path(x).is_file()),None)
        options={'headless':True}
        if exe:options['executable_path']=exe
        browser=pw.chromium.launch(**options);page=browser.new_page(viewport={'width':1280,'height':960})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) else None)
        page.goto((root/'index.html').as_uri());assert page.title()=='Invest 版本化成交合同';checks.append('title')
        assert page.locator('h1').inner_text()=='同一份订单，明确同一套规则';checks.append('heading')
        assert page.get_by_role('link',name='规则详情').count()==summary['counts']['scenarios'];checks.append('all_links')
        assert f"{summary['counts']['native_match']} 组原生一致" in page.locator('body').inner_text();checks.append('true_native_count')
        assert f"{summary['counts']['unsupported']} 组原生规则不支持" in page.locator('body').inner_text();checks.append('unsupported_separate')
        page.screenshot(path=str(out/'contract-home.png'))
        for row in summary['scenarios']:
            page.goto((root/'cases'/(row['file']+'.html')).as_uri())
            assert row['status'] in page.locator('body').inner_text()
            assert '仅合成规则验证' in page.locator('body').inner_text()
            assert page.get_by_role('link',name='返回总览').count()==1
            checks.append('detail_'+row['file'])
        page.goto((root/'cases/day_volume_reuse--strict-partial-v1.html').as_uri())
        assert page.locator('table').first.locator('tr').count()==3;checks.append('capacity_trace_rows')
        page.screenshot(path=str(out/'contract-shared-capacity.png'),full_page=True)
        page.get_by_role('link',name='返回总览').click();assert page.title()=='Invest 版本化成交合同';checks.append('back_link')
        page.set_viewport_size({'width':390,'height':844})
        assert page.locator('h1').is_visible();checks.append('mobile_heading')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth');checks.append('no_mobile_page_overflow')
        page.screenshot(path=str(out/'contract-mobile.png'))
        assert not errors;checks.append('no_js_errors')
        assert not external;checks.append('no_external_requests')
        browser.close()
    (out/'browser-result.json').write_text(json.dumps({'status':'PASS','checks':checks,'count':len(checks),'errors':errors,'external_requests':external},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','checks':len(checks)}))

if __name__=='__main__':main()
