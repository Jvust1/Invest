"""Explicit local acquisition; no live calls on import, plan, audit, or tests.

Only collect() may read a credential and call the fixed TLS endpoint. Access is
user-declared, not legally authenticated. Receipts are local provenance records,
not independent attestations. No broker/evaluation/holdout capability is added.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import getpass
import http.client
import os
from pathlib import Path
import re
import ssl
import time
from typing import Callable
import warnings

from .intake import (CST, MAX_FILE, REQUIRED, IntakeError, _table, assemble_exports,
                     audit_bundle, canonical, day, is_mainboard_symbol, sha,
                     strict_json)
from .report import write_report

HOST = 'api.tushare.pro'
URL = 'https://' + HOST + '/'
SCHEMA = 'invest-local-acquisition-v1'


class AcquisitionError(ValueError):
    """Fixed diagnostics only. Never interpolate provider messages or paths."""
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def check(ok: bool, code: str) -> None:
    if not ok:
        raise AcquisitionError(code)


def now() -> datetime:
    return datetime.now(CST)


def plan(symbol: str, start_date: str, end_date: str, *, clock=now) -> dict:
    check(is_mainboard_symbol(symbol), 'SYMBOL_UNSUPPORTED')
    try:
        start, end = day(start_date), day(end_date)
    except IntakeError:
        raise AcquisitionError('DATE_FORMAT') from None
    check(start <= end and (end-start).days <= 365, 'SAMPLE_RANGE')
    # Do not request the still-changing current daily session by default.
    check(end < clock().astimezone(CST).date(), 'CLOSED_HISTORY_REQUIRED')
    common = {'start_date': start.strftime('%Y%m%d'), 'end_date': end.strftime('%Y%m%d')}
    requests = []
    for api, fields in REQUIRED.items():
        params = dict(common)
        params.update({'exchange': 'SSE' if symbol.endswith('.SH') else 'SZSE'}
                      if api == 'trade_cal' else {'ts_code': symbol})
        requests.append({'api_name': api, 'params': params, 'fields': ','.join(fields)})
    return {'schema': SCHEMA, 'endpoint': URL, 'symbol': symbol,
            'start_date': start_date, 'end_date': end_date, 'requests': requests,
            'max_requests': 4, 'automatic_retries': 0, 'execution_authorized': False}


def _regular_bytes(path: Path) -> bytes:
    path = Path(path).absolute()
    check(not any(p.is_symlink() for p in (path, *path.parents)), 'SYMLINK_FORBIDDEN')
    check(path.is_file(), 'LOCAL_EVIDENCE_REQUIRED')
    with path.open('rb') as stream:
        raw = stream.read(MAX_FILE + 1)
    check(0 < len(raw) <= MAX_FILE, 'LOCAL_EVIDENCE_SIZE')
    return raw


def preflight(spec: dict, output: Path, evidence: Path, *, access_declared: bool,
              network_allowed: bool, clock=now) -> dict:
    check(access_declared is True, 'ACCESS_CONFIRMATION_REQUIRED')
    check(network_allowed is True, 'NETWORK_CONFIRMATION_REQUIRED')
    check(spec == plan(spec.get('symbol'), spec.get('start_date'), spec.get('end_date'), clock=clock),
          'PLAN_CHANGED')
    output = Path(output).absolute()
    check(not output.exists() and not output.is_symlink(), 'OUTPUT_EXISTS')
    check(output.parent.is_dir(), 'OUTPUT_PARENT_REQUIRED')
    check(not any(p.is_symlink() for p in output.parents), 'SYMLINK_FORBIDDEN')
    raw = _regular_bytes(evidence)
    # Known supplied fixtures must not masquerade as user access evidence.
    check(b'SYNTHETIC' not in raw.upper(), 'TEST_EVIDENCE_FORBIDDEN')
    return {'artifact_sha256': sha(raw), 'bytes': len(raw),
            'status': 'USER_DECLARED_ACCESS_NOT_INDEPENDENTLY_VERIFIED'}


def read_credential() -> str:
    value = os.environ.get('TUSHARE_TOKEN')
    if value is None:
        # getpass normally falls back to echoing input when no secure terminal
        # exists. Here that warning becomes an error instead.
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            try:
                value = getpass.getpass('Tushare Token (local hidden input): ')
            except (EOFError, getpass.GetPassWarning):
                raise AcquisitionError('HIDDEN_INPUT_UNAVAILABLE') from None
    check(type(value) is str and re.fullmatch(r'[A-Za-z0-9_-]{16,256}', value) is not None,
          'CREDENTIAL_FORMAT')
    return value


def https_post(body: bytes) -> bytes:
    """One bounded POST, certificate/hostname verification, no redirects/proxies.

    Direct HTTPS deliberately ignores HTTP(S)_PROXY. An unavailable TLS route
    fails rather than falling back to plaintext or a third-party API proxy.
    """
    connection = http.client.HTTPSConnection(HOST, 443, timeout=30,
                                             context=ssl.create_default_context())
    try:
        connection.request('POST', '/', body=body,
                           headers={'Content-Type': 'application/json',
                                    'Accept': 'application/json',
                                    'Accept-Encoding': 'identity',
                                    'User-Agent': 'Invest-Local-Acquisition/0.1'})
        response = connection.getresponse()
        check(response.status == 200, 'HTTP_STATUS_REJECTED')
        content_type = response.getheader('Content-Type', '').split(';')[0].lower().strip()
        check(content_type == 'application/json', 'RESPONSE_CONTENT_TYPE')
        check(response.getheader('Content-Encoding', 'identity').lower() == 'identity',
              'RESPONSE_ENCODING_REJECTED')
        size = response.getheader('Content-Length')
        if size is not None:
            check(size.isdigit() and 0 < int(size) <= MAX_FILE, 'RESPONSE_SIZE')
        raw = response.read(MAX_FILE + 1)
        check(0 < len(raw) <= MAX_FILE, 'RESPONSE_SIZE')
        if size is not None:
            check(len(raw) == int(size), 'RESPONSE_TRUNCATED')
        return raw
    except AcquisitionError:
        raise
    except Exception:
        # Includes SSL, DNS, timeout and low-level HTTP errors. Never echo them.
        raise AcquisitionError('TLS_OR_NETWORK_ERROR') from None
    finally:
        connection.close()


def _contains(value, credential: str) -> bool:
    if isinstance(value, str):
        return credential in value
    if isinstance(value, dict):
        return any(_contains(k, credential) or _contains(v, credential) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains(v, credential) for v in value)
    return False


def _validate_response(raw: bytes, api: str, credential: str, spec: dict) -> int:
    check(type(raw) is bytes and 0 < len(raw) <= MAX_FILE, 'RESPONSE_SIZE')
    check(credential.encode('ascii') not in raw, 'SENSITIVE_RESPONSE_REJECTED')
    try:
        payload = strict_json(raw)
        check(not _contains(payload, credential), 'SENSITIVE_RESPONSE_REJECTED')
        check(type(payload) is dict, 'RESPONSE_SCHEMA')
        if type(payload.get('code')) is int and payload['code'] != 0:
            raise AcquisitionError('PROVIDER_ACCESS_REJECTED' if payload['code'] == 2002
                                   else 'PROVIDER_REPORTED_FAILURE')
        rows, fields = _table(raw, api)
        check(set(fields) == set(REQUIRED[api]), 'UNREQUESTED_FIELDS')
        check(payload.get('msg') in (None, ''), 'UNEXPECTED_SUCCESS_MESSAGE')
        check(len(rows) <= (day(spec['end_date'])-day(spec['start_date'])).days+1,
              'EXCESS_ROWS')
        # Complete cross-endpoint and numeric checks are done by the unchanged auditor.
        return len(rows)
    except IntakeError:
        raise AcquisitionError('RESPONSE_SCHEMA') from None


def _write(path: Path, raw: bytes) -> None:
    with path.open('xb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())


def implementation_identity() -> dict:
    root = Path(__file__).resolve().parents[2]
    paths = ['integrations/market_evidence/acquisition.py', 'tools/collect_market_data.py',
             'integrations/market_evidence/intake.py', 'integrations/market_evidence/report.py',
             'invest/data.py']
    files = {p: sha((root/p).read_text(encoding='utf-8').encode('utf-8')) for p in paths}
    return {'schema': 'invest-collection-source-v1', 'files': files, 'sha256': sha(canonical(files))}


def _checkpoint(output: Path, receipt: dict) -> None:
    raw = canonical(dict(receipt, receipt_id=sha(canonical(receipt))))
    pending = output/'collection.next.json'
    # Only this process's previously owned checkpoint is replaced.
    _write(pending, raw)
    pending.replace(output/'collection.json')


def _collect(spec: dict, output: Path, evidence: Path, *, access_declared: bool,
             network_allowed: bool, credential_reader: Callable[[], str],
             transport: Callable[[bytes], bytes], mode: str, clock=now,
             pause: Callable[[float], None] = time.sleep) -> dict:
    """Private dependency-injection seam. Non-live transports are marked TEST."""
    access = preflight(spec, output, evidence, access_declared=access_declared,
                       network_allowed=network_allowed, clock=clock)
    credential = credential_reader()
    check(type(credential) is str and re.fullmatch(r'[A-Za-z0-9_-]{16,256}', credential) is not None,
          'CREDENTIAL_FORMAT')
    # Neither paths nor evidence body are included in the receipt.
    check(credential.encode() not in canonical(spec), 'CREDENTIAL_IN_PLAN')
    output = Path(output).absolute()
    output.mkdir(mode=0o700, exist_ok=False)
    _write(output/'.incomplete', b'Incomplete collection; do not use as a finished bundle.\n')
    (output/'raw').mkdir(mode=0o700)
    receipt = {'schema': SCHEMA, 'mode': mode, 'plan': spec, 'access_evidence': access,
               'started_at': clock().isoformat(), 'attempts': [], 'status': 'IN_PROGRESS',
               'implementation': implementation_identity(),
               'real_data_verified': False, 'execution_authorized': False,
               'independent_license_review': False, 'credential_persisted': False,
               'request_bodies_persisted': False, 'provider_messages_persisted': False}
    _checkpoint(output, receipt)
    try:
        for index, request in enumerate(spec['requests']):
            if index:
                pause(1.0)
            record = dict(request, started_at=clock().isoformat(), status='ATTEMPT_STARTED')
            receipt['attempts'].append(record)
            _checkpoint(output, receipt)
            try:
                body = canonical(dict(request, token=credential))
                raw = transport(body)
                row_count = _validate_response(raw, request['api_name'], credential, spec)
                path = output/'raw'/(request['api_name']+'.json')
                _write(path, raw)
                record.update(status='RESPONSE_SAVED', finished_at=clock().isoformat(),
                              bytes=len(raw), sha256=sha(raw), rows=row_count)
                _checkpoint(output, receipt)
            except BaseException as exc:
                record.update(status='FAILED', finished_at=clock().isoformat(),
                              error_code=exc.code if isinstance(exc, AcquisitionError) else
                              ('INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'REQUEST_FAILED'))
                raise
        captured_at = receipt['attempts'][-1]['finished_at']
        assemble_exports(output/'raw', output/'bundle', symbol=spec['symbol'],
                         start_date=spec['start_date'], end_date=spec['end_date'],
                         captured_at=captured_at)
        if mode != 'LIVE_HTTPS':
            # Test data can never leave the seam marked as provider acquisition.
            p = output/'bundle'/'bundle.json'
            m = strict_json(p.read_bytes()); m['origin'] = 'synthetic_fixture'
            p.write_bytes(canonical(m))
        result = audit_bundle(output/'bundle')
        write_report(result, output/'review', input_root=output/'bundle')
        report = result['report']
        receipt.update(status='CAPTURED_MAPPING_CHECKED' if report['integrity']=='RAW_MAPPING_CHECKED'
                       else 'CAPTURED_WITH_DATA_BLOCKERS',
                       integrity=report['integrity'], review_state=report.get('review_state'),
                       report_id=report['report_id'], completed_at=clock().isoformat(),
                       raw_complete=True, independent_market_facts=False)
        _checkpoint(output, receipt)
        (output/'.incomplete').unlink()
    except BaseException as exc:
        receipt.update(status='FAILED', completed_at=clock().isoformat(),
                       error_code=exc.code if isinstance(exc, (AcquisitionError, IntakeError)) else
                       ('INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'COLLECTION_OR_AUDIT_FAILED'))
        _checkpoint(output, receipt)
        # Keep the marker and already saved originals. Never manufacture the other responses.
    finally:
        credential = ''  # Best effort, NOT a Python memory-zeroization guarantee.
    return receipt


def collect(spec: dict, output: Path, evidence: Path, *, access_declared: bool = False,
            network_allowed: bool = False) -> dict:
    """The only production network entry. No custom endpoints/transports accepted."""
    return _collect(spec, output, evidence, access_declared=access_declared,
                    network_allowed=network_allowed, credential_reader=read_credential,
                    transport=https_post, mode='LIVE_HTTPS')
