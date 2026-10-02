"""Explicit, bounded daily-history research adapter; never a live trading feed."""
from __future__ import annotations

from datetime import datetime, timezone
import re

from ..providers.akshare_eastmoney import fetch_a_share_daily


def history(symbol, start_date, end_date, validate_day):
    if not isinstance(symbol, str) or not re.fullmatch(r'(?:6\d{5}\.SH|[03]\d{5}\.SZ)', symbol):
        raise ValueError('supported scope: six-digit A-share code with matching .SH/.SZ exchange')
    start, end = validate_day(start_date), validate_day(end_date)
    if start > end or (end-start).days > 3660:
        raise ValueError('history interval must be ordered and at most 3660 days')
    try:
        frame = fetch_a_share_daily(symbol[:6], start.strftime('%Y%m%d'), end.strftime('%Y%m%d'),
                                    period='daily', adjust='', timeout=15)
    except Exception as exc:
        # Upstream errors may contain request details. Do not leak their bodies or invent a fallback.
        raise RuntimeError('Eastmoney history request failed ('+type(exc).__name__+'); no alternate or fabricated data used') from None
    if frame.empty:
        raise RuntimeError('Eastmoney returned no observations; no alternate or fabricated data used')
    if len(frame) > 5000 or not frame.index.is_unique:
        raise ValueError('upstream observation bound or date uniqueness failed')
    from .service import number, digest
    rows, previous = [], start
    for index, row in frame.iterrows():
        if getattr(index, 'is_nat', False):
            raise ValueError('upstream date invalid')
        # strftime is deliberate: intraday timestamps are not accepted as daily close proof.
        current = validate_day(index.strftime('%Y-%m-%d'))
        if current < start or current > end or (rows and current <= previous):
            raise ValueError('upstream dates violate requested range/order')
        previous = current
        bar = {'date':current.isoformat()}
        for column in ('open','high','low','close'):
            bar[column] = number(float(row[column]), column, lower=0.01, upper=1e8)
        bar['volume_provider_units'] = number(float(row['volume']), 'volume', lower=0, upper=1e15)
        if bar['low'] > min(bar['open'],bar['close']) or bar['high'] < max(bar['open'],bar['close']) or bar['low'] > bar['high']:
            raise ValueError('upstream OHLC relationship failed')
        rows.append(bar)
    return {'status':'PUBLIC_RESEARCH_ONLY','provider':'Eastmoney via existing Invest AKShare-derived adapter',
            'symbol':symbol,'currency':'CNY','frequency':'daily','adjustment':'unadjusted',
            'start_date':start_date,'end_date':end_date,'latest_observation':rows[-1]['date'],
            'fetched_at':datetime.now(timezone.utc).isoformat(),'observations':len(rows),'bars':rows,
            'data_sha256':digest(rows),'citation_url':'https://quote.eastmoney.com/'+symbol[-2:].lower()+symbol[:6]+'.html',
            'source_endpoint':'https://push2his.eastmoney.com/api/qt/stock/kline/get',
            'license_status':'DATA_RIGHTS_NOT_INDEPENDENTLY_VERIFIED','volume_unit_verified':False,
            'quote_freshness_verified':False,'execution_authorized':False,
            'limitations':['Daily history is not a real-time executable quote.',
                           'No dividend/split adjustment, exchange calendar completeness, point-in-time universe or data-license verification.',
                           'Raw provider volume is not asserted to be shares; execution engine must not consume it without unit evidence.',
                           'Network failures are surfaced, not replaced with synthetic observations.']}
