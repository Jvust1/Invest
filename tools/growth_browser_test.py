"""Real-browser interaction checks. Only synthetic fixtures; never a provider."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
from playwright.sync_api import sync_playwright, expect


def exercise(page, base, out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    checks=[]
    def record(label):checks.append(label)
    def nav(name):page.locator('.sidebar [data-view="'+name+'"]').click()
    page.goto(base,wait_until='networkidle')
    expect(page.locator('h1')).to_contain_text('每一个判断')
    record('workbench_root_render')
    page.locator('#demo').click()
    expect(page.locator('#dataset')).not_to_have_value('',timeout=20000)
    expect(page.locator('#source-banner')).to_contain_text('合成演示')
    record('synthetic_dataset_identity_banner')
    nav('data');page.locator('#receipt').click()
    expect(page.locator('#receipt-output')).to_contain_text('license_independently_verified',timeout=20000)
    record('audit_receipt_persisted')
    nav('study');page.locator('#cost-ack').check()
    page.locator('#study-form button[type=submit]').click()
    expect(page.locator('#study-output tbody tr')).to_have_count(18,timeout=60000)
    expect(page.locator('#message')).to_contain_text('失败 0 项')
    record('18_bounded_studies_real_UI')
    with page.expect_download() as got:page.locator('#study-export').click()
    target=out/'browser-synthetic-study.json';got.value.save_as(target)
    data=json.loads(target.read_text(encoding='utf-8'))
    assert data['payload']['summary']['succeeded']==18
    assert data['payload']['protocol']['frozen_holdout_opened'] is False
    record('full_study_export_with_holdout_not_opened')
    page.screenshot(path=str(out/'growth-study.png'),full_page=True)
    nav('review');page.locator('#review-name').fill('Browser synthetic review')
    page.locator('#review-cash').fill('10000');page.locator('#manual-ack').check()
    page.locator('#review-form button[type=submit]').click()
    expect(page.locator('#review-select')).not_to_have_value('',timeout=20000)
    record('manual_review_creation')
    n=0
    def event(kind,fields,day=2):
        nonlocal n
        page.locator('#event-type').select_option(kind)
        page.locator('#event-time').fill(f'2024-01-{day:02d}T16:00:00+08:00')
        page.locator('#event-source').fill('人工合成浏览器测试，无真实交易')
        page.locator('#event-fields').fill(json.dumps(fields))
        page.locator('#event-form button[type=submit]').click()
        n+=1;expect(page.locator('#events-output tbody tr')).to_have_count(n,timeout=20000)
    event('DEPOSIT',{'amount':'1000'})
    event('BUY',{'symbol':'600000.SH','quantity':100,'price':'10','fee':'5'})
    expect(page.locator('#review-output')).to_contain_text('缺少持仓估值')
    record('fill_price_not_invented_as_current_quote')
    event('MARK',{'prices':{'600000.SH':'10'}})
    event('DIVIDEND',{'symbol':'600000.SH','amount':'10'},3)
    event('FEE',{'amount':'2'},3)
    event('MARK',{'prices':{'600000.SH':'11'}},3)
    expect(page.locator('#review-output')).to_contain_text('11103.00')
    record('cashflow_dividend_fees_marked_NAV_11103')
    page.screenshot(path=str(out/'growth-review.png'),full_page=True)
    nav('facts');page.locator('#facts-example').click();page.locator('#facts-enabled').check()
    page.locator('#facts-import').click()
    expect(page.locator('#facts-select')).not_to_have_value('',timeout=20000)
    page.locator('#facts-query').click()
    expect(page.locator('#facts-output')).to_contain_text('"value": "10"')
    record('PIT_hides_future_revision')
    page.locator('#facts-time').fill('2024-06-01T16:00:00+08:00');page.locator('#facts-query').click()
    expect(page.locator('#facts-output')).to_contain_text('"value": "8"')
    record('PIT_selects_available_revision')
    page.locator('#facts-enabled').uncheck();page.locator('#facts-query').click()
    expect(page.locator('#facts-output')).to_contain_text('"core_unaffected": true')
    record('disabled_extension_isolated')
    page.screenshot(path=str(out/'growth-facts.png'),full_page=True)
    nav('archive');page.locator('#refresh-documents').click()
    expect(page.locator('#documents-output tbody tr')).to_have_count(1,timeout=20000)
    with page.expect_download() as got:
        page.locator('#backup-ack').check();page.locator('#backup').click()
    backup=out/'browser-synthetic-private-backup.zip';got.value.save_as(backup)
    assert backup.stat().st_size>100
    record('complete_private_backup_explicit_consent')
    page.reload(wait_until='networkidle');nav('review')
    expect(page.locator('#review-select')).to_contain_text('Browser synthetic review')
    record('reload_account_list_persistence')
    nav('overview');page.set_viewport_size({'width':1440,'height':960})
    page.screenshot(path=str(out/'growth-home.png'),full_page=True)
    page.set_viewport_size({'width':390,'height':844})
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    expect(page.locator('h1')).to_be_visible()
    page.screenshot(path=str(out/'growth-mobile.png'),full_page=True)
    record('mobile_390px_no_horizontal_page_overflow')
    page.set_viewport_size({'width':1400,'height':960})
    page.goto(base+'/legacy',wait_until='networkidle')
    expect(page.locator('#load-demo')).to_be_visible()
    record('legacy_workspace_preserved')
    return checks


def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=Path('delivery/evidence'));args=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    from invest.server import InvestServer
    with tempfile.TemporaryDirectory() as tmp,sync_playwright() as pw:
        server=InvestServer(('127.0.0.1',0),Path(tmp));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        errors=[];browser=None
        try:
            if sys.platform=='win32':browser=pw.chromium.launch(channel='msedge',headless=True)
            else:browser=pw.chromium.launch(headless=True)
            page=browser.new_page(viewport={'width':1400,'height':960});page.on('pageerror',lambda e:errors.append(str(e)))
            checks=exercise(page,f'http://127.0.0.1:{server.server_port}',args.out)
            assert not errors,errors
            (args.out/'growth-browser.json').write_text(json.dumps({'status':'PASS','checks':checks,'javascript_errors':errors,'platform':sys.platform,'network_transport':'real_loopback_HTTP','fixtures':'synthetic_only'},ensure_ascii=False,indent=2),encoding='utf-8')
        finally:
            if browser:browser.close()
            server.shutdown();thread.join(timeout=5);server.server_close()

if __name__=='__main__':main()
