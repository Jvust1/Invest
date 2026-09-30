"""Local SDK + real loopback HTTP proofs; synthetic studies, no provider traffic."""
from contextlib import contextmanager
import builtins
import importlib.util
import io
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import threading
from urllib.error import HTTPError
from urllib.request import Request, build_opener, ProxyHandler
import zipfile

import pytest

from invest.backup import export_backup, restore_backup
from invest.data import demo_dataset
from invest.experiments import run_study
from invest.mlflow_tracking import LocalMLflowArchive, _artifact_path, _checked_record
from invest.server import InvestServer
from invest.workspace import Workspace

HAS_MLFLOW = importlib.util.find_spec("mlflow") is not None
sdk = pytest.mark.skipif(not HAS_MLFLOW, reason="optional real MLflow SDK is not installed")
REPO = Path(__file__).resolve().parents[1]


@contextmanager
def http_server(root, *, enabled=False):
    server = InvestServer(("127.0.0.1", 0), root, track_experiments=enabled)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    opener = build_opener(ProxyHandler({}))

    def request(path, payload=None, headers=None):
        h = {"Content-Type": "application/json", "X-Invest-CSRF": server.csrf_token}
        h.update(headers or {})
        req = Request(f"http://127.0.0.1:{server.server_port}" + path,
                      data=json.dumps(payload).encode() if payload is not None else None, headers=h)
        try:
            response = opener.open(req, timeout=60)
        except HTTPError as exc:
            response = exc
        with response:
            raw = response.read()
            return response.status, json.loads(raw) if "json" in response.headers.get("Content-Type", "") else raw

    try:
        yield server, request
    finally:
        server.shutdown()
        thread.join(5)
        server.server_close()


def study_request(request):
    code, dataset = request("/api/datasets/demo", {})
    assert code == 200
    return {"dataset_id": dataset["id"], "specification": {
        "symbol": "600000.SH", "cost_model_acknowledged": True}}


def saved_record(root):
    return Workspace(root / "state.sqlite").put("study", run_study(demo_dataset(), {
        "symbol": "600000.SH", "cost_model_acknowledged": True}))


def sdk_probe(root, script, *args):
    """Release SDK engine handles before Windows tmpdir removal; deny all HTTP."""
    prefix = '''
import os, sys, json
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, sys.argv[1])
root = Path(sys.argv[2])
os.environ['MLFLOW_DISABLE_TELEMETRY'] = 'true'
os.environ['DO_NOT_TRACK'] = 'true'
network = patch('requests.sessions.Session.request', side_effect=AssertionError('HTTP forbidden')).start()
from mlflow import MlflowClient
from mlflow.telemetry.client import get_telemetry_client
assert get_telemetry_client() is None
uri = 'sqlite:///' + (root / 'mlflow' / 'tracking.sqlite').as_posix()
client = MlflowClient(tracking_uri=uri, registry_uri=uri)
'''
    env = {k: v for k, v in os.environ.items() if not k.startswith("MLFLOW_")}
    env["MLFLOW_DISABLE_TELEMETRY"] = "true"
    env["DO_NOT_TRACK"] = "true"
    result = subprocess.run([sys.executable, "-I", "-c", prefix + script + "\nassert network.call_count == 0\n",
                             str(REPO), str(root), *args], capture_output=True, text=True, env=env, timeout=60)
    assert result.returncode == 0, result.stderr
    return result.stdout


def test_default_mode_preserves_response_and_does_not_import_sdk(tmp_path, monkeypatch):
    original = builtins.__import__

    def no_mlflow(name, *args, **kwargs):
        assert name != "mlflow" and not name.startswith("mlflow."), "disabled mode imported SDK"
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_mlflow)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("disabled mode spawned worker"))
    with http_server(tmp_path) as (_, request):
        payload = study_request(request)
        code, record = request("/api/workbench/study", payload)
        assert code == 200
        assert "tracking" not in record
        assert request("/api/workbench/document?id=" + record["id"])[1] == record
        assert request("/api/workbench/status")[1]["experiment_tracking"]["enabled"] is False
        assert request("/api/workbench/track-study", {"study_id": record["id"]})[1]["tracking"]["status"] == "disabled"
    assert not (tmp_path / "mlflow").exists()


@sdk
def test_real_http_save_sdk_readback_repeat_and_backup(tmp_path, monkeypatch):
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://remote.invalid/tracking")
    monkeypatch.setenv("MLFLOW_REGISTRY_URI", "https://remote.invalid/registry")
    monkeypatch.setenv("MLFLOW_EXPERIMENT_NAME", "untrusted-experiment")
    monkeypatch.setenv("MLFLOW_DISABLE_TELEMETRY", "false")
    monkeypatch.setenv("MLFLOW_ENABLE_ASYNC_LOGGING", "true")
    monkeypatch.setenv("MLFLOW_RUN_ID", "untrusted-active-run")
    with http_server(tmp_path, enabled=True) as (server, request):
        payload = study_request(request)
        code, response = request("/api/workbench/study", payload)
        assert code == 200
        tracking = response.pop("tracking")
        assert tracking["status"] == "archived", tracking
        assert tracking["reused"] is False
        assert request("/api/workbench/document?id=" + response["id"])[1] == response
        repeated = request("/api/workbench/study", payload)[1]
        assert repeated["id"] == response["id"]
        assert repeated["tracking"]["run_id"] == tracking["run_id"]
        assert repeated["tracking"]["reused"] is True
        retry = request("/api/workbench/track-study", {"study_id": response["id"]})[1]
        assert retry["tracking"]["run_id"] == tracking["run_id"]
        assert not server.study_lock.locked()
        code, backup = request("/api/private-backup", {"confirm_private_export": True})
        assert code == 200
        with zipfile.ZipFile(io.BytesIO(backup)) as z:
            assert set(z.namelist()) == {"paper.sqlite", "state.sqlite", "manifest.json"}
        assert request("/api/workbench/status")[1]["experiment_tracking"]["included_in_private_backup"] is False
    sdk_probe(tmp_path, '''
from invest.mlflow_tracking import LOCAL_EXPERIMENT, _artifact_path
from invest.workspace import Workspace
experiment = client.get_experiment_by_name(LOCAL_EXPERIMENT)
runs = client.search_runs([experiment.experiment_id])
assert len(runs) == 1
run = client.get_run(sys.argv[3])
assert run.info.status == 'FINISHED'
record = Workspace(root / 'state.sqlite').get(sys.argv[4], 'study')
assert run.data.tags['invest.study_id'] == record['id']
assert run.data.tags['invest.dataset_id'] == record['payload']['protocol']['dataset_id']
assert run.data.tags['invest.protocol_id'] == record['payload']['protocol_id']
assert run.data.tags['invest.code_identity'] == record['payload']['protocol']['code_identity']
assert run.data.params['symbol'] == '600000.SH'
assert run.data.metrics['summary.succeeded'] == 18
case = record['payload']['results'][0]
assert run.data.metrics['case.000.total_return'] == case['result']['metrics']['total_return']
assert run.data.metrics['case.000.total_fees'] == case['result']['metrics']['total_fees']
assert json.loads(run.data.params['case.000.descriptor'])['candidate'] == case['candidate']
assert json.loads(run.data.params['candidates']) == record['payload']['protocol']['candidates']
assert len(client.get_metric_history(run.info.run_id, 'summary.succeeded')) == 1
artifact = _artifact_path(run.info.artifact_uri, root / 'mlflow' / 'artifacts') / 'study.json'
assert json.loads(artifact.read_text(encoding='utf-8')) == record
assert client.list_artifacts(run.info.run_id)[0].path == 'study.json'
''', tracking["run_id"], response["id"])
    restored = restore_backup(backup, tmp_path / "restored")
    assert Workspace(restored / "state.sqlite").get(response["id"]) == response
    assert not (restored / "mlflow").exists()
    assert LocalMLflowArchive(restored).archive(response)["status"] == "archived"
    # Subprocess completion must leave no SQLite handles that prevent moves on Windows.
    archive = tmp_path / "mlflow"
    archive.rename(tmp_path / "archive-moved")


@pytest.mark.parametrize("failure", ["exception", "timeout", "bad_output", "missing_sdk"])
def test_archive_failure_keeps_authoritative_http_study(tmp_path, monkeypatch, failure):
    def fail(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired(args[0], 45)
        if failure == "exception":
            raise OSError("private path and token must not be reflected")
        raw = (b'{"status":"failed","reason":"mlflow_extra_required","study_saved":true}'
               if failure == "missing_sdk" else b"invalid output")
        return subprocess.CompletedProcess(args[0], 0, raw, b"")

    monkeypatch.setattr(subprocess, "run", fail)
    with http_server(tmp_path, enabled=True) as (server, request):
        code, response = request("/api/workbench/study", study_request(request))
        assert code == 200
        status = response.pop("tracking")
        assert status["status"] == "failed" and status["study_saved"] is True
        assert "private" not in json.dumps(status)
        assert request("/api/workbench/document?id=" + response["id"])[1] == response
        assert len(server.workspace.list("study")) == 1
        assert not server.study_lock.locked()


@sdk
def test_actual_partial_failure_retries_same_run_without_duplicate_metrics(tmp_path):
    record = saved_record(tmp_path)
    sdk_probe(tmp_path, '''
from invest.mlflow_tracking import _archive_local, LOCAL_EXPERIMENT
from invest.workspace import Workspace
record = Workspace(root / 'state.sqlite').get(sys.argv[3])
with patch.object(MlflowClient, 'log_text', side_effect=OSError('synthetic local write failure')):
    try:
        _archive_local(record, root)
    except OSError:
        pass
    else:
        raise AssertionError('write failure was not reported')
experiment = client.get_experiment_by_name(LOCAL_EXPERIMENT)
runs = client.search_runs([experiment.experiment_id])
assert len(runs) == 1 and runs[0].info.status == 'FAILED'
failed_id = runs[0].info.run_id
result = _archive_local(record, root)
assert result['run_id'] == failed_id
assert result['status'] == 'archived'
assert client.get_run(failed_id).info.status == 'FINISHED'
assert len(client.get_metric_history(failed_id, 'summary.succeeded')) == 1
assert Workspace(root / 'state.sqlite').get(record['id']) == record
''', record["id"])


@sdk
@pytest.mark.parametrize("column", ["artifact_uri", "artifact_location"])
@pytest.mark.parametrize("destination", ["https://remote.invalid/study", "file:///outside-archive", "file://remote.invalid/share"])
def test_existing_backend_cannot_redirect_artifacts(tmp_path, column, destination):
    record = saved_record(tmp_path)
    archive = LocalMLflowArchive(tmp_path)
    first = archive.archive(record)
    assert first["status"] == "archived"
    table = "runs" if column == "artifact_uri" else "experiments"
    with sqlite3.connect(tmp_path / "mlflow" / "tracking.sqlite") as db:
        db.execute(f"UPDATE {table} SET {column}=?", (destination,))
    result = archive.archive(record)
    assert result["status"] == "failed"
    assert Workspace(tmp_path / "state.sqlite").get(record["id"]) == record


@sdk
def test_existing_symlink_cannot_escape_archive_root(tmp_path):
    record = saved_record(tmp_path)
    archive = LocalMLflowArchive(tmp_path)
    assert archive.archive(record)["status"] == "archived"
    artifact = next((tmp_path / "mlflow" / "artifacts").rglob("study.json"))
    outside = tmp_path / "outside.json"
    outside.write_text("private sentinel", encoding="utf-8")
    artifact.unlink()
    try:
        artifact.symlink_to(outside)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    assert archive.archive(record)["status"] == "failed"
    assert outside.read_text() == "private sentinel"


def test_artifact_uri_validation_rejects_remote_relative_and_sibling_paths(tmp_path):
    root = tmp_path / "artifacts"
    root.mkdir()
    assert _artifact_path((root / "run" / "artifacts").as_uri(), root) == root / "run" / "artifacts"
    for bad in ("https://remote.invalid/a", "s3://bucket/a", "file://host/share", "relative/path",
                "file:relative/path", (tmp_path / "artifacts-sibling").as_uri(), root.as_uri() + "?query=x"):
        with pytest.raises(ValueError):
            _artifact_path(bad, root)


def test_http_guards_and_lock_cover_tracking_route(tmp_path, monkeypatch):
    with http_server(tmp_path, enabled=True) as (server, request):
        record = saved_record(tmp_path)
        monkeypatch.setattr(server.experiment_archive, "archive", lambda r: pytest.fail("guard bypass"))
        payload = {"study_id": record["id"]}
        for h in ({"Host": "bad.invalid"}, {"Origin": "https://bad.invalid"},
                  {"Sec-Fetch-Site": "cross-site"}, {"X-Invest-CSRF": "wrong"}):
            assert request("/api/workbench/track-study", payload, h)[0] == 403
        server.study_lock.acquire()
        try:
            assert request("/api/workbench/track-study", payload)[0] == 409
        finally:
            server.study_lock.release()
        assert request("/api/workbench/track-study", {"study_id": "bad"})[0] == 400
        assert not server.study_lock.locked()


def test_invalid_records_and_frozen_executable_never_spawn(tmp_path, monkeypatch):
    record = saved_record(tmp_path)
    archive = LocalMLflowArchive(tmp_path)
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("invalid record spawned worker"))
    bad = dict(record, id="0" * 64)
    with pytest.raises(ValueError):
        _checked_record(bad)
    assert archive.archive(bad)["status"] == "failed"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert archive.archive(record)["reason"] == "source_python_required"


@sdk
def test_parallel_archive_workers_serialize_one_run(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    record = saved_record(tmp_path)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: LocalMLflowArchive(tmp_path).archive(record), range(2)))
    assert all(r["status"] == "archived" for r in results), results
    assert results[0]["run_id"] == results[1]["run_id"]
    assert sorted(r["reused"] for r in results) == [False, True]


def test_writer_lock_budget_fits_unchanged_worker_deadline():
    from invest.mlflow_tracking import ARCHIVE_LOCK_TIMEOUT, WORKER_TIMEOUT
    assert ARCHIVE_LOCK_TIMEOUT == 30
    assert ARCHIVE_LOCK_TIMEOUT < WORKER_TIMEOUT == 45


@sdk
def test_writer_waits_past_old_ten_second_boundary(tmp_path):
    record = saved_record(tmp_path)
    (tmp_path/'mlflow').mkdir()
    sdk_probe(tmp_path, r'''
import sqlite3, threading, time
from invest.mlflow_tracking import _archive_local
from invest.workspace import Workspace
record = Workspace(root/'state.sqlite').get(sys.argv[3], 'study')
# The SDK is already imported by sdk_probe. This separate writer deterministically
# holds the lock beyond the former 10-second limit without doing any network IO.
lock = sqlite3.connect(root/'mlflow'/'archive-lock.sqlite', check_same_thread=False)
lock.execute('BEGIN IMMEDIATE')
timer = threading.Timer(12, lock.close)
timer.start()
started = time.monotonic()
try:
    result = _archive_local(record, root)
finally:
    timer.join()
assert result['status'] == 'archived', result
assert time.monotonic() - started >= 11
assert Workspace(root/'state.sqlite').get(record['id'], 'study') == record
''', record['id'])


def test_worker_reports_busy_without_leaking_sqlite_details():
    # The worker's permanent audit hook must not affect later pytest HTTP tests.
    script = r'''
import io, json, sqlite3, sys
sys.path.insert(0, sys.argv[1])
from invest import mlflow_tracking as module
original_stdout = sys.stdout
results = []
for code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_LOCKED | 256, sqlite3.SQLITE_IOERR):
    def fail(*args):
        error = sqlite3.OperationalError('private filesystem details must not leak')
        error.sqlite_errorcode = code
        raise error
    module._archive_local = fail
    sys.stdin = io.TextIOWrapper(io.BytesIO(b'{}'))
    sys.stdout = io.StringIO()
    module._worker_main('unused')
    results.append(json.loads(sys.stdout.getvalue()))
sys.stdout = original_stdout
print(json.dumps(results))
'''
    result = subprocess.run([sys.executable, '-I', '-c', script, str(REPO)],
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    statuses = json.loads(result.stdout)
    assert [r['reason'] for r in statuses] == ['archive_busy']*3 + ['local_archive_unavailable']
    assert all(r == {'status': 'failed', 'reason': r['reason'], 'study_saved': True} for r in statuses)
    assert 'private filesystem' not in result.stdout


@sdk
def test_completed_artifact_tampering_and_duplicate_run_fail_closed(tmp_path):
    record = saved_record(tmp_path)
    archive = LocalMLflowArchive(tmp_path)
    assert archive.archive(record)["status"] == "archived"
    artifact = next((tmp_path / "mlflow" / "artifacts").rglob("study.json"))
    original = artifact.read_bytes()
    artifact.write_text('{"id":"forged"}', encoding="utf-8")
    assert archive.archive(record)["status"] == "failed"
    artifact.write_bytes(original)
    sdk_probe(tmp_path, '''
from invest.mlflow_tracking import LOCAL_EXPERIMENT
experiment = client.get_experiment_by_name(LOCAL_EXPERIMENT)
run = client.search_runs([experiment.experiment_id])[0]
client.create_run(experiment.experiment_id, tags=dict(run.data.tags))
''')
    assert archive.archive(record)["status"] == "failed"
    assert Workspace(tmp_path / "state.sqlite").get(record["id"]) == record


def test_schema_and_mode_are_bound_before_worker_import(tmp_path):
    import copy
    from invest.mlflow_tracking import STUDY_MODES
    from invest.workspace import digest
    record = saved_record(tmp_path)
    for schema, mode in STUDY_MODES.items():
        probe = copy.deepcopy(record)
        probe["payload"]["schema"] = schema
        probe["payload"]["protocol"].update(schema=schema, mode=mode)
        probe["payload"]["protocol_id"] = digest(probe["payload"]["protocol"])
        probe["id"] = digest({"kind": "study", "payload": probe["payload"]})
        assert _checked_record(probe)
        for field, value in (("mode", "UNKNOWN"), ("schema", "UNKNOWN")):
            bad = copy.deepcopy(probe)
            bad["payload"]["protocol"][field] = value
            bad["payload"]["protocol_id"] = digest(bad["payload"]["protocol"])
            bad["id"] = digest({"kind": "study", "payload": bad["payload"]})
            with pytest.raises(ValueError):
                _checked_record(bad)


def test_sqlite_uri_delimiter_paths_fail_before_sdk_import(tmp_path, monkeypatch):
    from invest.mlflow_tracking import _archive_local
    record = saved_record(tmp_path)
    for suffix in ("?uri=true", "#fragment"):
        with pytest.raises(ValueError, match="SQLite URI"):
            _archive_local(record, str(tmp_path) + suffix)


@sdk
def test_same_root_wrong_run_directory_is_rejected(tmp_path):
    record = saved_record(tmp_path)
    archive = LocalMLflowArchive(tmp_path)
    first = archive.archive(record)
    assert first["status"] == "archived"
    sibling = tmp_path / "mlflow" / "artifacts" / "other-run" / "artifacts"
    sibling.mkdir(parents=True)
    sentinel = sibling / "study.json"
    sentinel.write_text("other study sentinel", encoding="utf-8")
    with sqlite3.connect(tmp_path / "mlflow" / "tracking.sqlite") as db:
        db.execute("UPDATE runs SET artifact_uri=?", (sibling.as_uri(),))
    assert archive.archive(record)["status"] == "failed"
    assert sentinel.read_text() == "other study sentinel"


def test_unsupported_sdk_version_is_rejected_before_import(tmp_path, monkeypatch):
    import importlib.metadata
    from invest.mlflow_tracking import UnsupportedMLflowVersion, _archive_local
    record = saved_record(tmp_path)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "3.0.0")
    with pytest.raises(UnsupportedMLflowVersion):
        _archive_local(record, tmp_path)


@sdk
def test_internal_symlink_cannot_redirect_study_artifact(tmp_path):
    record = saved_record(tmp_path)
    archive = LocalMLflowArchive(tmp_path)
    assert archive.archive(record)["status"] == "archived"
    artifact = next((tmp_path / "mlflow" / "artifacts").rglob("study.json"))
    sentinel = artifact.with_name("other.json")
    sentinel.write_bytes(artifact.read_bytes())
    artifact.unlink()
    try:
        artifact.symlink_to(sentinel)
    except OSError:
        pytest.skip("symlink creation is unavailable on this platform")
    assert archive.archive(record)["status"] == "failed"


@sdk
def test_failed_research_cases_are_preserved_without_return_metrics(tmp_path, monkeypatch):
    from invest import experiments
    monkeypatch.setattr(experiments, "backtest", lambda *a, **k: (_ for _ in ()).throw(ValueError("synthetic case failure")))
    record = saved_record(tmp_path)
    assert record["payload"]["summary"]["failed"] == 18
    result = LocalMLflowArchive(tmp_path).archive(record)
    assert result["status"] == "archived"
    sdk_probe(tmp_path, '''
from invest.mlflow_tracking import _artifact_path
run = client.get_run(sys.argv[3])
assert run.data.metrics['summary.failed'] == 18
assert run.data.metrics['case.000.passed'] == 0
assert 'case.000.total_return' not in run.data.metrics
artifact = _artifact_path(run.info.artifact_uri, root / 'mlflow' / 'artifacts') / 'study.json'
record = json.loads(artifact.read_text(encoding='utf-8'))
assert all(case['reason'] == 'synthetic case failure' for case in record['payload']['results'])
''', result["run_id"])
