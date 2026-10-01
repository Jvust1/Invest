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
            if kind not in {'study','facts','review','receipt','native_research'}:
                raise ValueError('文档类型错误')
            if kind == 'native_research':
                return handler._reply(200, {'documents': ws.list_summaries(kind), 'listing_limit':100,
                    'validation':'content_identity_only; full_native_replay_on_download'})
            docs = ws.list(kind)
            return handler._reply(200, {'documents':[{'id':d['id'],'kind':kind,'recorded_at':d['recorded_at'],
                'name':d['payload'].get('name',d['payload'].get('source_name',d['id'][:12])),
                'summary':d['payload'].get('summary')} for d in docs], 'listing_limit':100})
        if path == '/api/workbench/document':
            record = ws.get(parameter('id',True))
            if record['kind'] == 'native_research':
                from .native_research import validate_native_record
                if not server.study_lock.acquire(blocking=False):
                    return handler._reply(409, {'error':'已有研究计算或校验正在运行，请稍后重试'})
                try:
                    validate_native_record(record)
                finally:
                    server.study_lock.release()
            return handler._reply(200, record, attachment='invest-workbench-record.json')
        if path == '/api/workbench/native-chart':
            from .native_charts import render_native_png
            from .study_charts import ChartBusyError, ChartDependencyError
            if not server.study_lock.acquire(blocking=False):
                return handler._reply(409, {'error':'已有研究计算或校验正在运行，请稍后重试'})
            try:
                record = ws.get(parameter('id', True), 'native_research')
                try:
                    png = render_native_png(record)
                    error, status = None, 200
                except ChartDependencyError as exc:
                    error, status = str(exc), 503
                except ChartBusyError as exc:
                    error, status = str(exc), 409
            finally:
                server.study_lock.release()
            # Release validation/render locks before every reply. A complete
            # error or success response must already permit a subsequent retry.
            if error is not None:
                return handler._reply(status, {'error':error, 'record_saved':True})
            return handler._reply(200, body=png, content_type='image/png',
                attachment=f'invest-native-research-{record["id"][:12]}.png')
        if path == '/api/workbench/study-chart':
            import re
            from .study_charts import ChartBusyError, ChartDependencyError, render_study_png
            index = parameter('case', True)
            if re.fullmatch(r'0|[1-9][0-9]?', index) is None:
                raise ValueError('图表 case 必须为从0开始的整数')
            record = ws.get(parameter('id', True), 'study')
            try:
                png = render_study_png(record, int(index))
            except ChartDependencyError as exc:
                return handler._reply(503, {'error': str(exc), 'study_saved': True})
            except ChartBusyError as exc:
                return handler._reply(409, {'error': str(exc), 'study_saved': True})
            return handler._reply(200, body=png, content_type='image/png',
                attachment=f'invest-study-{record["id"][:12]}-case-{index}.png')
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
            response = record
            if server.experiment_archive is not None:
                response = dict(record,tracking=server.experiment_archive.archive(record))
        finally:
            server.study_lock.release()
        # A fully received success must already be ready for the next action.
        # Do not retain the study lock while a slow client receives the body.
        return handler._reply(200,response)
    if path == '/api/workbench/track-study':
        if not server.study_lock.acquire(blocking=False):
            return handler._reply(409,{'error':'已有实验正在运行，请保留当前结果后重试'})
        try:
            record = ws.get(payload.get('study_id'),'study')
            status = ({'status':'disabled','study_saved':True} if server.experiment_archive is None
                      else server.experiment_archive.archive(record))
        finally:
            server.study_lock.release()
        return handler._reply(200,{'study_id':record['id'],'tracking':status})
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
