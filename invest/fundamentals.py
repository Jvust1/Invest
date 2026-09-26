"""G5 extension: local, versioned point-in-time financial facts.

This is a deterministic availability filter, not a truth/permission verifier.
No extension code is imported from users; disabling it does not change the core.
"""
from __future__ import annotations
from datetime import date, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import re
from .data import is_mainboard_symbol
from .workspace import digest, instant, text


def validate_bundle(payload):
    if not isinstance(payload,dict) or set(payload) != {'source_name','source_text','license_note','facts'}:
        raise ValueError('扩展包须包含source_name/source_text/license_note/facts')
    source_name = text(payload['source_name'],'来源名称',200)
    source_text = text(payload['source_text'],'来源原文',300000)
    license_note = text(payload['license_note'],'许可声明',2000)
    raw = payload['facts']
    if not isinstance(raw,list) or not 1 <= len(raw) <= 5000:
        raise ValueError('本地事实包必须为1–5000条')
    rows,unique = [],set()
    expected = {'symbol','metric','period_end','available_at','revision','value','unit'}
    for row in raw:
        if not isinstance(row,dict) or set(row)!=expected:
            raise ValueError('事实字段必须完整且不能附带额外字段')
        if not is_mainboard_symbol(row['symbol']):
            raise ValueError('不支持该证券代码')
        metric = text(row['metric'],'指标名',80)
        if not re.fullmatch('[A-Za-z][A-Za-z0-9_]{0,79}',metric):
            raise ValueError('指标名请使用英文、数字或下划线')
        period = date.fromisoformat(row['period_end'])
        if period.isoformat() != row['period_end']:
            raise ValueError('报告期末须为标准日期')
        available = instant(row['available_at'])
        if available.astimezone(timezone(timedelta(hours=8))).date() < period:
            raise ValueError('可见时间不能早于报告期末')
        revision = row['revision']
        if type(revision) is not int or not 1 <= revision <= 10000:
            raise ValueError('修订版本必须为正整数')
        value = row['value']
        if isinstance(value,bool) or not isinstance(value,(str,int,float)):
            raise ValueError('指标值必须是有限数值')
        try:
            value = Decimal(str(value))
            if not value.is_finite() or abs(value)>Decimal('1e15') or (value and value.adjusted() < -18):
                raise ValueError('指标值超出范围')
        except InvalidOperation:
            raise ValueError('指标值错误') from None
        key = (row['symbol'],metric,period.isoformat(),revision)
        if key in unique:
            raise ValueError('同一指标、报告期和修订号重复或冲突')
        unique.add(key)
        rows.append({'symbol':row['symbol'],'metric':metric,'period_end':period.isoformat(),
                     'available_at':available.isoformat(),'revision':revision,
                     'value':str(value),'unit':text(row['unit'],'单位',50)})
    groups = {}
    for row in rows:
        groups.setdefault((row['symbol'],row['metric'],row['period_end']),[]).append(row)
    for group in groups.values():
        revisions = sorted(group,key=lambda r:r['revision'])
        if any(instant(a['available_at'])>=instant(b['available_at']) for a,b in zip(revisions,revisions[1:])):
            raise ValueError('修订号增加时，可见时间必须严格增加')
        if len({r['unit'] for r in revisions})!=1:
            raise ValueError('同一指标报告期的修订不能暗中切换单位')
    rows.sort(key=lambda r:(r['symbol'],r['metric'],r['period_end'],r['revision']))
    return {'schema':'invest-pit-facts-v1','source_name':source_name,
            'source_text':source_text,'source_sha256':hashlib.sha256(source_text.encode()).hexdigest(),
            'license_note':license_note,'license_independently_verified':False,
            'facts':rows,'facts_id':digest(rows),'source_truth_verified':False}


def as_of(bundle, symbol, timestamp, *, enabled=False):
    if type(enabled) is not bool:
        raise ValueError('扩展启用状态必须为布尔值')
    if not enabled:
        return {'enabled':False,'facts':[],'core_unaffected':True}
    if bundle.get('schema')!='invest-pit-facts-v1' or digest(bundle.get('facts'))!=bundle.get('facts_id'):
        raise ValueError('扩展包身份错误')
    if not is_mainboard_symbol(symbol):
        raise ValueError('证券代码错误')
    moment = instant(timestamp)
    selected = {}
    for row in bundle['facts']:
        if row['symbol']==symbol and instant(row['available_at']) <= moment:
            key = (row['metric'],row['period_end'])
            if key not in selected or row['revision']>selected[key]['revision']:
                selected[key] = row
    return {'enabled':True,'symbol':symbol,'as_of':moment.isoformat(),
            'facts':sorted(selected.values(),key=lambda r:(r['metric'],r['period_end'])),
            'source_sha256':bundle['source_sha256'],'source_truth_verified':False,
            'limitations':['按供应者声明的available_at过滤，不证明真实公告发布时间',
                           '只做可解释的本地研究扩展，未自动加入选股或交易决策']}
