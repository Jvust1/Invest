"""HTTP routing for the five-stage workbench; inherits the host/CSRF guard."""
from . import __version__
from .experiments import audit_receipt, run_study
from .fundamentals import as_of, validate_bundle
from .review import append_event, create_review, snapshot


def dispatch(handler, path, parameter, payload=None):
    server = handler.server
    ws = server.workspace
    if payload is None:
        if path == '/api/workbench/status':
            return handler._reply(200, {'version':__version__,'scope':'OFFLINE_CAPABILITY_CANDIDATE',
                'stages':{'G1':'数据审计与身份回执','G2':'有界实验与独立算术回放','G3':'事件复盘账本与资金流',
                          'G4':'中文工作台与备份恢复','G5':'可关闭的本地PIT事实扩展'},
                'not_accepted':['真实数据许可和完整性','真实三种市场环境与样本外有效性',
                                '持续前向模拟观察','用户Windows实机验收','独立第三方审阅'],
                'broker_connected':False,'real_holdout_opened':False,
                'experiment_tracking':{'enabled':server.experiment_archive is not None,
                    'scope':'local_derivative_archive','included_in_private_backup':False}})
        if path == '/api/workbench/documents':
            kind = parameter('kind', True)
            if kind not in {'study','facts','review','receipt'}:
                raise ValueError('文档类型错误')
            docs = ws.list(kind)
            return handler._reply(200, {'documents':[{'id':d['id'],'kind':kind,'recorded_at':d['recorded_at'],
                'name':d['payload'].get('name',d['payload'].get('source_name',d['id'][:12])),
                'summary':d['payload'].get('summary')} for d in docs], 'listing_limit':100})
        if path == '/api/workbench/document':
            return handler._reply(200, ws.get(parameter('id',True)), attachment='invest-workbench-record.json')
        if path == '/api/workbench/review':
            return handler._reply(200, snapshot(ws,parameter('id',True)))
        raise LookupError('工作台接口不存在')
    if path == '/api/workbench/receipt':
        dataset = server.state.dataset(payload.get('dataset_id'))
        return handler._reply(200,ws.put('receipt',audit_receipt(dataset,payload.get('declaration'))))
    if path == '/api/workbench/study':
        dataset = server.state.dataset(payload.get('dataset_id'))
        if not server.study_lock.acquire(blocking=False):
            return handler._reply(409,{'error':'已有实验正在运行，请保留当前结果后重试'})
        try:
            study = run_study(dataset,payload.get('specification'))
            record = ws.put('study',study)
            # Save the authoritative record before the optional derivative archive.
            if server.experiment_archive is not None:
                return handler._reply(200,dict(record,tracking=server.experiment_archive.archive(record)))
            return handler._reply(200,record)
        finally:
            server.study_lock.release()
    if path == '/api/workbench/track-study':
        if not server.study_lock.acquire(blocking=False):
            return handler._reply(409,{'error':'已有实验正在运行，请保留当前结果后重试'})
        try:
            record = ws.get(payload.get('study_id'),'study')
            status = ({'status':'disabled','study_saved':True} if server.experiment_archive is None
                      else server.experiment_archive.archive(record))
            return handler._reply(200,{'study_id':record['id'],'tracking':status})
        finally:
            server.study_lock.release()
    if path == '/api/workbench/reviews':
        return handler._reply(200,create_review(ws,payload))
    if path == '/api/workbench/event':
        review_id = payload.get('review_id')
        append_event(ws,review_id,payload.get('event_key'),payload.get('event'))
        return handler._reply(200,snapshot(ws,review_id))
    if path == '/api/workbench/facts':
        if payload.get('enabled') is not True:
            raise ValueError('导入扩展前必须明确启用本地PIT事实扩展')
        return handler._reply(200,ws.put('facts',validate_bundle(payload.get('bundle'))))
    if path == '/api/workbench/as-of':
        enabled = payload.get('enabled',False)
        bundle = ws.get(payload.get('bundle_id'),'facts')['payload'] if enabled else {}
        return handler._reply(200,as_of(bundle,payload.get('symbol'),payload.get('as_of'),enabled=enabled))
    raise LookupError('工作台接口不存在')
