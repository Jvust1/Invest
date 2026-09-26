"""Check the generated offline HTML report with a real browser; no web server."""
import argparse
import json
import os
import shutil
from pathlib import Path


def main(argv=None):
    p=argparse.ArgumentParser();p.add_argument('--report-dir',required=True);p.add_argument('--evidence',required=True);p.add_argument('--executable')
    args=p.parse_args(argv)
    from playwright.sync_api import sync_playwright
    root=Path(args.report_dir).resolve();out=Path(args.evidence).resolve();out.mkdir(parents=True,exist_ok=False)
    summary=json.loads((root/'summary.json').read_text(encoding='utf-8'))
    errors=[];checks=[];remote=[]
    with sync_playwright() as pw:
        options={'headless':True}
        executable=args.executable
        if not executable:
            candidates=[shutil.which('google-chrome'),shutil.which('chromium'),r'C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe',r'C:\Program Files\Microsoft\Edge\Application\msedge.exe']
            executable=next((x for x in candidates if x and Path(x).is_file()),None)
        if executable:options['executable_path']=executable
        browser=pw.chromium.launch(**options)
        page=browser.new_page(viewport={'width':1280,'height':960})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:remote.append(r.url) if r.url.startswith(('http:','https:')) else None)
        page.goto((root/'index.html').as_uri())
        assert page.title()=='Invest 双引擎实验室';checks.append('index_title')
        assert page.locator('h1').inner_text()=='双引擎对照实验室';checks.append('visible_heading')
        assert page.locator('table tr').count()==summary['counts']['scenarios']+1;checks.append('all_scenario_rows')
        assert page.get_by_role('link',name='逐笔报告').count()==summary['counts']['scenarios'];checks.append('all_report_links')
        assert '6 组分歧' in page.locator('body').inner_text();checks.append('divergence_visible')
        page.screenshot(path=str(out/'engine-lab-home.png'),full_page=True)
        for row in summary['scenarios']:
            page.goto((root/'index.html').as_uri())
            page.locator('a[href="cases/'+row['name']+'.html"]').click()
            assert row['status'] in page.locator('h1').inner_text()
            assert '仅合成验证' in page.locator('body').inner_text()
            checks.append('link_and_status_'+row['name'])
        page.goto((root/'cases/partial_volume.html').as_uri());page.screenshot(path=str(out/'engine-lab-differences.png'),full_page=True)
        page.set_viewport_size({'width':390,'height':844});page.goto((root/'index.html').as_uri())
        assert page.locator('h1').is_visible();checks.append('mobile_heading')
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');checks.append('no_page_horizontal_overflow')
        page.screenshot(path=str(out/'engine-lab-mobile.png'),full_page=True)
        assert not errors;checks.append('no_javascript_errors')
        assert not remote;checks.append('no_external_requests')
        browser.close()
    (out/'browser-result.json').write_text(json.dumps({'status':'PASS','checks':checks,'count':len(checks),'errors':errors,'external_requests':remote},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','checks':len(checks)}))


if __name__=='__main__':main()
