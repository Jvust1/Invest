"""Chat-facing stable research tools. Input scenarios are not trade authorizations."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from importlib.metadata import PackageNotFoundError, version
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
from typing import Any

from .catalog import Catalog
from .connectors import DriveClient, GitHubClient, REPOSITORY, REPOSITORY_ID

TOOL_NAMES = ('status','search','fetch','list_sources','github_read_file','drive_list_files',
              'drive_read_file','allocation_scenario','portfolio_snapshot','risk_summary',
              'backtest_sma','pit_facts','upstream_catalog','market_history',
              'connection_check','analyze_price_series')
SHANGHAI = timezone(timedelta(hours=8))
SCOPE = 'PUBLIC_RESEARCH_ONLY'


def canonical(value):
    return json.dumps(value,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def day(value):
    if not isinstance(value,str): raise ValueError('date must be YYYY-MM-DD')
    parsed = date.fromisoformat(value)
    if parsed.isoformat()!=value or parsed>datetime.now(SHANGHAI).date():
        raise ValueError('date must be canonical and not in the future (Asia/Shanghai)')
    return parsed


def number(value, label, *, lower=-1e9, upper=1e9):
    if isinstance(value,bool) or not isinstance(value,(str,int,float)):
        raise ValueError(label+' must be a finite number')
    try: n=float(value)
    except (ValueError,OverflowError): raise ValueError(label+' must be a finite number') from None
    if not math.isfinite(n) or not lower<=n<=upper: raise ValueError(label+' is outside bounds')
    return n


def exact_decimal(value, label, *, lower=0, upper=1_000_000_000, integral=False):
    """Validate original decimal input without lossy float round trips."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float)) or len(str(value)) > 100:
        raise ValueError(label+' must be a bounded finite decimal')
    try:
        result = Decimal(str(value))
        if not result.is_finite() or not Decimal(lower) <= result <= Decimal(upper):
            raise ValueError(label+' is outside bounds')
        if integral:
            if result != result.to_integral_value(): raise ValueError(label+' must be an integer')
        elif result != result.quantize(Decimal('0.01')):
            raise ValueError(label+' must be precise to CNY cents')
    except InvalidOperation:
        raise ValueError(label+' must be a bounded finite decimal') from None
    return result


def _metrics(values, annualization=252):
    nav, peak, dd = 1.0, 1.0, 0.0
    for r in values:
        nav*=1+r
        if not math.isfinite(nav) or nav<=0: raise ValueError('cumulative wealth is outside numeric range')
        peak=max(peak,nav)
        dd=min(dd,nav/peak-1)
    vol=statistics.stdev(values) if len(values)>1 else 0.0
    mean=statistics.mean(values)
    downside=math.sqrt(sum(min(r,0)**2 for r in values)/len(values))
    try: annual=nav**(annualization/len(values))-1
    except OverflowError: raise ValueError('annualized return is outside numeric range') from None
    if not math.isfinite(annual): raise ValueError('annualized return is outside numeric range')
    return {'cumulative_return':nav-1,'annualized_return':annual,'annual_volatility':vol*math.sqrt(annualization),
            'max_drawdown':dd,'sharpe_zero_rf':mean/vol*math.sqrt(annualization) if vol else None,
            'sortino_zero_target':mean/downside*math.sqrt(annualization) if downside else None}


class InvestService:
    def __init__(self, *, catalog_path=None, github=None, drive=None):
        configured = catalog_path or os.environ.get('INVEST_CATALOG_PATH')
        self.catalog = Catalog(configured) if configured else None
        self.github = github or GitHubClient()
        self.drive = drive or DriveClient()

    def status(self) -> dict[str, Any]:
        deps={}
        for dependency in ('mcp','numpy','pandas'):
            try: deps[dependency]=version(dependency)
            except PackageNotFoundError: deps[dependency]=None
        return {'schema':'invest-chat-status-v1','plugin_version':'0.2.0','repository':REPOSITORY,'repository_id':REPOSITORY_ID,
                'scope':SCOPE,'tools':list(TOOL_NAMES),'capability':'LOCAL_IMPLEMENTATION_NOT_CHATGPT_ACCEPTANCE',
                'source_configuration':{'github_public_reader':True,'drive_oauth_configured':self.drive.configured,
                                        'private_catalog_present':bool(self.catalog and self.catalog.path.is_file())},
                'dependencies':deps,'broker_connected':False,'automatic_orders_supported':False,
                'real_holdout_opened':False,'live_market_data_verified':False,
                'remaining_acceptance':['authenticated deployment/tunnel','ChatGPT Chat tool-call smoke',
                                        'licensed/current market data and forward validation'],
                'note':'Configured is not Connected; offline/synthetic software checks are not investment-performance evidence.'}

    def list_sources(self) -> dict[str, Any]:
        return {'repository':REPOSITORY,'repository_id':REPOSITORY_ID,
                'drive_folders':[{'id':f,'url':'https://drive.google.com/drive/folders/'+f} for f in self.drive.folders],
                'private_catalog_configured':self.catalog is not None,
                'credentials_exposed':False,'all_sources_untrusted':True}

    def search(self, query: str, source='all', limit=10, include_live=False) -> dict[str, Any]:
        if source not in {'all','github','drive'} or type(limit) is not int or not 1<=limit<=20:
            raise ValueError('invalid search source/limit')
        if not isinstance(query,str) or not query.strip() or len(query)>200: raise ValueError('invalid search query')
        if type(include_live) is not bool: raise ValueError('include_live must be boolean')
        page=self.catalog.search_page(query,source=source,limit=limit) if self.catalog else {'results':[],'limited':False}
        results=page['results']; limited=page['limited']
        errors=[]
        if include_live and source in {'all','github'}:
            try:
                listing=self.github.list_files(query=query,limit=limit)
                results.extend(listing['results']); limited=limited or bool(listing.get('limited'))
            except RuntimeError as exc: errors.append({'source':'github','error':str(exc)})
        if include_live and source in {'all','drive'}:
            # List only selected roots. Recursive/paginated browsing is an explicit separate tool.
            for folder in self.drive.folders:
                try:
                    listing=self.drive.list_files(folder,limit=100)
                    results.extend(r for r in listing['files'] if query.casefold() in r['title'].casefold())
                    if listing.get('next_page_token'):
                        limited=True
                        errors.append({'source':'drive','error':'root listing has further pages; use drive_list_files'})
                except RuntimeError as exc: errors.append({'source':'drive','error':str(exc)})
        unique={r['id']:r for r in results}
        return {'results':list(unique.values())[:limit],'limited':limited or len(unique)>limit,'errors':errors,
                'search_scope':'private index; optional live filenames in bound repo and allowlisted folders',
                'complete_drive_scan':False,'untrusted_source_material':True}

    def fetch(self, id: str, offset=0, max_chars=1000) -> dict[str, Any]:
        if not isinstance(id,str): raise ValueError('resource ID must be text')
        if id.startswith('local:'):
            if not self.catalog: raise LookupError('private catalog not configured')
            return self.catalog.fetch(id,offset=offset,max_chars=max_chars)
        if id.startswith('github:'):
            _,sha,path=id.split(':',2)
            return self.github.fetch(path,commit=sha,offset=offset,max_chars=max_chars)
        if id.startswith('drive:'):
            return self.drive.fetch(id[6:],offset=offset,max_chars=max_chars)
        raise ValueError('use a source-bound ID returned by search/listing, not a URL or local path')

    def github_read_file(self, path: str, offset=0, max_chars=2000) -> dict[str, Any]:
        return self.github.fetch(path,offset=offset,max_chars=max_chars)

    def drive_list_files(self, folder_id=None, limit=20, page_token=None) -> dict[str, Any]:
        return self.drive.list_files(folder_id,limit=limit,page_token=page_token)

    def drive_read_file(self, file_id: str, offset=0, max_chars=1000) -> dict[str, Any]:
        return self.drive.fetch(file_id,offset=offset,max_chars=max_chars)

    def allocation_scenario(self, request: dict) -> dict[str, Any]:
        from ..allocation import size_allocation
        day(request.get('as_of'))
        result=size_allocation(request)
        result.update(execution_authorized=False,quote_freshness_verified=False,
                      evidence_label='CALLER_SUPPLIED_SCENARIO', no_order_generated=True)
        return result

    def market_history(self, symbol: str, start_date: str, end_date: str) -> dict[str, Any]:
        from .market import history
        return history(symbol, start_date, end_date, day)

    def connection_check(self, include_network: bool = False) -> dict[str, Any]:
        from .diagnostics import connection_check
        return connection_check(catalog=self.catalog, github=self.github, drive=self.drive,
                                include_network=include_network)

    def analyze_price_series(self, symbol: str, bars: list[dict], currency: str,
                             source: str, as_of: str, adjustment: str = 'unknown',
                             max_staleness_days: int = 7) -> dict[str, Any]:
        from .price_quality import analyze_price_series
        return analyze_price_series(symbol, bars, currency, source, as_of, adjustment, max_staleness_days)

    def portfolio_snapshot(self, cash_cny: str, positions: list[dict], as_of: str,
                           max_quote_age_days: int = 7) -> dict[str, Any]:
        cutoff=day(as_of)
        if type(max_quote_age_days) is not int or not 0<=max_quote_age_days<=366:
            raise ValueError('max_quote_age_days must be an integer from 0 to 366')
        cash=exact_decimal(cash_cny,'cash')
        if not isinstance(positions,list) or len(positions)>100: raise ValueError('positions limit is 100')
        rows,seen=[],set()
        for p in positions:
            if not isinstance(p,dict) or set(p)!={'symbol','quantity','price_cny','quote_date','quote_source'}:
                raise ValueError('explicit symbol, quantity, CNY price, quote date/source required')
            symbol=p['symbol']
            if not isinstance(symbol,str) or not symbol.strip() or len(symbol)>40 or symbol in seen: raise ValueError('invalid/duplicate symbol')
            seen.add(symbol)
            quantity=exact_decimal(p['quantity'],'quantity',upper=100_000_000,integral=True)
            price=exact_decimal(p['price_cny'],'price',lower=Decimal('0.01'))
            quote_day=day(p['quote_date'])
            if quote_day>cutoff: raise ValueError('quote later than snapshot')
            if not isinstance(p['quote_source'],str) or not p['quote_source'].strip() or len(p['quote_source'])>300: raise ValueError('quote source required')
            age=(cutoff-quote_day).days
            rows.append(dict(p,market_value_cny=format(price*int(quantity),'.2f'),
                             quote_age_calendar_days=age,quote_stale=age>max_quote_age_days))
        invested=sum((Decimal(r['market_value_cny']) for r in rows),Decimal(0))
        total=cash+invested
        for r in rows: r['portfolio_weight']=float(Decimal(r['market_value_cny'])/total) if total else 0
        return {'status':'SCENARIO_ONLY','currency':'CNY','as_of':as_of,'cash_cny':format(cash,'.2f'),
                'invested_cny':format(invested,'.2f'),'total_cny':format(total,'.2f'),'positions':rows,
                'quote_quality':{'max_age_calendar_days':max_quote_age_days,
                                 'stale_symbols':[r['symbol'] for r in rows if r['quote_stale']],
                                 'source_independently_verified':False,'freshness_relative_to':'caller as_of, not wall clock'},
                'concentration_max_weight':max((r['portfolio_weight'] for r in rows),default=0),
                'stress_scenarios':[{'invested_price_shock':x,'pnl_cny':str((invested*Decimal(str(x))).quantize(Decimal('0.01')))} for x in (-0.1,-0.2,-0.3)],
                'limitations':['Caller quotes; no actual account access, FX verification, correlations, fees or forecasts.'],
                'execution_authorized':False}

    def risk_summary(self, daily_returns: list[dict], source: str, as_of: str, annualization=252) -> dict[str, Any]:
        cutoff=day(as_of)
        if type(annualization) is not int or not 1<=annualization<=366: raise ValueError('annualization must be 1-366')
        if not isinstance(source,str) or not source.strip() or len(source)>300: raise ValueError('source declaration required')
        if not isinstance(daily_returns,list) or not 2<=len(daily_returns)<=5000: raise ValueError('2-5000 daily observations required')
        values,previous=[],date.min
        for row in daily_returns:
            if not isinstance(row,dict) or set(row)!={'date','return'}: raise ValueError('daily rows require only date/return')
            current=day(row['date'])
            if current<=previous or current>cutoff: raise ValueError('dates must be strictly increasing and <= as_of')
            previous=current
            r=number(row['return'],'simple return',lower=-1,upper=10)
            if r<=-1: raise ValueError('return must be greater than -1')
            values.append(r)
        return {'status':'SCENARIO_ONLY','engine':'native-reference-formulas','input_sha256':digest(daily_returns),
                'source':source,'as_of':as_of,'observations':len(values),'annualization':annualization,
                'metrics':_metrics(values,annualization),'execution_authorized':False,
                'limitations':['Descriptive, in-sample statistics; initial wealth=1 included in drawdown.',
                               'Zero risk-free/target rate; undefined Sharpe/Sortino are null, not zero.',
                               'No source license, corporate action, PIT or forward-return verification.']}

    def backtest_sma(self, prices: list[dict], source: str, as_of: str, fast=5, slow=20, fee_bps=5.0) -> dict[str, Any]:
        from ..pipeline import moving_average_signal, run_backtest
        import pandas as pd
        cutoff=day(as_of)
        if type(fast) is not int or type(slow) is not int or not 0<fast<slow<=1000: raise ValueError('require 0 < fast < slow <= 1000')
        fee=number(fee_bps,'fee bps',lower=0,upper=1000)
        if not isinstance(source,str) or not source.strip() or len(source)>300: raise ValueError('source required')
        if not isinstance(prices,list) or not slow+2<=len(prices)<=5000: raise ValueError('price observations outside required bounds')
        values,days,previous=[],[],date.min
        for row in prices:
            if not isinstance(row,dict) or set(row)!={'date','close'}: raise ValueError('price rows require only date/close')
            current=day(row['date'])
            if current<=previous or current>cutoff: raise ValueError('dates must be increasing and <= as_of')
            previous=current
            values.append(number(row['close'],'close',lower=0.01,upper=1e8)); days.append(row['date'])
        series=pd.Series(values,index=pd.to_datetime(days),dtype=float)
        result=run_backtest(series,moving_average_signal(series,fast=fast,slow=slow),fee_bps=fee)
        returns=[{'date':d,'return':float(r)} for d,r in zip(days,result['strategy_return'])]
        risk=self.risk_summary(returns,source=source,as_of=as_of)
        return {'status':'SCENARIO_ONLY','input_sha256':digest(prices),'source':source,'fast':fast,'slow':slow,'fee_bps':fee,
                'risk':risk,'observations':len(prices),'last_equity':float(result['equity'].iloc[-1]),
                'last_signal':int(result['signal'].iloc[-1]),'execution_authorized':False,
                'limitations':['Existing Invest close-to-close delayed-signal arithmetic; not a fill simulator.',
                               'Fee is charged at signal turnover; no intraday fills, lots, T+1, suspensions or corporate actions.',
                               'Not equivalent to the gated execution engine or an opened holdout.']}

    def pit_facts(self, bundle: dict, symbol: str, as_of: str, enabled=False) -> dict[str, Any]:
        from ..fundamentals import as_of as filter_as_of, validate_bundle
        if type(enabled) is not bool: raise ValueError('enabled must be boolean')
        return filter_as_of(validate_bundle(bundle) if enabled else {},symbol,as_of,enabled=enabled)

    def upstream_catalog(self, capability=None, adapter_safe_only=True) -> dict[str, Any]:
        from ..upstreams import list_upstreams, is_import_available
        if capability is not None and (not isinstance(capability,str) or len(capability)>100): raise ValueError('invalid capability')
        if type(adapter_safe_only) is not bool: raise ValueError('adapter_safe_only must be boolean')
        rows=list_upstreams(capability=capability,adapter_safe_only=adapter_safe_only)
        return {'projects':[dict(r,installed=is_import_available(r)) for r in rows],
                'count':len(rows),'license_note':'Recorded software license is not a market-data license; installed is not end-to-end validated.'}
