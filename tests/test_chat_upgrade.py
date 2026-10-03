import copy
from contextlib import closing, redirect_stdout, redirect_stderr
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from invest.chat.catalog import Catalog
from invest.chat.service import InvestService


class PortfolioPrecisionTests(unittest.TestCase):
    def setUp(self):
        self.service=InvestService()
        self.position={'symbol':'SYNTHETIC','quantity':100,'price_cny':'4.00',
                       'quote_date':'2026-09-25','quote_source':'SYNTHETIC'}

    def test_cash_decimal_validation_does_not_round_before_checking(self):
        for cash in ('100.00000000000000000000001','1000000000.00000000001','NaN','Infinity',True,'1e999999'):
            with self.subTest(cash=cash), self.assertRaises(ValueError):
                self.service.portfolio_snapshot(cash,[],'2026-09-28')

    def test_original_price_and_quantity_precision_enforced(self):
        for field,value in [('quantity','1.00000000000000000001'),('quantity','100000000.00000001'),
                            ('price_cny','1.00000000000000000001'),('price_cny','1000000000.00000001')]:
            p=dict(self.position,**{field:value})
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                self.service.portfolio_snapshot('100.00',[p],'2026-09-28')

    def test_exact_large_cent_amounts_and_stable_two_decimal_strings(self):
        p=dict(self.position,quantity=100000000,price_cny='999999999.99')
        r=self.service.portfolio_snapshot('999999999.99',[p],'2026-09-28')
        self.assertEqual(r['invested_cny'],'99999999999000000.00')
        self.assertEqual(r['total_cny'],'100000000998999999.99')
        self.assertEqual(r['cash_cny'],'999999999.99')

    def test_quote_age_relative_to_explicit_asof_and_input_unchanged(self):
        positions=[dict(self.position)]
        before=copy.deepcopy(positions)
        r=self.service.portfolio_snapshot('100.00',positions,'2026-09-28',max_quote_age_days=2)
        self.assertEqual(r['quote_quality']['stale_symbols'],['SYNTHETIC'])
        self.assertEqual(r['positions'][0]['quote_age_calendar_days'],3)
        self.assertEqual(r['total_cny'],'500.00')
        self.assertFalse(r['quote_quality']['source_independently_verified'])
        self.assertEqual(positions,before)

    def test_quote_age_bounds_and_empty_portfolio(self):
        for age in (-1,367,True,7.5,'7'):
            with self.assertRaises(ValueError):self.service.portfolio_snapshot('0',[],'2026-09-28',age)
        r=self.service.portfolio_snapshot('0',[],'2026-09-28',0)
        self.assertEqual(r['total_cny'],'0.00');self.assertEqual(r['quote_quality']['stale_symbols'],[])


class CatalogIntegrityAndPaginationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.catalog=Catalog(Path(self.tmp.name)/'index.sqlite')

    def add(self,n=1):
        return [self.catalog.add(title=f'risk {i:03}',content='SYNTHETIC risk facts',source='drive',
                                url='https://drive.google.com/drive/folders/abcdefghijk') for i in range(n)]

    def test_search_and_fetch_both_reject_tampered_content(self):
        key=self.add()[0]
        with closing(sqlite3.connect(self.catalog.path)) as db:
            with db:db.execute('UPDATE resources SET content=?',('tampered risk facts',))
        for call in (lambda:self.catalog.search('risk'),lambda:self.catalog.fetch(key)):
            with self.assertRaisesRegex(ValueError,'hash mismatch'):call()

    def test_service_reports_local_limit_without_returning_extra_row(self):
        self.add(21)
        r=InvestService(catalog_path=self.catalog.path).search('risk',limit=20)
        self.assertEqual(len(r['results']),20);self.assertTrue(r['limited'])
        self.assertIsInstance(self.catalog.search('risk'),list)

    def test_exact_limit_is_complete(self):
        self.add(20)
        self.assertFalse(self.catalog.search_page('risk',limit=20)['limited'])

    def test_provider_limit_survives_aggregation(self):
        github=Mock();github.list_files.return_value={'results':[{'id':'github:demo','title':'risk'}],'limited':True}
        service=InvestService(github=github)
        r=service.search('risk',source='github',include_live=True,limit=1)
        self.assertEqual(len(r['results']),1);self.assertTrue(r['limited'])

    def test_drive_pagination_marks_listing_incomplete(self):
        drive=Mock();drive.folders=('abcdefghijk',)
        drive.list_files.return_value={'files':[{'id':'drive:one','title':'risk'}],'next_page_token':'next'}
        r=InvestService(drive=drive).search('risk',source='drive',include_live=True)
        self.assertTrue(r['limited']);self.assertFalse(r['complete_drive_scan'])


class UpgradeProtocolTests(unittest.TestCase):
    def test_cli_offline_check_is_not_connection_acceptance(self):
        from invest.chat.mcp_server import main
        output=io.StringIO()
        with patch.dict(os.environ,{},clear=True),redirect_stdout(output),self.assertRaises(SystemExit) as raised:
            main(['--check'])
        self.assertEqual(raised.exception.code,0)
        result=json.loads(output.getvalue())
        self.assertFalse(result['network_attempted']);self.assertFalse(result['chat_acceptance_verified'])

    def test_cli_missing_configured_catalog_fails_and_network_flag_requires_check(self):
        from invest.chat.mcp_server import main
        with tempfile.TemporaryDirectory() as folder:
            with patch.dict(os.environ,{'INVEST_CATALOG_PATH':str(Path(folder)/'missing.sqlite')},clear=True),redirect_stdout(io.StringIO()),self.assertRaises(SystemExit) as raised:
                main(['--check'])
            self.assertEqual(raised.exception.code,1)
        with redirect_stderr(io.StringIO()),self.assertRaises(SystemExit) as raised:
            main(['--check-network'])
        self.assertEqual(raised.exception.code,2)

    def test_http_calls_both_new_tools_with_structured_outputs(self):
        from starlette.testclient import TestClient
        from invest.chat.mcp_server import build_server
        headers={'Accept':'application/json, text/event-stream'}
        with patch.dict(os.environ,{},clear=True),TestClient(build_server().streamable_http_app()) as client:
            def call(i,name,args):
                result=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':i,'method':'tools/call','params':{'name':name,'arguments':args}})
                self.assertEqual(result.status_code,200)
                return result.json()['result']
            diagnostic=call(1,'connection_check',{})
            self.assertFalse(diagnostic['isError']);self.assertFalse(diagnostic['structuredContent']['network_attempted'])
            report=call(2,'analyze_price_series',{'symbol':'SYNTHETIC','currency':'CNY','source':'SYNTHETIC',
                 'as_of':'2026-09-28','bars':[{'date':'2026-09-25','open':10,'high':12,'low':9,'close':11}]})
            self.assertFalse(report['isError']);self.assertEqual(report['structuredContent']['status'],'CALLER_SUPPLIED')
            self.assertFalse(report['structuredContent']['execution_authorized'])
            bad=call(3,'analyze_price_series',{'symbol':'SYNTHETIC','currency':'CNY','source':'SYNTHETIC',
                 'as_of':'2026-09-28','bars':[{'date':'2026-09-25','open':10,'high':8,'low':9,'close':11}]})
            self.assertTrue(bad['isError'])


if __name__=='__main__':unittest.main()
