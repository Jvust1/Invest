"""ENG-04A: offline, source-bound intake of four Tushare response files.

The raw bytes, deterministic normalization, and user-supplied evidence claims
are checked separately. A hash is not an authenticity proof or a data license.
This module has no network, broker, credential, or holdout-opening capability.
It leaves suspension/company-action fields UNKNOWN in the exported dataset.
"""
from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
from urllib.parse import urlsplit

from invest.data import FIELDS, dataset_identity, is_mainboard_symbol, parse_csv, verify_dataset_identity

SCHEMA = 'invest-raw-intake-v1'
REPORT_SCHEMA = 'invest-raw-intake-report-v1'
CST = timezone(timedelta(hours=8))
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 16 * 1024 * 1024
MAX_ROWS = 10000
REQUIRED = {
    'daily': ('ts_code', 'trade_date', 'open', 'high', 'low', 'close', 'vol'),
    'adj_factor': ('ts_code', 'trade_date', 'adj_factor'),
    'stk_limit': ('ts_code', 'trade_date', 'up_limit', 'down_limit'),
    'trade_cal': ('exchange', 'cal_date', 'is_open'),
}
FORBIDDEN = ('token', 'secret', 'password', 'cookie', 'authorization', 'api_key', 'apikey')


class IntakeError(ValueError):
    """Safe fixed diagnostic code; never echo raw inputs or provider messages."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def require(condition: bool, code: str) -> None:
    if not condition:
        raise IntakeError(code)


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw: bytes):
    require(type(raw) is bytes and 0 < len(raw) <= MAX_FILE, 'FILE_SIZE')
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, 'DUPLICATE_JSON_KEY')
            require(not any(x in key.lower().replace('-', '_') for x in FORBIDDEN), 'SENSITIVE_FIELD')
            result[key] = value
        return result
    def invalid(_):
        raise IntakeError('NONFINITE_JSON')
    try:
        value = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=pairs, parse_constant=invalid)
        canonical(value)  # reject overflow to infinity such as 1e999
        return value
    except IntakeError:
        raise
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise IntakeError('INVALID_JSON') from None


def keys(obj, required, optional=()) -> None:
    require(type(obj) is dict, 'OBJECT_REQUIRED')
    require(set(required) <= obj.keys() and not obj.keys() - set(required) - set(optional), 'SCHEMA_FIELDS')


def day(value) -> date:
    require(type(value) is str and re.fullmatch(r'\d{4}-\d{2}-\d{2}', value) is not None, 'DATE_FORMAT')
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise IntakeError('DATE_FORMAT') from None


def instant(value) -> datetime:
    require(type(value) is str and len(value) <= 40 and 'T' in value, 'TIME_FORMAT')
    try:
        t = datetime.fromisoformat(value.replace('Z', '+00:00'))
        require(t.tzinfo is not None and t.utcoffset() is not None, 'TIMEZONE_REQUIRED')
        return t.astimezone(CST)
    except ValueError:
        raise IntakeError('TIME_FORMAT') from None


def number(value, *, price=False, zero=False) -> Decimal:
    require(type(value) in (int, float, str), 'NUMBER_TYPE')
    text = str(value)
    require(len(text) <= 64 and re.fullmatch(r'[+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?', text) is not None, 'NUMBER_FORMAT')
    try:
        n = Decimal(text)
        require(n.is_finite() and (n >= 0 if zero else n > 0) and n <= Decimal('1e15'), 'NUMBER_RANGE')
        require(not price or n * 100 == (n * 100).to_integral_value(), 'SUBCENT_PRICE_UNSUPPORTED')
        return n
    except InvalidOperation:
        raise IntakeError('NUMBER_FORMAT') from None


class Store:
    """Bounded immutable read snapshot; same-path references reuse the same bytes."""
    def __init__(self, root: Path):
        self.root = root.resolve(strict=True)
        self.cache: dict[str, bytes] = {}
        self.total = 0

    def read(self, descriptor: dict) -> bytes:
        keys(descriptor, {'path', 'sha256'})
        name, expected = descriptor['path'], descriptor['sha256']
        require(type(name) is str and len(name) <= 180 and re.fullmatch(r'[A-Za-z0-9_./-]+', name) is not None, 'UNSAFE_PATH')
        rel = PurePosixPath(name)
        require(not rel.is_absolute() and str(rel) == name and all(p not in ('..', '.') for p in rel.parts), 'UNSAFE_PATH')
        require(type(expected) is str and re.fullmatch(r'[a-f0-9]{64}', expected) is not None, 'INVALID_SHA256')
        if name not in self.cache:
            path = self.root
            for component in rel.parts:
                path = path / component
                require(not path.is_symlink(), 'SYMLINK_FORBIDDEN')
            try:
                require(path.resolve(strict=True).is_relative_to(self.root) and path.is_file(), 'UNSAFE_PATH')
                require(path.stat().st_size <= MAX_FILE, 'FILE_SIZE')
                with path.open('rb') as stream:
                    raw = stream.read(MAX_FILE + 1)
            except OSError:
                raise IntakeError('ARTIFACT_MISSING') from None
            require(0 < len(raw) <= MAX_FILE, 'FILE_SIZE')
            self.total += len(raw)
            require(self.total <= MAX_TOTAL, 'BUNDLE_SIZE')
            self.cache[name] = raw
        raw = self.cache[name]
        require(sha(raw) == expected, 'ARTIFACT_HASH_MISMATCH')
        return raw


def _table(raw: bytes, endpoint: str) -> tuple[list[dict], list[str]]:
    payload = strict_json(raw)
    keys(payload, {'code', 'msg', 'data'}, {'request_id'})
    require(type(payload['code']) is int, 'PROVIDER_CODE_TYPE')
    require(payload['code'] == 0, 'PROVIDER_REPORTED_FAILURE')
    data = payload['data']
    keys(data, {'fields', 'items'}, {'has_more'})
    require('has_more' not in data or data['has_more'] is False, 'TRUNCATED_RESPONSE')
    fields, items = data['fields'], data['items']
    require(type(fields) is list and 1 <= len(fields) <= 64 and all(type(f) is str and re.fullmatch('[a-z_]+', f) for f in fields), 'TABLE_FIELDS')
    require(len(fields) == len(set(fields)), 'DUPLICATE_TABLE_FIELD')
    require(not any(any(x in f for x in FORBIDDEN) for f in fields), 'SENSITIVE_FIELD')
    require(set(REQUIRED[endpoint]) <= set(fields), 'MISSING_PROVIDER_FIELD')
    require(type(items) is list and len(items) <= MAX_ROWS, 'TABLE_ROWS')
    rows = []
    for item in items:
        require(type(item) is list and len(item) == len(fields), 'RAGGED_TABLE')
        require(all(v is None or type(v) in (str, int, float) for v in item), 'TABLE_SCALAR_TYPE')
        rows.append(dict(zip(fields, item)))
    return rows, fields


def _index(rows, endpoint, manifest):
    result = {}
    for i, row in enumerate(rows):
        s = row['cal_date' if endpoint == 'trade_cal' else 'trade_date']
        require(type(s) is str and re.fullmatch('[0-9]{8}', s) is not None, 'PROVIDER_DATE')
        d = day(s[:4] + '-' + s[4:6] + '-' + s[6:]).isoformat()
        require(manifest['start_date'] <= d <= manifest['end_date'], 'ROW_OUT_OF_RANGE')
        require(d not in result, 'DUPLICATE_PROVIDER_ROW')
        if endpoint == 'trade_cal':
            exchange = 'SSE' if manifest['symbol'].endswith('.SH') else 'SZSE'
            require(row['exchange'] == exchange, 'EXCHANGE_MISMATCH')
            require((type(row['is_open']) is int and row['is_open'] in (0, 1)) or (type(row['is_open']) is str and row['is_open'] in ('0', '1')), 'CALENDAR_FLAG')
        else:
            require(row['ts_code'] == manifest['symbol'], 'SYMBOL_MISMATCH')
        result[d] = (i, row)
    return result


def _normalize(manifest, tables, hashes):
    indexed = {n: _index(tables[n], n, manifest) for n in REQUIRED}
    start, end = day(manifest['start_date']), day(manifest['end_date'])
    days = [(start + timedelta(days=i)).isoformat() for i in range((end-start).days+1)]
    cal = indexed['trade_cal']
    require(set(cal) == set(days), 'CALENDAR_NATURAL_DAY_GAP')
    opens = [d for d in days if str(cal[d][1]['is_open']) == '1']
    require(bool(indexed['daily']), 'EMPTY_DAILY')
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=FIELDS, lineterminator='\n')
    writer.writeheader()
    provenance, issues = [], []
    for d in opens:
        if d not in indexed['daily']:
            issues.append({'code': 'MISSING_SESSION_NOT_ASSUMED_SUSPENDED', 'date': d})
    for d, (raw_index, row) in sorted(indexed['daily'].items()):
        require(d in opens, 'PRICE_ON_CLOSED_DAY')
        norm = {'symbol': manifest['symbol'], 'date': d, 'suspended': '', 'corporate_action': ''}
        traces = []
        for field in ('open', 'high', 'low', 'close'):
            norm[field] = str(number(row[field], price=True))
            traces.append({'field': field, 'endpoint': 'daily', 'item_index': raw_index, 'input_field': field, 'transform': 'identity'})
        shares = number(row['vol'], zero=True) * 100
        require(shares == shares.to_integral_value() and shares <= Decimal('1e15'), 'VOLUME_NOT_INTEGER_SHARES')
        norm['volume_shares'] = str(int(shares))
        traces.append({'field': 'volume_shares', 'endpoint': 'daily', 'item_index': raw_index, 'input_field': 'vol', 'transform': 'decimal_times_100'})
        for endpoint, fields in [('adj_factor', ('adj_factor',)), ('stk_limit', ('up_limit', 'down_limit'))]:
            require(d in indexed[endpoint], 'SUPPLEMENT_MISSING_FOR_PRICE')
            j, supplement = indexed[endpoint][d]
            for field in fields:
                norm[field] = str(number(supplement[field], price=field != 'adj_factor'))
                traces.append({'field': field, 'endpoint': endpoint, 'item_index': j, 'input_field': field, 'transform': 'identity'})
        writer.writerow(norm)
        provenance.append({'date': d, 'symbol': manifest['symbol'], 'normalized_csv_line': len(provenance)+2,
                           'fields': [dict(t, raw_sha256=hashes[t['endpoint']]) for t in traces],
                           'unknown_fields': ['suspended', 'corporate_action']})
    csv_text = out.getvalue()
    calendar_csv = 'date\n' + '\n'.join(opens) + '\n'
    try:
        ds = parse_csv(csv_text, source='ENG04 raw Tushare response reconstruction', calendar_csv=calendar_csv)
    except ValueError:
        raise IntakeError('CORE_DATA_CONTRACT_REJECTED') from None
    # The existing core uses floats: never let a rounding loss be called exact.
    csv_rows = list(csv.DictReader(io.StringIO(csv_text)))
    for source_row, bar in zip(csv_rows, ds['bars']):
        for f in ('open','high','low','close','volume_shares','up_limit','down_limit','adj_factor'):
            require(Decimal(str(bar[f])) == Decimal(source_row[f]), 'CORE_NUMERIC_REPRESENTATION_LOSS')
    ds['meta'].update(source_kind='eng04_' + manifest['origin'], retrieved_at=manifest['captured_at'],
                      raw_bundle_id=sha(canonical(hashes)), requested_start=manifest['start_date'],
                      requested_end=manifest['end_date'], normalization_schema=SCHEMA)
    ds['id'] = dataset_identity(ds)
    for endpoint in ('adj_factor', 'stk_limit'):
        for d in sorted(indexed[endpoint].keys() - indexed['daily'].keys()):
            issues.append({'code': 'SUPPLEMENT_WITHOUT_PRICE', 'endpoint': endpoint, 'date': d})
    for e in ds['audit']['errors']:
        issues.append({'code': 'CORE_' + e['code'].upper(), 'date': e.get('date')})
    factors = {Decimal(str(b['adj_factor'])) for b in ds['bars']}
    if len(factors) > 1:
        issues.append({'code': 'FACTOR_CHANGE_REQUIRES_ACTION_REVIEW'})
    return ds, csv_text, calendar_csv, provenance, issues, days, opens, indexed


def _candidate(store, descriptor, expected):
    if descriptor is None:
        return {'status': 'NOT_SUPPLIED', 'differences': []}
    candidate = strict_json(store.read(descriptor))
    try:
        verify_dataset_identity(candidate)
    except ValueError:
        raise IntakeError('CANDIDATE_IDENTITY_MISMATCH') from None
    differences = []
    if type(candidate.get('audit')) is not dict or candidate['audit'].get('backtest_ready') is not False:
        differences.append({'section':'audit','field':'unjustified_backtest_ready'})
    for field in ('currency', 'price_basis', 'volume_unit'):
        if candidate['meta'].get(field) != expected['meta'][field]:
            differences.append({'section':'meta','field':field})
    if candidate['calendar'] != expected['calendar']:
        differences.append({'section':'calendar','field':'dates'})
    require(type(candidate['bars']) is list, 'CANDIDATE_BARS')
    actual = {}
    for b in candidate['bars']:
        require(type(b) is dict and set(b) == set(FIELDS), 'CANDIDATE_BAR_FIELDS')
        key = (b['symbol'], b['date'])
        require(key not in actual, 'CANDIDATE_DUPLICATE_BAR')
        actual[key] = b
    for b in expected['bars']:
        key = (b['symbol'], b['date'])
        match = actual.pop(key, None)
        if match is None:
            differences.append({'section':'bars','date':b['date'],'field':'missing_row'})
            continue
        for f in FIELDS:
            # bool equals int in Python; require matching types for null/flags.
            if f in ('suspended','corporate_action'):
                equal = match[f] is b[f]
            elif f in ('symbol','date'):
                equal = type(match[f]) is str and match[f] == b[f]
            else:
                equal = type(match[f]) in (int, float) and Decimal(str(match[f])) == Decimal(str(b[f]))
            if not equal:
                differences.append({'section':'bars','date':b['date'],'field':f})
    for _, d in sorted(actual):
        differences.append({'section':'bars','date':d,'field':'extra_row'})
    return {'status':'MATCH' if not differences else 'MISMATCH', 'differences':differences,
            'candidate_dataset_id':candidate['id'], 'comparison':'raw-derived fields, unknown flags, calendar and units; not metadata text equality'}


def _license(store, review, m, as_of):
    if review is None:
        return {'status':'MISSING', 'independently_verified':False}
    keys(review, {'artifact','provider','symbol','data_start','data_end','valid_from','valid_until','permitted_uses','decision','reviewed_at'})
    raw = store.read(review['artifact'])
    require(review['decision'] in ('declared_authorized','unknown','denied'), 'LICENSE_DECISION')
    require(type(review['permitted_uses']) is list and all(type(x) is str for x in review['permitted_uses']), 'LICENSE_USES')
    require(instant(review['reviewed_at']) <= as_of, 'FUTURE_LICENSE_REVIEW')
    lo, hi = day(review['data_start']), day(review['data_end'])
    vf, vu = day(review['valid_from']), day(review['valid_until'])
    require(lo <= hi and vf <= vu, 'LICENSE_DATE_RANGE')
    checks = {
        'provider': review['provider'] == 'tushare', 'symbol':review['symbol'] == m['symbol'],
        'data_window':lo <= day(m['start_date']) <= day(m['end_date']) <= hi,
        'capture_date':vf <= instant(m['captured_at']).date() <= vu,
        'audit_date':vf <= as_of.date() <= vu,
        'local_research':'local_research' in review['permitted_uses'],
        'declared_authorized':review['decision'] == 'declared_authorized',
    }
    return {'status':'DECLARED_SCOPE_MATCH' if all(checks.values()) else 'SCOPE_NOT_SATISFIED',
            'checks':checks, 'evidence_sha256':sha(raw), 'independently_verified':False,
            'redistribution_granted_by_program':False}


def _facts(store, descriptor, m, as_of, days, opens, ds):
    if descriptor is None:
        return {'status':'MISSING','issues':[{'code':'MARKET_FACTS_MISSING'}], 'independently_verified':False}
    facts = strict_json(store.read(descriptor))
    keys(facts, {'schema','symbol','start_date','end_date','evidence','calendar','sessions','rules'})
    require(facts['schema'] == 'invest-market-facts-v1' and all(facts[k] == m[k] for k in ('symbol','start_date','end_date')), 'FACT_SCOPE_MISMATCH')
    require(type(facts['evidence']) is dict and 1 <= len(facts['evidence']) <= 20, 'FACT_EVIDENCE_SET')
    evidence = {}
    for name, e in facts['evidence'].items():
        require(re.fullmatch('[a-z][a-z0-9_]{0,39}', name) is not None, 'EVIDENCE_NAME')
        keys(e, {'artifact','source_url','published_at','retrieved_at'})
        store.read(e['artifact'])
        require(type(e['source_url']) is str and len(e['source_url']) <= 500, 'EVIDENCE_URL')
        try:
            u = urlsplit(e['source_url'])
        except ValueError:
            raise IntakeError('EVIDENCE_URL') from None
        require(u.scheme == 'https' and bool(u.hostname) and not u.username and not u.password and not u.query and not u.fragment, 'EVIDENCE_URL')
        pub, got = instant(e['published_at']), instant(e['retrieved_at'])
        require(pub <= got <= as_of, 'EVIDENCE_TIME_ORDER')
        evidence[name] = pub
    issues = []
    def check_ref(row, d):
        name = row['evidence_id']
        require(type(name) is str and name in evidence, 'EVIDENCE_REF_MISSING')
        # Explicit conservative research cutoff, not an exchange session claim.
        if evidence[name] > datetime.combine(day(d), time(9), CST):
            issues.append({'code':'FACT_NOT_KNOWN_AT_DECLARED_CUTOFF','date':d})
    for field in ('calendar','sessions','rules'):
        require(type(facts[field]) is list and len(facts[field]) <= 10000, 'FACT_ROWS')
    calendar = {}
    for row in facts['calendar']:
        keys(row, {'date','is_open','evidence_id'})
        d = day(row['date']).isoformat()
        require(d in days and d not in calendar and type(row['is_open']) is bool, 'FACT_CALENDAR_ROW')
        check_ref(row,d)
        calendar[d] = row['is_open']
    if set(calendar) != set(days) or [d for d in days if calendar.get(d)] != opens:
        issues.append({'code':'EXTERNAL_CALENDAR_DISAGREES_OR_INCOMPLETE'})
    sessions, bars = {}, {b['date']:b for b in ds['bars']}
    for row in facts['sessions']:
        keys(row, {'date','suspended','corporate_action','risk_warning','evidence_id'})
        d = day(row['date']).isoformat()
        require(d in opens and d not in sessions, 'FACT_SESSION_ROW')
        check_ref(row,d)
        sessions[d] = row
        for f in ('suspended','corporate_action','risk_warning'):
            require(row[f] is None or type(row[f]) is bool, 'FACT_BOOLEAN')
            if row[f] is None:
                issues.append({'code':'FACT_UNKNOWN','date':d,'field':f})
        if row['corporate_action'] is True:
            issues.append({'code':'CORPORATE_ACTION_UNSUPPORTED','date':d})
        if row['suspended'] is True and d in bars and bars[d]['volume_shares'] > 0:
            issues.append({'code':'SUSPENSION_VOLUME_CONFLICT','date':d})
        if row['suspended'] is False and d not in bars:
            issues.append({'code':'UNSUSPENDED_SESSION_WITHOUT_PRICE','date':d})
    for d in sorted(set(opens)-sessions.keys()):
        issues.append({'code':'FACT_SESSION_MISSING','date':d})
    coverage = {d:0 for d in opens}
    for rule in facts['rules']:
        keys(rule, {'effective_from','effective_to','tick_size','buy_lot','evidence_id'})
        lo, hi = day(rule['effective_from']), day(rule['effective_to'])
        require(lo <= hi, 'RULE_RANGE')
        tick = number(rule['tick_size'])
        require(type(rule['buy_lot']) is int and 0 < rule['buy_lot'] <= 1000000, 'RULE_LOT')
        check_ref(rule,lo.isoformat())
        if tick != Decimal('0.01') or rule['buy_lot'] != 100:
            issues.append({'code':'RULE_UNSUPPORTED_BY_CURRENT_CORE'})
        for d in opens:
            if lo <= day(d) <= hi:
                coverage[d] += 1
                if d in bars and any(Decimal(str(bars[d][f])) % tick for f in ('open','high','low','close')):
                    issues.append({'code':'PRICE_NOT_ON_DECLARED_TICK','date':d})
    for d, n in coverage.items():
        if n != 1:
            issues.append({'code':'RULE_COVERAGE_GAP' if n == 0 else 'RULE_COVERAGE_OVERLAP','date':d})
    return {'status':'CLAIM_STRUCTURE_CONSISTENT' if not issues else 'INCOMPLETE_OR_CONFLICTING',
            'issues':issues, 'evidence_files':len(evidence), 'sessions':len(sessions),
            'decision_cutoff':'09:00:00+08:00; declared research assumption, not market opening time',
            'independently_verified':False,'survivorship_bias':'NOT_VERIFIED','pit_features':'NOT_VERIFIED'}


def audit_bundle(root: str | Path, *, as_of: str | None = None) -> dict:
    """Return a deterministic audit payload plus optional normalized artifacts.

    `as_of` is explicit for reproducible replay; it is not an attested clock.
    Neither a structurally complete bundle nor a caller's declarations authorize
    trading, opening a holdout, or redistributing any third-party material.
    """
    checked = instant(as_of) if as_of else datetime.now(CST)
    report = {'schema':REPORT_SCHEMA, 'origin':'UNREAD', 'integrity':'INVALID_INPUT',
              'issues':[], 'execution_authorized':False, 'holdout_opened':False,
              'provider_calls_by_auditor':0, 'independently_verified_source':False,
              'source_identity':implementation_identity()}
    artifacts = {}
    try:
        store = Store(Path(root))
        # Manifest is bounded too; it has no trusted hash supplied externally.
        require(not (store.root/'.incomplete').exists(), 'INCOMPLETE_BUNDLE')
        p = store.root/'bundle.json'
        require(not p.is_symlink(), 'SYMLINK_FORBIDDEN')
        with p.open('rb') as stream:
            raw_manifest = stream.read(MAX_FILE+1)
        m = strict_json(raw_manifest)
        keys(m, {'schema','provider','origin','symbol','start_date','end_date','captured_at','raw','license_review','market_facts','normalized_candidate'})
        require(m['schema'] == SCHEMA and m['provider'] == 'tushare', 'UNSUPPORTED_BUNDLE_SCHEMA')
        require(m['origin'] in ('synthetic_fixture','provider_export'), 'ORIGIN_REQUIRED')
        require(is_mainboard_symbol(m['symbol']), 'SYMBOL_UNSUPPORTED')
        start,end,captured = day(m['start_date']),day(m['end_date']),instant(m['captured_at'])
        require(start <= end and (end-start).days <= 365, 'SAMPLE_RANGE')
        require(end <= captured.date() and captured <= checked, 'CAPTURE_TIME_ORDER')
        keys(m['raw'], set(REQUIRED))
        report.update(origin=m['origin'], sample={'symbol':m['symbol'],'start':m['start_date'],'end':m['end_date']},
                      manifest_sha256=sha(raw_manifest), captured_at=captured.isoformat())
        tables, hashes, fields = {}, {}, {}
        for endpoint in REQUIRED:
            raw = store.read(m['raw'][endpoint]); hashes[endpoint] = sha(raw)
            tables[endpoint], fields[endpoint] = _table(raw,endpoint)
        report['raw_files'] = {n:{'sha256':hashes[n],'rows':len(tables[n]),'fields':fields[n]} for n in REQUIRED}
        ds, csv_text, cal_text, lineage, issues, days, opens, _ = _normalize(m,tables,hashes)
        if end == captured.date() and captured.time() < time(16):
            issues.append({'code':'CAPTURE_BEFORE_DECLARED_EOD_CUTOFF','date':end.isoformat()})
        report['issues'].extend(issues)
        report['candidate_comparison'] = _candidate(store,m['normalized_candidate'],ds)
        if report['candidate_comparison']['status'] == 'MISMATCH':
            report['issues'].append({'code':'RAW_NORMALIZED_MISMATCH'})
        report['license_review'] = _license(store,m['license_review'],m,checked)
        report['market_facts'] = _facts(store,m['market_facts'],m,checked,days,opens,ds)
        report['normalized_dataset_id'] = ds['id']
        report['lineage'] = lineage
        report['core_execution_blockers'] = sorted({b['code'] for b in ds['audit']['backtest_blockers']})
        report['integrity'] = 'MATCHED_WITH_BLOCKERS' if issues or report['candidate_comparison']['status'] == 'MISMATCH' else 'RAW_MAPPING_CHECKED'
        report['review_state'] = 'AWAITING_INDEPENDENT_REVIEW' if (report['integrity']=='RAW_MAPPING_CHECKED' and report['license_review']['status']=='DECLARED_SCOPE_MATCH' and report['market_facts']['status']=='CLAIM_STRUCTURE_CONSISTENT') else 'EVIDENCE_INCOMPLETE'
        if m['origin'] == 'synthetic_fixture':
            report['review_state'] = 'SYNTHETIC_FIXTURE_ONLY'
        report['attachment_hashes'] = {n:sha(raw) for n,raw in sorted(store.cache.items())}
        report['notes'] = ['原始字节与逐行转换已核对，不证明供应商真实性或法律授权。',
                           '执行字段仍保留未知；不会生成可解锁旧 evaluation/opening 的授权记录。',
                           '日线整日OHLC/成交量不能证明开盘时已知流动性。',
                           '外部事实及许可为用户提交的声明，须独立审阅；报告与规范化文件仅留本机。']
        artifacts = {'normalized.json':canonical(ds), 'prices.csv':csv_text.encode('utf-8'), 'calendar.csv':cal_text.encode('utf-8')}
    except IntakeError as exc:
        report['issues'].append({'code':exc.code})
    except (OSError, KeyError, TypeError, UnicodeError, OverflowError, InvalidOperation):
        report['issues'].append({'code':'UNREADABLE_OR_MALFORMED_INPUT'})
    report['report_id'] = sha(canonical(report))
    return {'report':report, 'artifacts':artifacts,
            'context':{'checked_at':checked.isoformat(),'as_of_is_caller_declared':as_of is not None}}


def implementation_identity() -> dict:
    root = Path(__file__).resolve().parents[2]
    paths = ['integrations/market_evidence/intake.py','invest/data.py']
    return {p:sha((root/p).read_text(encoding='utf-8').encode('utf-8')) for p in paths}


def assemble_exports(raw_directory: Path, output: Path, *, symbol: str,
                     start_date: str, end_date: str, captured_at: str) -> None:
    """Bind existing response bytes into a NEW local bundle; no acquisition.

    Filenames are daily.json, adj_factor.json, stk_limit.json, trade_cal.json.
    The caller supplies capture time; neither it nor provenance is attested.
    License and market evidence start missing, never filled by this command.
    """
    source, output = Path(raw_directory).resolve(strict=True), Path(output)
    require(is_mainboard_symbol(symbol), 'SYMBOL_UNSUPPORTED')
    start,end = day(start_date),day(end_date)
    captured = instant(captured_at)
    require(start <= end and (end-start).days <= 365 and end <= captured.date(), 'SAMPLE_RANGE')
    require(captured <= datetime.now(CST), 'CAPTURE_TIME_ORDER')
    require(not output.exists() and not output.is_symlink(), 'OUTPUT_EXISTS')
    require(not output.resolve().is_relative_to(source), 'OUTPUT_INSIDE_INPUT')
    m = dict(schema=SCHEMA,provider='tushare',origin='provider_export',symbol=symbol,
             start_date=start_date,end_date=end_date,captured_at=captured.isoformat(),
             raw={},license_review=None,market_facts=None,normalized_candidate=None)
    blobs = {}
    for endpoint in REQUIRED:
        p = source/(endpoint+'.json')
        require(not p.is_symlink(), 'SYMLINK_FORBIDDEN')
        with p.open('rb') as stream:
            raw = stream.read(MAX_FILE+1)
        _table(raw,endpoint)
        name = 'raw/'+endpoint+'.json'
        blobs[name]=raw
        m['raw'][endpoint]={'path':name,'sha256':sha(raw)}
    output.mkdir(parents=True,exist_ok=False)
    (output/'.incomplete').write_text('Assembly incomplete.\n',encoding='utf-8')
    (output/'raw').mkdir()
    for name,raw in blobs.items():
        with (output/name).open('xb') as stream:
            stream.write(raw)
    with (output/'bundle.json').open('xb') as stream:
        stream.write(canonical(m))
    (output/'.incomplete').unlink()
