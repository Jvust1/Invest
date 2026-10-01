"""Fast contract tests for the synthetic-only journal comparison tool."""
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from tools import profile_mlflow_journals as profile


def test_counterbalanced_order_and_bounded_repeat_count():
    assert profile.case_order(4) == ("DELETE", "PERSIST", "PERSIST", "DELETE", "PERSIST", "DELETE", "DELETE", "PERSIST")
    for count in range(1, 5):
        order = profile.case_order(count)
        assert order.count("DELETE") == order.count("PERSIST") == count
    for value in (0, 5, -1, True, 1.5, "4"):
        with pytest.raises(ValueError):
            profile.case_order(value)


@pytest.mark.parametrize("mode", ["DELETE", "PERSIST"])
def test_public_connection_policy_is_exact_path_scoped_and_cleans_up(tmp_path, mode):
    sa = pytest.importorskip("sqlalchemy")
    from sqlalchemy.pool import NullPool

    database = tmp_path / "tracking.sqlite"
    unrelated = tmp_path / "unrelated.sqlite"
    counts, cleanup, snapshots = profile.empty_counts(), {}, []
    target = sa.create_engine("sqlite:///" + database.as_posix(), poolclass=NullPool)
    other = sa.create_engine("sqlite:///" + unrelated.as_posix(), poolclass=NullPool)
    try:
        with profile.connection_policy(database, mode, counts, lambda: snapshots.append(dict(counts)), cleanup):
            for _ in range(2):
                with target.connect() as conn:
                    assert conn.exec_driver_sql("PRAGMA main.journal_mode").scalar() == mode.lower()
                    assert conn.exec_driver_sql("PRAGMA main.synchronous").scalar() == 2
                    assert conn.exec_driver_sql("PRAGMA main.locking_mode").scalar() == "normal"
            with other.connect() as conn:
                assert conn.exec_driver_sql("PRAGMA main.journal_mode").scalar() == "delete"
        assert cleanup == {"removed": True}
        assert counts == {"sqlite_connections": 3, "matched": 2, "configured": 2,
                          "verified": 2, "unrelated_untouched": 1, "rejected": 0}
        assert len(snapshots) == 3
        before = dict(counts)
        with target.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA main.journal_mode").scalar() == "delete"
        assert counts == before
    finally:
        target.dispose()
        other.dispose()


def test_policy_cleanup_preserves_body_error(tmp_path):
    pytest.importorskip("sqlalchemy")
    cleanup = {}
    error = ValueError("private error")
    with pytest.raises(ValueError) as caught:
        with profile.connection_policy(tmp_path / "tracking.sqlite", "PERSIST", profile.empty_counts(), lambda: None, cleanup):
            raise error
    assert caught.value is error
    assert cleanup == {"removed": True}


def test_preopen_journal_path_guard_rejects_redirection(tmp_path):
    sentinel = tmp_path / "sentinel"
    sentinel.write_bytes(b"unchanged")
    database = tmp_path / "tracking.sqlite"
    journal = Path(str(database) + "-journal")
    try:
        journal.symlink_to(sentinel)
    except OSError:
        pytest.skip("symlink creation unavailable")
    with pytest.raises(ValueError):
        profile.check_paths(database)
    assert not database.exists()
    assert sentinel.read_bytes() == b"unchanged"


def test_output_is_fixed_bounded_and_does_not_reflect_private_data():
    counts = profile.empty_counts()
    counts.update(sqlite_connections=2, matched=2, configured=2, verified=2)
    stderr = (
        "private path/credential/SQL\n" + profile.POLICY_MARKER + json.dumps(counts) + "\n"
        + profile.POLICY_MARKER + json.dumps({**counts, "private": "secret"}) + "\n"
        + profile.MARKER + json.dumps({"name": "private_name", "seconds": 1}) + "\n"
        + profile.MARKER + json.dumps({"name": "schema_upgrade", "seconds": 2, "error_type": "PrivateSecret"}) + "\n"
    ).encode()
    payload = {"worker": {"status": "failed"}, "connection_policy": counts, "checks": {"integrity_ok": True, "foreign_keys_ok": "secret"},
               "listener_removed": True, "private": "secret"}
    worker, phases, actual, checks, removed = profile.observations(json.dumps(payload).encode(), stderr)
    assert worker == {"status": "failed"}
    assert phases == [{"name": "schema_upgrade", "seconds": 2}]
    assert actual == counts
    assert checks == {"integrity_ok": True, "foreign_keys_ok": None, "schema_head_matches": None}
    assert removed is True
    assert "secret" not in json.dumps([phases, actual, checks, removed]).lower()
    repeated = ((profile.MARKER + '{"name":"schema_upgrade","seconds":1}\n') * 1000).encode()
    assert len(profile.observations(b"{}", repeated)[1]) <= 100
    assert profile.observations(b"x" * (profile.MAX_STDOUT + 1), b"")[0] == {}
    assert profile.observations(b"{}", b"x" * (profile.MAX_DIAGNOSTIC_BYTES + 1))[1] == []
    worker = profile.observations(b'{"worker":{"status":[],"reason":{},"run_id":"private"}}', b"")[0]
    assert worker == {"reason": "unrecognized_reason"}
    huge = (profile.MARKER + '{"name":"schema_upgrade","seconds":' + '9' * 400 + '}\n').encode()
    assert profile.observations(b"{}", huge)[1] == []
    nested = b'{"nested":' + b'[' * 1200 + b'0' + b']' * 1200 + b'}'
    assert len(nested) < profile.MAX_STDOUT
    assert profile.observations(nested, b"")[0] == {}


def test_binary_utf8_transport_ignores_child_text_locale():
    raw = json.dumps({"name": "中文合成测试"}, ensure_ascii=False).encode("utf-8")
    child = "import json,sys;sys.stdin.reconfigure(encoding='cp1252');p=json.loads(sys.stdin.buffer.read());print(json.dumps(p))"
    result = subprocess.run([sys.executable, "-I", "-c", child], input=raw, capture_output=True, timeout=5)
    assert result.returncode == 0
    assert json.loads(result.stdout) == json.loads(raw)


def test_case_timeout_retains_observations_and_unchanged_budget(tmp_path, monkeypatch):
    raw = '{"name":"中文"}'.encode("utf-8")
    seen = []
    monkeypatch.setenv("MLFLOW_TRACKING_URI", "https://untrusted.invalid")
    monkeypatch.setenv("MLFLOW_DISABLE_TELEMETRY", "false")
    def timed_out(command, **kwargs):
        seen.append(command)
        assert kwargs["input"] is raw
        assert "text" not in kwargs and "encoding" not in kwargs
        assert kwargs["timeout"] == 45 and kwargs["check"] is False
        assert "MLFLOW_TRACKING_URI" not in kwargs["env"]
        assert kwargs["env"]["MLFLOW_DISABLE_TELEMETRY"] == "true"
        assert kwargs["env"]["DO_NOT_TRACK"] == "true"
        assert kwargs["env"]["MLFLOW_ENABLE_ASYNC_LOGGING"] == "false"
        assert command[1] == "-I"
        assert profile.CHILD.index("sys.addaudithook") < profile.CHILD.index("from tools")
        kwargs["stdout"].write(b'{"worker":{"status":"archived"}}')
        kwargs["stderr"].write((profile.MARKER + '{"name":"schema_upgrade","seconds":12}\n').encode())
        raise subprocess.TimeoutExpired(command, 45)
    monkeypatch.setattr(subprocess, "run", timed_out)
    result = profile.run_case(tmp_path, tmp_path / "case", "PERSIST", 1, raw)
    assert len(seen) == 1
    assert result["process_timeout"] is True and result["case_completed"] is False
    assert result["reported_worker_status"] == "archived"
    assert result["case_outcome"] == "timeout"
    assert result["phases"] == [{"name": "schema_upgrade", "seconds": 12}]
    assert result["committed_evidence"] == {"success_emitted": False}
    assert "untrusted" not in json.dumps(result)


@pytest.mark.parametrize("returncode,expected", [(0, "archived"), (1, "process_failed")])
def test_postexit_completion_is_required_independently_of_committed_evidence(tmp_path, monkeypatch, returncode, expected):
    run_id = "a" * 32
    counts = profile.empty_counts()
    counts.update(sqlite_connections=2, matched=2, configured=2, verified=2)
    payload = {"worker": {"status": "archived", "run_id": run_id}, "connection_policy": counts,
               "checks": dict.fromkeys(profile.CHECK_KEYS, True), "listener_removed": True}
    stdout = json.dumps(payload).encode()
    stderr = (profile.POLICY_MARKER + json.dumps(counts)).encode()
    def completed(command, **kwargs):
        kwargs["stdout"].write(stdout)
        kwargs["stderr"].write(stderr)
        return subprocess.CompletedProcess(command, returncode)
    monkeypatch.setattr(subprocess, "run", completed)
    monkeypatch.setattr(profile, "verify_committed", lambda *args:
                        {"success_emitted": True, "artifact_matches": True, "database_finished": True})
    result = profile.run_case(tmp_path, tmp_path / "case", "DELETE", 1, b"{}")
    assert result["case_outcome"] == expected
    assert result["committed_evidence"]["database_finished"] is True
    assert run_id not in json.dumps(result)
    assert len(json.dumps(result).encode()) < 16 * 1024


def test_final_counters_override_stale_success_snapshot_and_truncation_fails_verification(tmp_path, monkeypatch):
    good = profile.empty_counts()
    good.update(sqlite_connections=2, matched=2, configured=2, verified=2)
    rejected = {**good, "sqlite_connections": 3, "matched": 3, "rejected": 1}
    payload = {"worker": {"status": "archived", "run_id": "a" * 32}, "connection_policy": rejected,
               "checks": dict.fromkeys(profile.CHECK_KEYS, True), "listener_removed": True}
    stderr = (profile.POLICY_MARKER + json.dumps(good) + "\n").encode()
    assert profile.observations(json.dumps(payload).encode(), stderr)[2] == rejected
    payload["connection_policy"] = good
    def truncated(command, **kwargs):
        kwargs["stdout"].write(json.dumps(payload).encode())
        kwargs["stderr"].write(stderr + b"x" * profile.MAX_DIAGNOSTIC_BYTES)
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, "run", truncated)
    monkeypatch.setattr(profile, "verify_committed", lambda *args:
                        {"success_emitted": True, "artifact_matches": True, "database_finished": True})
    result = profile.run_case(tmp_path, tmp_path / "case", "DELETE", 1, b"{}")
    assert result["diagnostic_output_truncated"] is True
    assert result["case_outcome"] == "verification_failed"


def test_private_file_capture_bounds_reads_and_reports_truncation(tmp_path, monkeypatch):
    def noisy(command, **kwargs):
        assert "capture_output" not in kwargs
        kwargs["stdout"].write(b"x" * (profile.MAX_STDOUT + 20))
        kwargs["stderr"].write(b"x" * (profile.MAX_DIAGNOSTIC_BYTES + 20))
        return subprocess.CompletedProcess(command, 0)
    monkeypatch.setattr(subprocess, "run", noisy)
    result = profile.run_case(tmp_path, tmp_path / "case", "DELETE", 1, b"{}")
    assert result["diagnostic_output_truncated"] is True
    assert result["case_outcome"] == "archive_failed"
    assert len(json.dumps(result).encode()) < 16 * 1024


def test_collection_runs_each_case_once_and_exits_zero_on_failed_observations(monkeypatch, capsys):
    calls = []
    def failed(_package, destination, mode, index, raw):
        calls.append((destination, mode, index))
        assert type(raw) is bytes and json.loads(raw)["kind"] == "study"
        return {"case": index, "mode": mode, "process_timeout": True, "worker_status": "not_emitted"}
    monkeypatch.setattr(profile, "run_case", failed)
    assert profile.main(["--repeats", "4"]) == 0
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(lines) == len(calls) == 8
    assert [call[1] for call in calls] == list(profile.ORDER)
    assert len({call[0] for call in calls}) == 8
    assert all(not call[0].parent.exists() for call in calls)
