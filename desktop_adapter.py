from pathlib import Path
import json
import threading
from urllib.request import build_opener, ProxyHandler
from invest.server import InvestServer
from invest.backup import export_backup, restore_backup

NAME='Invest'
TITLE='Invest · 人民币研究工作台'
DESCRIPTION='行情导入 → 数据检查 → 含成本回测 → 模拟账本与研究笔记。没有券商连接，不执行实盘交易。'
BOUNDARY='默认行情为合成演示；真实数据、授权与样本外评估需要单独验证。'

class Service:
    def __init__(self,server):
        self.server=server;self.url=f'http://127.0.0.1:{server.server_port}'
        self.health_url=self.url+'/api/config'
        self.thread=threading.Thread(target=server.serve_forever,daemon=True);self.thread.start()
    def close(self):
        self.server.shutdown();self.thread.join(timeout=10);self.server.server_close()


def start(home,root,intake=False):
    return Service(InvestServer(('127.0.0.1',0),Path(home)/'data'))


def self_test(home,root):
    from invest.data import demo_dataset
    svc=start(home,root)
    try:
        opener=build_opener(ProxyHandler({}))
        with opener.open(svc.url,timeout=10) as response:
            assert b'Invest' in response.read()
        dataset=svc.server.state.save_dataset(demo_dataset())
        key=dataset['id']
        backup=export_backup(home/'data')
        recovered=restore_backup(backup,home/'recovered')
    finally: svc.close()
    server=InvestServer(('127.0.0.1',0),recovered)
    try:
        assert server.state.dataset(key)['id']==key
    finally: server.server_close()
    return {'ok':True,'checks':['HTTP home','real SQLite dataset write','complete local backup','new-folder restore','dataset identity after restart'], 'provider_calls':0, 'broker_calls':0}


def backup(home):
    return export_backup(Path(home)/'data')


def restore(raw,home):
    return restore_backup(raw,Path(home)/'data')
