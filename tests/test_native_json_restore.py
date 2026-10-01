"""Bounded, immutable native JSON recovery; no SDK, provider or producer calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
import builtins
import io
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import threading
from urllib.request import build_opener, ProxyHandler

import pytest

from examples import native_research_record as cli
from invest import native_research as native
from invest.server import encode_json
from invest.workspace import Workspace, canonical, digest
from test_mlflow_local import http_server

FIXTURE = Path(__file__).with_name('fixtures') / 'native_research_v1_synthetic.json'
OPTIONAL_SDKS = {'duckdb', 'optuna', 'qlib', 'pyqlib', 'mlflow', 'matplotlib'}


@pytest.fixture(autouse=True)
def no_optional_work(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        assert name.split('.')[0] not in OPTIONAL_SDKS, 'unexpected optional import: ' + name
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, '__import__', guarded)
    forbidden = lambda *a, **k: pytest.fail('restore invoked producer/provider/runtime discovery')
    monkeypatch.setattr(native, '_producer', forbidden)
    monkeypatch.setattr(native, 'runtime_manifest', forbidden)
    monkeypatch.setattr(native.metadata, 'version', forbidden)
    monkeypatch.setattr(native.DuckDBReplayProvider, 'history', forbidden)
    monkeypatch.setattr(native, 'run_a_share_research_bundle', forbidden)


@pytest.fixture
def record():
    return json.loads(FIXTURE.read_text(encoding='utf-8'))


def rows(path):
    with sqlite3.connect(path) as db:
        return db.execute('SELECT * FROM growth_documents ORDER BY id').fetchall()


def test_restore_reopen_and_identical_repeat_preserve_entire_envelope(tmp_path, record):
    path = tmp_path / 'empty' / 'state.sqlite'
    assert not path.parent.exists()
    restored = native.restore_native_json(FIXTURE.read_text(encoding='utf-8'), path)
    assert canonical(restored) == canonical(record)
    reopened = Workspace(path).get(record['id'], native.KIND)
    assert canonical(reopened) == canonical(record)
    assert reopened['recorded_at'] == record['recorded_at']
    assert reopened['payload']['producer'] == record['payload']['producer']
    assert native.validate_native_record(reopened) == record
    # Python equality alone cannot establish exact numeric JSON types.
    assert canonical(native.restore_native_json(canonical(record), path)) == canonical(record)
    assert len(rows(path)) == 1
    assert Workspace(path).list(native.KIND) == [record]
    assert Workspace(path).list_summaries(native.KIND)[0]['recorded_at'] == record['recorded_at']
    assert Workspace(path).events('restore') == []
    assert not (path.parent / 'native.duckdb').exists()
    assert not (path.parent / 'mlflow').exists()


@pytest.mark.parametrize('timestamp', ['2001-01-01T00:00:00+00:00', '2026-09-30T10:20:30+00:00',
                                     '2026-09-30T18:20:30+08:00', '2026-09-30T10:20:30Z'])
def test_timestamp_declaration_preserved_without_normalization(tmp_path, record, timestamp):
    record['recorded_at'] = timestamp
    assert native.restore_native_json(canonical(record), tmp_path / 'state.sqlite') == record
    assert Workspace(tmp_path / 'state.sqlite').get(record['id'])['recorded_at'] == timestamp


@pytest.mark.parametrize('timestamp', ['2000-01-01T00:00:00+00:00', '2026-09-30T10:20:30Z'])
def test_same_id_different_timestamp_is_a_conflict_even_for_same_instant(tmp_path, record, timestamp):
    record['recorded_at'] = '2026-09-30T10:20:30+00:00'
    path = tmp_path / 'state.sqlite'
    native.restore_native_json(canonical(record), path)
    before = rows(path)
    changed = dict(record, recorded_at=timestamp)
    assert changed['id'] == record['id']  # Timestamp is deliberately outside ID.
    with pytest.raises(ValueError, match='conflicts'):
        native.restore_native_json(canonical(changed), path)
    assert rows(path) == before
    assert Workspace(path).get(record['id']) == record


def invalid_raw(case, record):
    if case == 'malformed':
        return '{'
    if case == 'duplicate':
        return '{"id":"duplicate",' + canonical(record)[1:]
    if case == 'oversized':
        return ' ' * (native.MAX_BYTES + 1)
    if case == 'utf8_size':
        return 'é' * (native.MAX_BYTES // 2 + 1)
    if case == 'depth':
        return '[' * 14 + '0' + ']' * 14
    if case == 'recursion':
        return '[' * 1200 + '0' + ']' * 1200
    if case == 'nan':
        record['payload']['training_fraction'] = float('nan')
        return json.dumps(record)
    if case == 'not_text':
        return record
    if case == 'cash':
        record['kind'] = 'study'
        record['payload'] = {'schema': 'invest-study-v1'}
    elif case == 'cash_payload':
        record['payload'] = {'schema': 'invest-study-v1'}
    elif case == 'arithmetic':
        record['payload']['summary']['sharpe'] += 1
    elif case == 'numeric_identity':
        value = record['payload']['input']['rows'][0][4]
        assert type(value) is float and value.is_integer()
        record['payload']['input']['rows'][0][4] = int(value)
        return canonical(record)
    elif case == 'identity':
        record['id'] = '0' * 64
        return canonical(record)
    elif case == 'envelope':
        record['extra'] = 'unexpected'
    elif case == 'timestamp':
        record['recorded_at'] = 'yesterday'
    else:
        raise AssertionError(case)
    record['id'] = digest({'kind': record['kind'], 'payload': record['payload']})
    return canonical(record)


@pytest.mark.parametrize('case', ['malformed', 'duplicate', 'oversized', 'utf8_size', 'depth',
    'recursion', 'nan', 'not_text', 'cash', 'cash_payload', 'arithmetic', 'numeric_identity',
    'identity', 'envelope', 'timestamp'])
def test_invalid_import_has_no_destination_writes(tmp_path, record, case):
    path = tmp_path / 'must-not-exist' / 'state.sqlite'
    with pytest.raises(ValueError):
        native.restore_native_json(invalid_raw(case, record), path)
    assert not path.parent.exists()


@pytest.mark.parametrize('case', ['malformed', 'duplicate', 'oversized', 'cash', 'arithmetic'])
def test_failed_import_does_not_change_existing_records(tmp_path, record, case):
    path = tmp_path / 'state.sqlite'
    native.restore_native_json(canonical(record), path)
    before = rows(path)
    with pytest.raises(ValueError):
        native.restore_native_json(invalid_raw(case, deepcopy(record)), path)
    assert rows(path) == before


@pytest.mark.parametrize('conflict', ['kind', 'payload', 'timestamp', 'duplicate'])
def test_foreign_conflicting_same_id_row_is_never_overwritten(tmp_path, record, conflict):
    path = tmp_path / 'state.sqlite'
    workspace = Workspace(path)
    kind, payload, timestamp = native.KIND, canonical(record['payload']), record['recorded_at']
    if conflict == 'kind':
        kind = 'study'
    elif conflict == 'payload':
        payload = '{}'
    elif conflict == 'timestamp':
        timestamp = 'not-a-time'
    else:
        payload = '{"schema":"duplicate",' + payload[1:]
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)', (record['id'], kind, payload, timestamp))
    before = rows(path)
    with pytest.raises(ValueError):
        native.restore_native_json(canonical(record), path)
    assert rows(path) == before


@pytest.mark.parametrize('payload', ['{', '[' * 2000 + '0' + ']' * 2000,
                                    ' ' * (native.MAX_BYTES + 1)],
                         ids=['malformed', 'deep', 'oversized'])
def test_foreign_kind_conflict_is_rejected_without_decoding(tmp_path, record, monkeypatch, payload):
    path = tmp_path / 'state.sqlite'
    workspace = Workspace(path)
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (record['id'], 'study', payload, record['recorded_at']))
    before = rows(path)
    monkeypatch.setattr(Workspace, '_decode', lambda *a: pytest.fail('foreign payload was decoded'))
    with pytest.raises(ValueError, match='conflicts'):
        native.restore_native_json(canonical(record), path)
    assert rows(path) == before


@pytest.mark.parametrize('case', ['foreign_kind', 'casefold_kind', 'large_kind', 'large_payload', 'blob_payload',
                                'large_timestamp', 'nul_timestamp', 'blob_timestamp'])
def test_invalid_existing_header_never_fetches_payload_or_inserts(tmp_path, record, monkeypatch, case):
    path = tmp_path / 'state.sqlite'
    if case == 'casefold_kind':
        with sqlite3.connect(path) as db:
            db.execute('''CREATE TABLE growth_documents(id TEXT PRIMARY KEY,
                kind TEXT COLLATE NOCASE NOT NULL, payload TEXT NOT NULL, recorded_at TEXT NOT NULL)''')
    workspace = Workspace(path)
    kind, payload, timestamp = native.KIND, canonical(record['payload']), record['recorded_at']
    if case == 'foreign_kind':
        kind, payload = 'study', ' ' * (native.MAX_BYTES + 1)
    elif case == 'casefold_kind':
        kind, payload = native.KIND.upper(), '[' * 2000 + '0' + ']' * 2000
    elif case == 'large_kind':
        kind = 'x' * (native.MAX_BYTES + 1)
    elif case == 'large_payload':
        payload = ' ' * (native.MAX_BYTES + 1)
    elif case == 'blob_payload':
        payload = payload.encode('utf-8')
    elif case == 'large_timestamp':
        timestamp = 'x' * (native.MAX_BYTES + 1)
    elif case == 'nul_timestamp':
        timestamp = record['recorded_at'] + '\x00' + 'x' * (native.MAX_BYTES + 1)
    else:
        timestamp = timestamp.encode('utf-8')
    with workspace.connection() as db:
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)', (record['id'], kind, payload, timestamp))
    before = rows(path)
    original = Workspace.connection
    headers = []

    class HeaderOnly:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def execute(self, sql, *args):
            if sql.startswith('SELECT'):
                assert 'AS is_native' in sql, 'hostile existing payload was fetched'
                headers.append(sql)
            assert not sql.startswith('INSERT'), 'conflicting record was inserted'
            return self.db.execute(sql, *args)

    @contextmanager
    def bounded(self):
        with original(self) as db:
            yield HeaderOnly(db)

    monkeypatch.setattr(Workspace, 'connection', bounded)
    monkeypatch.setattr(Workspace, '_decode', lambda *a: pytest.fail('hostile row was decoded'))
    with pytest.raises(ValueError, match='conflicts'):
        native.restore_native_json(canonical(record), path)
    assert len(headers) == 1
    assert rows(path) == before


def test_only_explicit_envelope_columns_are_inserted_and_fetched(tmp_path, record, monkeypatch):
    path = tmp_path / 'state.sqlite'
    workspace = Workspace(path)
    with workspace.connection() as db:
        db.execute('ALTER TABLE growth_documents ADD COLUMN unexpected BLOB')
    original = Workspace.connection
    fetched = []

    class ExplicitColumns:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def execute(self, sql, *args):
            if sql.startswith('SELECT') and 'AS is_native' not in sql:
                assert sql.startswith('SELECT id,kind,payload,recorded_at FROM growth_documents')
                fetched.append(sql)
            if sql.startswith('INSERT'):
                assert sql.startswith('INSERT INTO growth_documents(id,kind,payload,recorded_at)')
            return self.db.execute(sql, *args)

    @contextmanager
    def explicit(self):
        with original(self) as db:
            yield ExplicitColumns(db)

    with monkeypatch.context() as patch:
        patch.setattr(Workspace, 'connection', explicit)
        assert native.restore_native_json(canonical(record), path) == record
    # A foreign row's unrelated column must never be materialized into Python by
    # restore. Insert it directly in a separate fixture DB with identical schema.
    second = tmp_path / 'foreign.sqlite'
    foreign = Workspace(second)
    with foreign.connection() as db:
        db.execute('ALTER TABLE growth_documents ADD COLUMN unexpected BLOB')
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?,zeroblob(?))',
                   (record['id'], native.KIND, canonical(record['payload']), record['recorded_at'], native.MAX_BYTES + 1))
    with monkeypatch.context() as patch:
        patch.setattr(Workspace, 'connection', explicit)
        assert native.restore_native_json(canonical(record), second) == record
    assert len(fetched) == 2
    with foreign.connection() as db:
        assert db.execute('SELECT length(unexpected) FROM growth_documents').fetchone()[0] == native.MAX_BYTES + 1


def test_foreign_rtrim_id_is_never_fetched_as_the_imported_identity(tmp_path, record, monkeypatch):
    path = tmp_path / 'state.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('''CREATE TABLE growth_documents(id TEXT COLLATE RTRIM PRIMARY KEY,
            kind TEXT NOT NULL,payload TEXT NOT NULL,recorded_at TEXT NOT NULL)''')
        db.execute('INSERT INTO growth_documents VALUES(?,?,?,?)',
                   (record['id'] + ' ' * (native.MAX_BYTES + 1), native.KIND,
                    canonical(record['payload']), record['recorded_at']))
    monkeypatch.setattr(Workspace, '_decode', lambda *a: pytest.fail('alternate ID was fetched'))
    with pytest.raises(sqlite3.IntegrityError):
        native.restore_native_json(canonical(record), path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT count(*) FROM growth_documents').fetchone()[0] == 1
        assert db.execute('SELECT length(id) FROM growth_documents').fetchone()[0] == 64 + native.MAX_BYTES + 1


def test_failed_insert_rolls_back_all_transaction_writes_and_can_retry(tmp_path, record):
    path = tmp_path / 'state.sqlite'
    workspace = Workspace(path)
    with workspace.connection() as db:
        db.execute('CREATE TABLE restore_probe(value TEXT)')
        db.executescript('''
CREATE TRIGGER forced_restore_failure BEFORE INSERT ON growth_documents
BEGIN
 INSERT INTO restore_probe VALUES('partial write');
 SELECT RAISE(FAIL, 'forced insert failure');
END;
''')
    with pytest.raises(sqlite3.IntegrityError, match='forced insert failure'):
        native.restore_native_json(canonical(record), path)
    assert rows(path) == []
    with workspace.connection() as db:
        assert db.execute('SELECT * FROM restore_probe').fetchall() == []
        db.execute('DROP TRIGGER forced_restore_failure')
    assert native.restore_native_json(canonical(record), path) == record


def test_silently_ignored_insert_cannot_report_success_or_leave_trigger_writes(tmp_path, record):
    path = tmp_path / 'state.sqlite'
    workspace = Workspace(path)
    with workspace.connection() as db:
        db.execute('CREATE TABLE restore_probe(value TEXT)')
        db.executescript('''
CREATE TRIGGER ignored_restore BEFORE INSERT ON growth_documents
BEGIN
 INSERT INTO restore_probe VALUES('partial write');
 SELECT RAISE(IGNORE);
END;
''')
    with pytest.raises(ValueError, match='did not insert'):
        native.restore_native_json(canonical(record), path)
    assert rows(path) == []
    with workspace.connection() as db:
        assert db.execute('SELECT * FROM restore_probe').fetchall() == []
        db.execute('DROP TRIGGER ignored_restore')
    assert native.restore_native_json(canonical(record), path) == record


@pytest.mark.parametrize('tamper', ['delete', 'substitute', 'oversize'])
def test_post_insert_tampering_is_detected_before_commit_and_rolled_back(tmp_path, record, tamper):
    path = tmp_path / 'state.sqlite'
    workspace = Workspace(path)
    with workspace.connection() as db:
        # Model a foreign database whose same-name immutability triggers were
        # replaced before import; production trigger definitions are unchanged.
        db.executescript('''
DROP TRIGGER growth_docs_no_update;
DROP TRIGGER growth_docs_no_delete;
CREATE TRIGGER growth_docs_no_update BEFORE UPDATE ON growth_documents BEGIN SELECT 1; END;
CREATE TRIGGER growth_docs_no_delete BEFORE DELETE ON growth_documents BEGIN SELECT 1; END;
CREATE TABLE restore_probe(value TEXT);
''')
        if tamper == 'delete':
            action = 'DELETE FROM growth_documents WHERE id=NEW.id;'
        elif tamper == 'substitute':
            action = "UPDATE growth_documents SET recorded_at='2001-01-01T00:00:00+00:00' WHERE id=NEW.id;"
        else:
            action = f'UPDATE growth_documents SET payload=CAST(zeroblob({native.MAX_BYTES + 1}) AS TEXT) WHERE id=NEW.id;'
        db.executescript(f'''
CREATE TRIGGER tamper_restored_record AFTER INSERT ON growth_documents
BEGIN
 INSERT INTO restore_probe VALUES('partial write');
 {action}
END;
''')
    with pytest.raises(ValueError, match='preserve|conflicts'):
        native.restore_native_json(canonical(record), path)
    assert rows(path) == []
    with workspace.connection() as db:
        assert db.execute('SELECT * FROM restore_probe').fetchall() == []
        db.execute('DROP TRIGGER tamper_restored_record')
    assert native.restore_native_json(canonical(record), path) == record


def test_commit_failure_rolls_back_insert_and_releases_lock(tmp_path, record, monkeypatch):
    path = tmp_path / 'state.sqlite'
    Workspace(path)
    original = Workspace.connection

    class FailedCommit:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def commit(self):
            assert self.db.in_transaction
            assert self.db.execute('SELECT count(*) FROM growth_documents').fetchone()[0] == 1
            raise sqlite3.OperationalError('forced commit failure')

    @contextmanager
    def failing(self):
        with original(self) as db:
            yield FailedCommit(db)

    with monkeypatch.context() as patch:
        patch.setattr(Workspace, 'connection', failing)
        with pytest.raises(sqlite3.OperationalError, match='forced commit failure'):
            native.restore_native_json(canonical(record), path)
    assert rows(path) == []
    assert native.restore_native_json(canonical(record), path) == record


@pytest.mark.parametrize('conflict', [False, True], ids=['same-record', 'conflicting-timestamp'])
def test_parallel_restore_serializes_check_and_insert(tmp_path, record, monkeypatch, conflict):
    path = tmp_path / 'state.sqlite'
    assert not path.exists()
    original = Workspace.connection
    begin = threading.Barrier(2, timeout=10)
    leader_locked, follower_attempted = threading.Event(), threading.Event()
    inserted, release = threading.Event(), threading.Event()
    role = threading.local()

    class Coordinated:
        def __init__(self, db):
            self.db = db

        def __getattr__(self, name):
            return getattr(self.db, name)

        def execute(self, sql, *args):
            if sql == 'BEGIN IMMEDIATE':
                begin.wait()
                if role.name == 'leader':
                    result = self.db.execute(sql, *args)
                    leader_locked.set()
                    return result
                assert leader_locked.wait(10)
                follower_attempted.set()
            result = self.db.execute(sql, *args)
            if sql.startswith('INSERT INTO growth_documents') and role.name == 'leader':
                inserted.set()
                assert release.wait(10)
            return result

    @contextmanager
    def coordinated(self):
        with original(self) as db:
            yield Coordinated(db)

    def restore(name, value):
        role.name = name
        return native.restore_native_json(canonical(value), path)

    changed = deepcopy(record)
    if conflict:
        changed['recorded_at'] = '2001-01-01T00:00:00+00:00'
    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=2) as pool:
        patch.setattr(Workspace, 'connection', coordinated)
        leader = pool.submit(restore, 'leader', record)
        follower = pool.submit(restore, 'follower', changed)
        try:
            assert inserted.wait(10) and follower_attempted.wait(10)
            assert not leader.done() and not follower.done()
            assert rows(path) == []
        finally:
            release.set()
        assert leader.result(timeout=10) == record
        if conflict:
            with pytest.raises(ValueError, match='conflicts'):
                follower.result(timeout=10)
        else:
            assert canonical(follower.result(timeout=10)) == canonical(record)
    assert len(rows(path)) == 1
    assert canonical(Workspace(path).get(record['id'])) == canonical(record)


def test_cli_restore_requires_explicit_paths_and_preserves_record(tmp_path, record, capsys):
    destination = tmp_path / 'recovered'
    assert cli.main(['restore', str(FIXTURE), '--workspace', str(destination)]) == 0
    response = json.loads(capsys.readouterr().out)
    assert response['record_id'] == record['id'] and response['validated'] is True
    assert response['recorded_at'] == record['recorded_at']
    assert response['provenance'] == 'preserved_producer_and_timestamp_declarations_not_authenticated'
    assert canonical(Workspace(destination / 'state.sqlite').get(record['id'])) == canonical(record)
    with pytest.raises(SystemExit) as exc:
        cli.main(['restore', str(FIXTURE)])
    assert exc.value.code == 2


@pytest.mark.parametrize('command', ['restore', 'validate'])
@pytest.mark.parametrize('raw', [b'\xff', b' ' * (native.MAX_BYTES + 1), b'{'])
def test_cli_invalid_bytes_never_create_destination(tmp_path, command, raw):
    source = tmp_path / 'invalid.json'
    source.write_bytes(raw)
    destination = tmp_path / 'must-not-exist'
    args = [command, str(source)]
    if command == 'restore':
        args += ['--workspace', str(destination)]
    with pytest.raises(ValueError):
        cli.main(args)
    assert not destination.exists()


def test_cli_reads_max_plus_one_without_stat_or_unbounded_read(monkeypatch):
    calls = []

    class GrowingFile(io.BytesIO):
        def read(self, size=-1):
            calls.append(size)
            assert size == native.MAX_BYTES + 1
            return super().read(size)

    def open_file(self, mode):
        assert mode == 'rb'
        return GrowingFile(b' ' * (native.MAX_BYTES + 2))

    monkeypatch.setattr(Path, 'open', open_file)
    monkeypatch.setattr(Path, 'stat', lambda *a, **k: pytest.fail('stat/read race reintroduced'))
    with pytest.raises(ValueError, match='8 MiB'):
        cli.read_native_json('growing.json')
    assert calls == [native.MAX_BYTES + 1]


@pytest.mark.skipif(shutil.which('node') is None, reason='Node required for served-JS byte acceptance')
def test_empty_restore_http_list_raw_and_served_js_download(tmp_path, record):
    path = tmp_path / 'state.sqlite'
    native.restore_native_json(FIXTURE.read_text(encoding='utf-8'), path)
    output = tmp_path / 'served-js-download.json'
    script = r'''
const fs=require('node:fs'),vm=require('node:vm');
(async()=>{const [base,id,out]=process.argv.slice(1);
const source=await(await fetch(base+'/workbench.js')).text();
let result;const context={Blob,AbortSignal,encodeURIComponent,csrf:'',
fetch:(route,opts)=>fetch(base+route,opts),download:(blob,name)=>{result={blob,name};}};
vm.createContext(context);vm.runInContext(source.slice(source.indexOf('const MAX_DOCUMENT_BYTES='),source.indexOf('function action(')),context);
await context.savedRecordDownload(id,'native-'+id+'.json');
if(result.name!=='native-'+id+'.json')throw new Error('wrong filename');
fs.writeFileSync(out,Buffer.from(await result.blob.arrayBuffer()));
})().catch(error=>{console.error(error);process.exitCode=1;});
'''
    with http_server(tmp_path) as (server, request):
        status, listing = request('/api/workbench/documents?kind=native_research')
        assert status == 200 and len(listing['documents']) == 1
        assert listing['documents'][0]['id'] == record['id']
        assert listing['documents'][0]['recorded_at'] == record['recorded_at']
        assert listing['validation'] == 'content_identity_only; full_native_replay_on_download'
        base = f'http://127.0.0.1:{server.server_port}'
        opener = build_opener(ProxyHandler({}))
        with opener.open(base + '/api/workbench/document?id=' + record['id'], timeout=10) as response:
            assert response.status == 200
            raw_http = response.read()
        result = subprocess.run([shutil.which('node'), '-e', script, base, record['id'], str(output)],
                                capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    assert raw_http == output.read_bytes() == encode_json(record)
    downloaded = native.parse_native_json(output.read_text(encoding='utf-8'))
    assert canonical(native.validate_native_record(downloaded)) == canonical(record)
