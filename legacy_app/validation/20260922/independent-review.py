from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
import http.client, json, threading, unittest
from invest.data import demo_dataset, parse_csv, _identity
from invest.engine import backtest, execute_order
from invest.portfolio import PaperLedger
from invest.server import InvestServer, StateStore

P = {"symbol":"600000.SH", "cost_model_acknowledged":True}

def sample():
    h = "symbol,date,open,high,low,close,volume_shares,suspended,up_limit,down_limit,adj_factor,corporate_action\n"
    rows = [f"600000.SH,2024-01-0{i+2},{10+i},{11+i},{9+i},{10+i},100000,false,20,1,1,false" for i in range(4)]
    return parse_csv(h+"\n".join(rows),source="independent audit fixture",calendar_csv="date\n2024-01-02\n2024-01-03\n2024-01-04\n2024-01-05")

class Review(unittest.TestCase):
    def test_signal_uses_previous_close_next_session(self):
        d=sample(); r=backtest(d,{**P,"fast":1,"slow":2,"slippage_bps":0})
        self.assertEqual(r['trades'][0]['date'],'2024-01-04')
        self.assertEqual(r['trades'][0]['signal_date'],'2024-01-03')
        altered=deepcopy(d); altered['bars'][2]['close']=11
        altered['id']=_identity(altered)
        self.assertEqual(r['trades'][0],backtest(altered,{**P,"fast":1,"slow":2,"slippage_bps":0})['trades'][0])
    def test_future_prices_do_not_rewrite_past(self):
        d=demo_dataset(); a=backtest(d,P); cutoff=d['calendar'][75]
        changed=deepcopy(d)
        for bar in changed['bars']:
            if bar['date']>cutoff:
                for f in ('open','high','low','close','up_limit','down_limit'):bar[f]=round(bar[f]*1.1,2)
        changed['id']=_identity(changed); b=backtest(changed,P)
        self.assertEqual([x for x in a['trades'] if x['date']<=cutoff],[x for x in b['trades'] if x['date']<=cutoff])
        self.assertEqual([x for x in a['curve'] if x['date']<=cutoff],[x for x in b['curve'] if x['date']<=cutoff])
    def test_unknown_states_block(self):
        for field in ('suspended','up_limit','down_limit','adj_factor','corporate_action'):
            d=sample(); d['bars'][0][field]=None;d['id']=_identity(d)
            with self.subTest(field=field),self.assertRaises(ValueError):backtest(d,{**P,'fast':1,'slow':2})
    def test_gap_and_actions_block(self):
        for mode in ('gap','action','factor'):
            d=sample()
            if mode=='gap':d['bars'].pop(1)
            elif mode=='action':d['bars'][1]['corporate_action']=True
            else:d['bars'][1]['adj_factor']=2
            d['id']=_identity(d)
            with self.subTest(mode=mode),self.assertRaises(ValueError):backtest(d,{**P,'fast':1,'slow':2})
    def test_cent_exact_cash_and_tplusone(self):
        d=sample()
        with TemporaryDirectory() as td:
            ledger=PaperLedger(Path(td)/'paper.sqlite'); a=ledger.create_account('review',10000)
            payload={**P,'date':'2024-01-04','side':'BUY','quantity':100,'reason':'review','slippage_bps':0}
            x=ledger.record_trade(a['id'],d,payload)
            self.assertEqual(x['trades'][0]['cash_after_exact'],'8794.99')
            with self.assertRaises(ValueError):ledger.record_trade(a['id'],d,{**payload,'side':'SELL'})
            y=ledger.record_trade(a['id'],d,{**payload,'date':'2024-01-05','side':'SELL'})
            self.assertEqual(y['trades'][-1]['cash_after_exact'],'10089.33')
    def test_history_change_rejected_and_missing_marks_null(self):
        d=sample()
        with TemporaryDirectory() as td:
            ledger=PaperLedger(Path(td)/'paper.sqlite'); a=ledger.create_account('review')
            payload={**P,'date':'2024-01-04','side':'BUY','quantity':100,'reason':'review','slippage_bps':0}
            ledger.record_trade(a['id'],d,payload)
            self.assertIsNone(ledger.snapshot(a['id'])['equity'])
            changed=deepcopy(d);changed['bars'][2]['close']=11;changed['id']=_identity(changed)
            with self.assertRaises(ValueError):ledger.record_trade(a['id'],changed,{**payload,'date':'2024-01-05','side':'SELL'})
    def test_dataset_hash_recomputed(self):
        d=sample();d['bars'][2]['close']=11
        with self.assertRaises(ValueError):backtest(d,{**P,'fast':1,'slow':2})
        with TemporaryDirectory() as td:
            with self.assertRaises(ValueError):StateStore(Path(td)/'state.sqlite').save_dataset(d)
    def test_http_csrf_origin_json_and_finite_values(self):
        with TemporaryDirectory() as td:
            server=InvestServer(('127.0.0.1',0),Path(td));t=threading.Thread(target=server.serve_forever,daemon=True);t.start()
            def request(method,path,body=None,headers=None):
                c=http.client.HTTPConnection('127.0.0.1',server.server_port)
                c.request(method,path,body=body,headers=headers or {});r=c.getresponse();out=(r.status,r.read());c.close();return out
            try:
                code,body=request('GET','/api/config');self.assertEqual(code,200);token=json.loads(body)['csrf_token']
                headers={'Content-Type':'application/json','X-Invest-CSRF':token}
                self.assertEqual(request('POST','/api/accounts','{"name":"r"}',{'Content-Type':'application/json'})[0],403)
                self.assertEqual(request('POST','/api/accounts','{"name":"r"}',{**headers,'Origin':'https://evil.example'})[0],403)
                self.assertEqual(request('POST','/api/accounts','{"name":"r","name":"s"}',headers)[0],400)
                self.assertEqual(request('POST','/api/accounts','{"name":"r","initial_cash":NaN}',headers)[0],400)
                self.assertEqual(request('POST','/api/accounts','{"name":"r","initial_cash":1e309}',headers)[0],400)
            finally:server.shutdown();server.server_close();t.join()

if __name__=='__main__':unittest.main(verbosity=2)
