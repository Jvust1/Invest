"""Actual file-navigation browser checks for the offline intake reports."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from playwright.sync_api import sync_playwright


def main():
    p=argparse.ArgumentParser();p.add_argument('--reports',required=True,type=Path);p.add_argument('--output',required=True,type=Path)
    a=p.parse_args();root=a.reports.resolve();a.output.mkdir(parents=True,exist_ok=False)
    expected=json.loads((root/'summary.json').read_bytes())
    checks=[];errors=[];external=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(headless=True)
        page=browser.new_page(viewport={'width':1280,'height':900})
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:external.append(r.url) if r.url.startswith(('http:','https:')) else None)
        def check(name,ok):
            checks.append({'check':name,'passed':bool(ok)});assert ok,name
        page.goto((root/'index.html').as_uri())
        check('index',page.locator('h1').inner_text()=='真实数据材料核验 · 人工样本演示')
        check('case_links',page.locator('tbody a').count()==expected['total'])
        check('synthetic_notice','人工测试材料' in page.locator('.notice').inner_text())
        page.screenshot(path=str(a.output/'intake-home.png'))
        for item in expected['cases']:
            page.goto((root/'index.html').as_uri())
            page.get_by_role('link',name=item['title'],exact=True).click()
            check(item['case']+'_navigation',page.locator('h1').inner_text()=='原始数据与证据核验')
            check(item['case']+'_no_execution','不授权交易' in page.locator('.notice').inner_text())
            check(item['case']+'_json_link',page.locator('a[href="report.json"]').count()==1)
        page.goto((root/'cases'/'price_changed'/'index.html').as_uri())
        check('changed_price_is_visible','close' in page.locator('body').inner_text())
        page.screenshot(path=str(a.output/'intake-price-difference.png'),full_page=True)
        page.goto((root/'cases'/'baseline'/'index.html').as_uri())
        check('lineage_rows',page.locator('.trace tbody tr').count()==5)
        page.get_by_role('link',name='查看机器可读核验记录').click()
        check('json_navigation',page.url.endswith('/report.json') and 'report_id' in page.locator('body').inner_text())
        page.set_viewport_size({'width':390,'height':844})
        page.goto((root/'cases'/'baseline'/'index.html').as_uri())
        check('mobile_no_body_overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth+1'))
        check('wide_trace_locally_scrolls',page.locator('.trace').evaluate('(e)=>e.parentElement.scrollWidth>e.parentElement.clientWidth'))
        check('mobile_dates_do_not_fragment',page.locator('.trace tbody td').first.evaluate("(e)=>getComputedStyle(e).whiteSpace==='nowrap'"))
        page.screenshot(path=str(a.output/'intake-mobile.png'),full_page=True)
        check('no_javascript_errors',not errors);check('no_external_requests',not external)
        browser.close()
    result={'checks':checks,'count':len(checks),'errors':errors,'external_requests':external,'all_passed':all(c['passed'] for c in checks)}
    (a.output/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'checks':len(checks),'all_passed':result['all_passed']}))


if __name__=='__main__':main()
