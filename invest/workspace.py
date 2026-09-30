"""Immutable, content-addressed workbench documents in the existing state DB.

No provider calls, secrets, file-system paths or real-order APIs are accepted.
The SQLite online backup used by the desktop also includes these tables.
"""
from __future__ import annotations
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode('utf-8')).hexdigest()


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def text(value, name, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{name}必须为1–{limit}字符文本')
    if any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError(f'{name}含有控制字符')
    return value.strip()


def instant(value):
    value = text(value, '带时区时间', 40)
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise ValueError('时间格式错误') from None
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError('时间必须明确时区，例如 +08:00')
    return result.astimezone(timezone.utc)


class Workspace:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            db.executescript('''
CREATE TABLE IF NOT EXISTS growth_documents(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, payload TEXT NOT NULL, recorded_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS growth_events(
 stream TEXT NOT NULL, sequence INTEGER NOT NULL, event_key TEXT NOT NULL,
 payload TEXT NOT NULL, previous_hash TEXT NOT NULL, hash TEXT NOT NULL,
 recorded_at TEXT NOT NULL, PRIMARY KEY(stream, sequence), UNIQUE(stream,event_key));
CREATE TRIGGER IF NOT EXISTS growth_docs_no_update BEFORE UPDATE ON growth_documents
 BEGIN SELECT RAISE(ABORT,'immutable growth document'); END;
CREATE TRIGGER IF NOT EXISTS growth_docs_no_delete BEFORE DELETE ON growth_documents
 BEGIN SELECT RAISE(ABORT,'immutable growth document'); END;
CREATE TRIGGER IF NOT EXISTS growth_events_no_update BEFORE UPDATE ON growth_events
 BEGIN SELECT RAISE(ABORT,'append-only growth event'); END;
CREATE TRIGGER IF NOT EXISTS growth_events_no_delete BEFORE DELETE ON growth_events
 BEGIN SELECT RAISE(ABORT,'append-only growth event'); END;
''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(str(self.path), timeout=15, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA busy_timeout=15000')
        try:
            yield db
        finally:
            if db.in_transaction:
                db.rollback()
            db.close()

    def put(self, kind, payload):
        if kind not in {'study', 'facts', 'review', 'receipt', 'native_research'}:
            raise ValueError('文档类型不支持')
        if kind == 'native_research':
            from .native_research import validate_native_research
            validate_native_research(payload)
        raw = canonical(payload)
        if len(raw.encode()) > 8 * 1024 * 1024:
            raise ValueError('单个研究文档超过8MiB限制')
        key = digest({'kind': kind, 'payload': payload})
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO growth_documents VALUES(?,?,?,?)',
                       (key, kind, raw, utcnow()))
        return self.get(key, kind)

    @staticmethod
    def _decode(row):
        raw = row['payload']
        if row['kind'] == 'native_research':
            # Check restored native data before parse/allocation. A malicious or
            # foreign SQLite document may bypass Workspace.put's write guard.
            if type(raw) is not str or len(raw) > 8 * 1024 * 1024 or len(raw.encode('utf-8')) > 8 * 1024 * 1024:
                raise ValueError('native research exceeds 8 MiB')
            from .native_research import parse_native_json
            payload = parse_native_json(raw)
            if type(payload) is not dict:
                raise ValueError('native research payload must be a JSON object')
            instant(row['recorded_at'])
        else:
            payload = json.loads(raw)
        if digest({'kind': row['kind'], 'payload': payload}) != row['id']:
            raise ValueError('研究文档内容身份校验失败')
        return {'id': row['id'], 'kind': row['kind'], 'recorded_at': row['recorded_at'], 'payload': payload}

    def get(self, key, kind=None):
        if not isinstance(key, str) or not re.fullmatch('[a-f0-9]{64}', key):
            raise ValueError('文档ID无效')
        with self.connection() as db:
            row = db.execute('SELECT * FROM growth_documents WHERE id=?', (key,)).fetchone()
        if row is None or (kind is not None and kind != row['kind']):
            raise ValueError('文档不存在或类型不符')
        return self._decode(row)

    def list(self, kind):
        with self.connection() as db:
            rows = db.execute('SELECT * FROM growth_documents WHERE kind=? ORDER BY recorded_at DESC,id LIMIT 100', (kind,)).fetchall()
        return [self._decode(r) for r in rows]

    def list_summaries(self, kind):
        """Identity-only listing with one payload resident at a time.

        No arithmetic replay. A native document is fully checked on explicit
        download/validation, rather than executing up to 100 trial suites here.
        """
        output = []
        with self.connection() as db:
            rows = db.execute('SELECT * FROM growth_documents WHERE kind=? ORDER BY recorded_at DESC,id LIMIT 100', (kind,))
            for row in rows:
                document = self._decode(row)
                payload = document['payload']
                summary = payload.get('summary')
                name = payload.get('name', payload.get('source_name', document['id'][:12]))
                if kind == 'native_research':
                    # A resealed foreign row must not make the tiny list response
                    # retain another large nested payload or arbitrary free text.
                    name = document['id'][:12]
                    fields = {'total_return', 'annualized_return', 'annualized_volatility', 'sharpe', 'max_drawdown'}
                    if (type(summary) is not dict or set(summary) != fields
                            or any(type(v) not in (int, float) or not -1e308 <= v <= 1e308
                                   or not math.isfinite(v) for v in summary.values())):
                        raise ValueError('native research listing summary shape is invalid')
                output.append({'id': document['id'], 'kind': kind, 'recorded_at': document['recorded_at'],
                    'name': name, 'summary': summary})
                del document, payload, row, summary
        return output

    @staticmethod
    def events_in(db, stream):
        rows = db.execute('SELECT * FROM growth_events WHERE stream=? ORDER BY sequence', (stream,)).fetchall()
        output, previous = [], '0' * 64
        for expected, row in enumerate(rows, 1):
            event = json.loads(row['payload'])
            record = {'stream': stream, 'sequence': expected, 'event_key': row['event_key'],
                      'event': event, 'previous_hash': previous, 'recorded_at': row['recorded_at']}
            if row['sequence'] != expected or row['previous_hash'] != previous or digest(record) != row['hash']:
                raise ValueError('事件链顺序或内容哈希不一致')
            record['hash'] = previous = row['hash']
            output.append(record)
        return output

    def events(self, stream):
        with self.connection() as db:
            return self.events_in(db, stream)

    def append(self, stream, key, event, validator):
        key = text(key, '幂等键', 100)
        canonical(event)  # reject NaN/Inf before beginning a transaction
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            records = self.events_in(db, stream)
            for record in records:
                if record['event_key'] == key:
                    if canonical(record['event']) != canonical(event):
                        raise ValueError('同一幂等键不能对应不同内容')
                    db.commit()
                    return record
            # Existing committed retries remain valid when the stream is full.
            if len(records) >= 10000:
                raise ValueError('单个复盘账户超过10000条事件限制')
            validator([r['event'] for r in records] + [event])
            record = {'stream': stream, 'sequence': len(records) + 1, 'event_key': key,
                      'event': event, 'previous_hash': records[-1]['hash'] if records else '0' * 64,
                      'recorded_at': utcnow()}
            h = digest(record)
            db.execute('INSERT INTO growth_events VALUES(?,?,?,?,?,?,?)',
                       (stream, record['sequence'], key, canonical(event), record['previous_hash'], h, record['recorded_at']))
            db.commit()
        return dict(record, hash=h)
